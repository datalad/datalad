# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Custom remote to support getting the load from archives present under annex"""

__docformat__ = 'restructuredtext'

import os
from os.path import exists, join as opj
from collections import OrderedDict
from operator import itemgetter

import logging
lgr = logging.getLogger('datalad.customremotes.archive')
lgr.log(5, "Importing datalad.customremotes.archive")

from ..dochelpers import exc_str
from ..cmd import link_file_load
from ..support.archives import ArchivesCache
from ..support.network import URL
from ..utils import getpwd
from ..utils import unique
from .base import AnnexCustomRemote
from .main import main as super_main


# TODO: RF functionality not specific to being a custom remote (loop etc)
#       into a separate class
class ArchiveAnnexCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives

     Archives should also be under annex control.
    """

    CUSTOM_REMOTE_NAME = "archive"
    SUPPORTED_SCHEMES = (AnnexCustomRemote._get_custom_scheme(CUSTOM_REMOTE_NAME),)
    # Since we support only 1 scheme here
    URL_SCHEME = SUPPORTED_SCHEMES[0]
    URL_PREFIX = URL_SCHEME + ":"

    AVAILABILITY = "local"
    COST = 500

    def __init__(self, persistent_cache=True, **kwargs):
        super(ArchiveAnnexCustomRemote, self).__init__(**kwargs)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._last_url = None  # for heuristic to choose among multiple URLs
        self._cache = ArchivesCache(self.path, persistent=persistent_cache)

    def stop(self, *args):
        """Stop communication with annex"""
        self._cache.clean()
        super(ArchiveAnnexCustomRemote, self).stop(*args)

    def get_file_url(self, archive_file=None, archive_key=None, file=None, size=None):
        """Given archive (file or a key) and a file -- compose URL for access

        Examples
        --------

        dl+archive:SHA256E-s176--69...3e.tar.gz#path=1/d2/2d&size=123
            when size of file within archive was known to be 123
        dl+archive:SHA256E-s176--69...3e.tar.gz#path=1/d2/2d
            when size of file within archive was not provided

        Parameters
        ----------
        size: int, optional
          Size of the file.  If not provided, will simply be empty
        """
        assert(file is not None)
        if archive_file is not None:
            if archive_key is not None:
                raise ValueError("Provide archive_file or archive_key - not both")
            archive_key = self.repo.get_file_key(archive_file)
        assert(archive_key is not None)
        attrs = OrderedDict()  # looking forward for more
        if file:
            attrs['path'] = file.lstrip('/')
        if size is not None:
            attrs['size'] = size
        return str(URL(scheme=self.URL_SCHEME, path=archive_key, fragment=attrs))

    @property
    def cache(self):
        return self._cache

    def _parse_url(self, url):
        """Parse url and return archive key, file within archive and additional attributes (such as size)
        """
        url = URL(url)
        assert(url.scheme == self.URL_SCHEME)
        fdict = url.fragment_dict
        if 'path' not in fdict:
            # must be old-style key/path#size=
            assert '/' in url.path, "must be of key/path format"
            key, path = url.path.split('/', 1)
        else:
            key, path = url.path, fdict.pop('path')
        if 'size' in fdict:
            fdict['size'] = int(fdict['size'])
        return key, path, fdict

    def _gen_akey_afiles(self, key, sorted=False, unique_akeys=True):
        """Given a key, yield akey, afile pairs

        if `sorted`, then first those which have extracted version in local cache
        will be yielded

        Gets determined based on urls for datalad archives

        Made "generators all the way" as an exercise but also to delay any
        checks etc until really necessary.
        """
        urls = self.get_URLS(key)

        akey_afiles = [
            self._parse_url(url)[:2]  # skip size
            for url in urls
        ]

        if unique_akeys:
            akey_afiles = unique(akey_afiles, key=itemgetter(0))

        if not sorted:
            for pair in akey_afiles:
                yield pair
            return

        # Otherwise we will go through each one

        # multiple URLs are available so we need to figure out which one
        # would be most efficient to "deal with"
        akey_afile_paths = (
            ((akey, afile), self.get_contentlocation(
                akey,
                absolute=True, verify_exists=False
            ))
            for akey, afile in akey_afiles
        )

        # by default get_contentlocation would return empty result for a key
        # which is not available locally.  But we could still have extracted archive
        # in the cache.  So we need pretty much get first all possible and then
        # only remove those which aren't present locally.  So verify_exists was added
        yielded = set()
        akey_afile_paths_ = []

        # utilize cache to check which archives might already be present in the cache
        for akey_afile, akey_path in akey_afile_paths:
            if akey_path and self.cache[akey_path].is_extracted:
                yield akey_afile
                yielded.add(akey_afile)
            akey_afile_paths_.append((akey_afile, akey_path))

        # replace generators with already collected ones into a list.
        # The idea that in many cases we don't even need to create a full list
        # and that initial single yield would be enough, thus we don't need to check
        # locations etc for every possible hit
        akey_afile_paths = akey_afile_paths_

        # if not present in the cache -- check which are present
        # locally and choose that one to use, so it would get extracted
        for akey_afile, akey_path in akey_afile_paths:
            if akey_path and exists(akey_path):
                yielded.add(akey_afile)
                yield akey_afile

        # So no archive is present either in the cache or originally under annex
        # XXX some kind of a heuristic I guess is to use last_url ;-)
        if self._last_url and self._last_url in urls and (len(urls) == len(akey_afiles)):
            akey_afile, _ = akey_afile_paths[urls.index(self._last_url)]
            yielded.add(akey_afile)
            yield akey_afile

        for akey_afile, _ in akey_afile_paths:
            if akey_afile not in yielded:
                yield akey_afile

    # Protocol implementation
    def req_CHECKURL(self, url):
        """

        Replies

        CHECKURL-CONTENTS Size|UNKNOWN Filename
            Indicates that the requested url has been verified to exist.
            The Size is the size in bytes, or use "UNKNOWN" if the size could
            not be determined.
            The Filename can be empty (in which case a default is used), or can
            specify a filename that is suggested to be used for this url.
        CHECKURL-MULTI Url Size|UNKNOWN Filename ...
            Indicates that the requested url has been verified to exist, and
            contains multiple files, which can each be accessed using their own
            url.
            Note that since a list is returned, neither the Url nor the Filename
            can contain spaces.
        CHECKURL-FAILURE
            Indicates that the requested url could not be accessed.
        """
        # TODO:  what about those MULTI and list to be returned?
        #  should we return all filenames or keys within archive?
        #  might be way too many?
        #  only if just archive portion of url is given or the one pointing
        #  to specific file?
        lgr.debug("Current directory: %s, url: %s" % (os.getcwd(), url))
        akey, afile, attrs = self._parse_url(url)
        size = attrs.get('size', None)

        # But reply that present only if archive is present
        # TODO: this would throw exception if not present, so this statement is kinda bogus
        akey_path = self.get_contentlocation(akey, absolute=True)
        if akey_path:
            # Extract via cache only if size is not yet known
            if size is None:
                # if for testing we want to force getting the archive extracted
                # _ = self.cache.assure_extracted(self._get_key_path(akey)) # TEMP
                efile = self.cache[akey_path].get_extracted_filename(afile)

                if exists(efile):
                    size = os.stat(efile).st_size

            if size is None:
                size = 'UNKNOWN'

            # FIXME: providing filename causes annex to not even talk to ask
            # upon drop :-/
            self.send("CHECKURL-CONTENTS", size)  # , basename(afile))

            # so it was a good successful one -- record
            self._last_url = url
        else:
            # TODO: theoretically we should first check if key is available from
            # any remote to know if file is available
            self.send("CHECKURL-FAILURE")

    def req_CHECKPRESENT(self, key):
        """Check if copy is available

        TODO: just proxy the call to annex for underlying tarball

        Replies

        CHECKPRESENT-SUCCESS Key
            Indicates that a key has been positively verified to be present in
            the remote.
        CHECKPRESENT-FAILURE Key
            Indicates that a key has been positively verified to not be present
            in the remote.
        CHECKPRESENT-UNKNOWN Key ErrorMsg
            Indicates that it is not currently possible to verify if the key is
            present in the remote. (Perhaps the remote cannot be contacted.)
        """
        # TODO: so we need to maintain mapping from urls to keys.  Then
        # we could even store the filename within archive
        # Otherwise it is unrealistic to even require to recompute key if we
        # knew the backend etc
        lgr.debug("VERIFYING key %s" % key)
        # The same content could be available from multiple locations within the same
        # archive, so let's not ask it twice since here we don't care about "afile"
        for akey, _ in self._gen_akey_afiles(key, unique_akeys=True):
            if self.get_contentlocation(akey) or self.repo.is_available(akey, batch=True, key=True):
                self.send("CHECKPRESENT-SUCCESS", key)
                return
        self.send("CHECKPRESENT-UNKNOWN", key)

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned
            if the remote didn't have the key at the point removal was requested
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        self.send("REMOVE-FAILURE", key,
                  "Removal from file archives is not supported")
        return
        # # TODO: proxy query to the underlying tarball under annex that if
        # # tarball was removed (not available at all) -- report success,
        # # otherwise failure (current the only one)
        # akey, afile = self._get_akey_afile(key)
        # if False:
        #     # TODO: proxy, checking present of local tarball is not sufficient
        #     #  not exists(self.get_key_path(key)):
        #     self.send("REMOVE-SUCCESS", akey)
        # else:
        #     self.send("REMOVE-FAILURE", akey,
        #               "Removal from file archives is not supported")

    def req_WHEREIS(self, key):
        """
        WHEREIS-SUCCESS String
            Indicates a location of a key. Typically an url, the string can be anything
            that it makes sense to display to the user about content stored in the special
            remote.
        WHEREIS-FAILURE
            Indicates that no location is known for a key.
        """
        self.send("WHEREIS-FAILURE")
        # although more logical is to report back success, it leads to imho more confusing
        # duplication. See
        # http://git-annex.branchable.com/design/external_special_remote_protocol/#comment-3f9588f6a972ae566347b6f467b53b54

        # try:
        #     key, file = self._get_akey_afile(key)
        #     self.send("WHEREIS-SUCCESS", "file %s within archive %s" % (file, key))
        # except ValueError:
        #     self.send("WHEREIS-FAILURE")

    def _transfer(self, cmd, key, path):

        akeys_tried = []
        # the same file could come from multiple files within the same archive
        # So far it doesn't make sense to "try all" of them since if one fails
        # it means the others would fail too, so it makes sense to immediately
        # prune the list so we keep only the ones from unique akeys.
        # May be whenever we support extraction directly from the tarballs
        # we should go through all and choose the one easiest to get or smth.
        for akey, afile in self._gen_akey_afiles(key, sorted=True, unique_akeys=True):
            akeys_tried.append(akey)
            try:
                akey_fpath = self.get_contentlocation(akey)
                if not akey_fpath:
                    # TODO: make it more stringent?
                    # Command could have fail to run if key was not present locally yet
                    # Thus retrieve the key using annex
                    # TODO: we need to report user somehow about this happening and progress on the download
                    self.runner(["git-annex", "get", "--key", akey],
                                cwd=self.path, expect_stderr=True)

                    akey_fpath = self.get_contentlocation(akey)
                    if not akey_fpath:
                        raise RuntimeError("We were reported to fetch it alright but now can't get its location.  Check logic")

                akey_path = opj(self.repo.path, akey_fpath)
                assert exists(akey_path), "Key file %s is not present" % akey_path

                # Extract that bloody file from the bloody archive
                # TODO: implement/use caching, for now a simple one
                #  actually patool doesn't support extraction of a single file
                #  https://github.com/wummel/patool/issues/20
                # so
                pwd = getpwd()
                lgr.debug("Getting file {afile} from {akey_path} while PWD={pwd}".format(**locals()))
                apath = self.cache[akey_path].get_extracted_file(afile)
                link_file_load(apath, path)
                self.send('TRANSFER-SUCCESS', cmd, key)
                return
            except Exception as exc:
                # from celery.contrib import rdb
                # rdb.set_trace()
                exc_ = exc_str(exc)
                self.debug("Failed to fetch {akey} containing {key}: {exc_}".format(**locals()))
                continue

        self.error("Failed to fetch any archive containing {key}. Tried: {akeys_tried}".format(**locals()))


def main():
    """cmdline entry point"""
    super_main(backend="archive")

lgr.log(5, "Done importing datalad.customremotes.archive")
