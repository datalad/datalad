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
from os.path import exists, join as opj, basename, abspath

from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote

import logging
lgr = logging.getLogger('datalad.customremotes.archive')

from ..cmd import link_file_load, Runner
from ..support.exceptions import CommandError
from ..support.archives import ArchivesCache
from .base import AnnexCustomRemote


# TODO: RF functionality not specific to being a custom remote (loop etc)
#       into a separate class
class AnnexArchiveCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives

     Archives should also be under annex control.
    """

    PREFIX = "archive"
    AVAILABILITY = "local"

    def __init__(self, *args, **kwargs):
        super(AnnexArchiveCustomRemote, self).__init__(*args, **kwargs)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._last_url = None  # for heuristic to choose among multiple URLs
        self._cache = ArchivesCache(self.path)

    def stop(self, *args):
        """Stop communication with annex"""
        self._cache.clean()
        super(AnnexArchiveCustomRemote, self).stop(*args)

    def get_file_url(self, archive_file=None, archive_key=None, file=None):
        """Given archive (file or a key) and a file -- compose URL for access
        """
        assert(file is not None)
        if archive_file is not None:
            if archive_key is not None:
                raise ValueError("Provide archive_file or archive_key - not both")
            archive_key = self.repo.get_file_key(archive_file)
        assert(archive_key is not None)
        file_quoted = urlquote(file)
        return '%s%s/%s' % (self.url_prefix, archive_key, file_quoted.lstrip('/'))

    @property
    def cache(self):
        return self._cache

    def _parse_url(self, url):
        assert(url[:len(self.url_prefix)] == self.url_prefix)
        key, file_ = url[len(self.url_prefix):].split('/', 1)
        return key, file_

    # Helper methods
    def _get_key_url(self, key):
        """Given a key, figure out the URL

        Raises
        ------
        ValueError
            If could not figure out any URL
        """
        urls = self.get_URLS(key)
        if not urls:
            raise ValueError("Do not have any URLs for %s" % key)
        elif len(urls) == 1:
            return urls[0]
        else:  # multiple
            # TODO:  utilize cache to check which archives might already be
            #        present in the cache.
            #    Then if not present in the cache -- check which are present
            #    locally and choose that one to use
            if self._last_url and self._last_url in urls:
                return self._last_url
            else:
                return urls[0]  # just the first one

    def _get_akey_afile(self, key):
        """Given a key, figure out target archive key, and file within archive
        """
        url = self._get_key_url(key)
        return self._parse_url(url)

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
        akey, afile = self._parse_url(url)

        # But reply that present only if archive is present
        # TODO: this would throw exception if not present, so this statement is kinda bogus
        try:
            # throws exception if not present
            akey_path = opj(self.path, self.repo.get_contentlocation(akey))

            # if for testing we want to force getting the archive extracted
            # _ = self.cache.assure_extracted(self._get_key_path(akey)) # TEMP
            efile = self.cache[akey_path].get_extracted_filename(afile)
            if exists(efile):
                size = os.stat(efile).st_size
            else:
                size = 'UNKNOWN'

            # FIXME: providing filename causes annex to not even talk to ask
            # upon drop :-/
            self.send("CHECKURL-CONTENTS", size)#, basename(afile))
        except CommandError:
            # TODO: theoretically we should first check if key is available from
            # any remote to know if file is available
            self.send("CHECKURL-FAILURE")
        self._last_url = url

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
        akey, afile = self._get_akey_afile(key)
        try:
            self.repo.get_contentlocation(akey)
            self.send("CHECKPRESENT-SUCCESS", key)
        except CommandError:
            # TODO: proxy the same to annex itself to verify check for archive.
            # If archive is no longer available -- then CHECKPRESENT-FAILURE
            self.send("CHECKPRESENT-UNKNOWN", key)

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned
            if the remote didn't have the key at the point removal was requested
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        # TODO: proxy query to the underlying tarball under annex that if
        # tarball was removed (not available at all) -- report success,
        # otherwise failure (current the only one)
        akey, afile = self._get_akey_afile(key)
        if False:
            # TODO: proxy, checking present of local tarball is not sufficient
            #  not exists(self.get_key_path(key)):
            self.send("REMOVE-SUCCESS", akey)
        else:
            self.send("REMOVE-FAILURE", akey,
                      "Removal from file archives is not supported")

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
        """
        although more logical is to report back success, it leads to imho more confusing
        duplication. See
        http://git-annex.branchable.com/design/external_special_remote_protocol/#comment-3f9588f6a972ae566347b6f467b53b54

        try:
            key, file = self._get_akey_afile(key)
            self.send("WHEREIS-SUCCESS", "file %s within archive %s" % (file, key))
        except ValueError:
            self.send("WHEREIS-FAILURE")
        """

    def _transfer(self, cmd, key, path):

        akey, afile = self._get_akey_afile(key)
        try:
            akey_path = opj(self.path, self.repo.get_contentlocation(akey))
        except CommandError:
            # TODO: make it more stringent?
            # Command could have fail to run if key was not present locally yet
            # Thus retrieve the key using annex
            try:
                self.runner(["git-annex", "get", "--key", akey],
                            cwd=self.path)
                akey_path = self.repo.get_contentlocation(akey)
                assert(exists(akey_path))
            except Exception as e:
                self.error("Failed to fetch %{akey}s containing %{key}s: %{e}s"
                           % locals())
                return

        # Extract that bloody file from the bloody archive
        # TODO: implement/use caching, for now a simple one
        #  actually patool doesn't support extraction of a single file
        #  https://github.com/wummel/patool/issues/20
        # so
        apath = self.cache[akey_path].get_extracted_file(afile)
        link_file_load(apath, path)
        self.send('TRANSFER-SUCCESS', cmd, key)


from .main import main as super_main
def main():
    """cmdline entry point"""
    super_main(backend="archive")
