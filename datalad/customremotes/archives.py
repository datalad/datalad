# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Custom remote to get the load from archives present under annex"""

__docformat__ = 'restructuredtext'

import logging
import os
import os.path as op
import shutil
from operator import itemgetter
from pathlib import Path
from urllib.parse import urlparse

from annexremote import UnsupportedRequest

from datalad.consts import ARCHIVES_SPECIAL_REMOTE
from datalad.customremotes import RemoteError
from datalad.customremotes.main import main as super_main
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.archives import ArchivesCache
from datalad.support.cache import DictCache
from datalad.support.exceptions import CapturedException
from datalad.support.locking import lock_if_check_fails
from datalad.support.network import URL
from datalad.utils import (
    ensure_bytes,
    get_dataset_root,
    getpwd,
    unique,
    unlink,
)

from .base import AnnexCustomRemote

lgr = logging.getLogger('datalad.customremotes.archive')


# ####
# Preserve from previous version
# TODO: document intention
# ####
# this one might get under Runner for better output/control
def link_file_load(src, dst, dry_run=False):
    """Just a little helper to hardlink files's load
    """
    dst_dir = op.dirname(dst)
    if not op.exists(dst_dir):
        os.makedirs(dst_dir)
    if op.lexists(dst):
        lgr.log(9, "Destination file %(dst)s exists. Removing it first",
                locals())
        # TODO: how would it interact with git/git-annex
        unlink(dst)
    lgr.log(9, "Hardlinking %(src)s under %(dst)s", locals())
    src_realpath = op.realpath(src)

    try:
        os.link(src_realpath, dst)
    except (OSError, AttributeError) as e:
        # we need to catch OSError too, because Python's own logic
        # of not providing link() where it is known to be unsupported
        # (e.g. Windows) will not cover scenarios where a particular
        # filesystem simply does not implement it on an otherwise
        # sane platform (e.g. exfat on Linux)
        lgr.warning("Linking of %s failed (%s), copying file", src, e)
        shutil.copyfile(src_realpath, dst)
        shutil.copystat(src_realpath, dst)
    else:
        lgr.log(2, "Hardlinking finished")


# TODO: RF functionality not specific to being a custom remote (loop etc)
#       into a separate class
class ArchiveAnnexCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives

     Archives must be under annex'ed themselves.
    """
    CUSTOM_REMOTE_NAME = "archive"
    SUPPORTED_SCHEMES = (
        AnnexCustomRemote._get_custom_scheme(CUSTOM_REMOTE_NAME),)
    # Since we support only 1 scheme here
    URL_SCHEME = SUPPORTED_SCHEMES[0]
    URL_PREFIX = URL_SCHEME + ":"

    COST = 500

    def __init__(self, annex, path=None, persistent_cache=True, **kwargs):
        super().__init__(annex)

        # MIH figure out what the following is all about
        # in particular path==None
        self.repo = Dataset(get_dataset_root(Path.cwd())).repo \
            if not path \
            else AnnexRepo(path, create=False, init=False)

        self.path = self.repo.path
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._last_url = None  # for heuristic to choose among multiple URLs
        self._cache = ArchivesCache(self.path, persistent=persistent_cache)
        self._contentlocations = DictCache(size_limit=100)  # TODO: config ?

    def stop(self, *args):
        """Stop communication with annex"""
        self._cache.clean()

    def get_file_url(self, archive_file=None, archive_key=None, file=None,
                     size=None):
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
                raise ValueError(
                    "Provide archive_file or archive_key - not both")
            archive_key = self.repo.get_file_annexinfo(archive_file)['key']
        assert(archive_key is not None)
        attrs = dict()  # looking forward for more
        if file:
            attrs['path'] = file.lstrip('/')
        if size is not None:
            attrs['size'] = size
        return str(URL(scheme=self.URL_SCHEME,
                       path=archive_key,
                       fragment=attrs))

    @property
    def cache(self):
        return self._cache

    def _parse_url(self, url):
        """Parse url and return archive key, file within archive and
        additional attributes (such as size)"""
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

        if `sorted`, then first those which have extracted version in local
        cache will be yielded

        Gets determined based on urls for datalad archives

        Made "generators all the way" as an exercise but also to delay any
        checks etc until really necessary.
        """
        # we will need all URLs anyways later on ATM, so lets list() them
        # Anyways here we have a single scheme (archive) so there is not
        # much optimization possible
        urls = list(self.gen_URLS(key))

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
        # which is not available locally.  But we could still have extracted
        # archive in the cache.  So we need pretty much get first all possible
        # and then only remove those which aren't present locally.  So
        # verify_exists was added
        yielded = set()
        akey_afile_paths_ = []

        # utilize cache to check which archives might already be present in the
        # cache
        for akey_afile, akey_path in akey_afile_paths:
            if akey_path and self.cache[akey_path].is_extracted:
                yield akey_afile
                yielded.add(akey_afile)
            akey_afile_paths_.append((akey_afile, akey_path))

        # replace generators with already collected ones into a list.  The idea
        # that in many cases we don't even need to create a full list and that
        # initial single yield would be enough, thus we don't need to check
        # locations etc for every possible hit
        akey_afile_paths = akey_afile_paths_

        # if not present in the cache -- check which are present
        # locally and choose that one to use, so it would get extracted
        for akey_afile, akey_path in akey_afile_paths:
            if akey_path and op.exists(akey_path):
                yielded.add(akey_afile)
                yield akey_afile

        # So no archive is present either in the cache or originally under
        # annex XXX some kind of a heuristic I guess is to use last_url ;-)
        if self._last_url and self._last_url in urls \
                and (len(urls) == len(akey_afiles)):
            akey_afile, _ = akey_afile_paths[urls.index(self._last_url)]
            yielded.add(akey_afile)
            yield akey_afile

        for akey_afile, _ in akey_afile_paths:
            if akey_afile not in yielded:
                yield akey_afile

    def get_contentlocation(self, key, absolute=False, verify_exists=True):
        """Return (relative to top or absolute) path to the file containing the key

        This is a wrapper around AnnexRepo.get_contentlocation which provides
        caching of the result (we are asking the location for the same archive
        key often)
        """
        if key not in self._contentlocations:
            fpath = self.repo.get_contentlocation(key, batch=True)
            if fpath:  # shouldn't store empty ones
                self._contentlocations[key] = fpath
        else:
            fpath = self._contentlocations[key]
            # but verify that it exists
            if verify_exists and not op.lexists(op.join(self.path, fpath)):
                # prune from cache
                del self._contentlocations[key]
                fpath = ''

        if absolute and fpath:
            return op.join(self.path, fpath)
        else:
            return fpath

    # Protocol implementation
    def checkurl(self, url):
        # TODO:  what about those MULTI and list to be returned?
        #  should we return all filenames or keys within archive?
        #  might be way too many?
        #  only if just archive portion of url is given or the one pointing
        #  to specific file?
        lgr.debug("Current directory: %s, url: %s", os.getcwd(), url)
        akey, afile, attrs = self._parse_url(url)
        size = attrs.get('size', None)

        # But reply that present only if archive is present
        # TODO: this would throw exception if not present, so this statement is
        # kinda bogus
        akey_path = self.get_contentlocation(akey, absolute=True)
        if akey_path:
            # Extract via cache only if size is not yet known
            if size is None:
                # if for testing we want to force getting the archive extracted
                efile = self.cache[akey_path].get_extracted_filename(afile)
                efile = ensure_bytes(efile)

                if op.exists(efile):
                    size = os.stat(efile).st_size

            # so it was a good successful one -- record
            self._last_url = url

            if size is None:
                return True
            else:
                # FIXME: providing filename causes annex to not even talk to
                # ask upon drop :-/
                return [dict(size=size)]  # , basename(afile))

        else:
            # TODO: theoretically we should first check if key is available
            # from any remote to know if file is available
            raise RemoteError(f"archive key {akey} is not available locally.")

    def checkpresent(self, key):
        # TODO: so we need to maintain mapping from urls to keys.  Then
        # we could even store the filename within archive
        # Otherwise it is unrealistic to even require to recompute key if we
        # knew the backend etc
        # The same content could be available from multiple locations within
        # the same archive, so let's not ask it twice since here we don't care
        # about "afile"
        for akey, _ in self._gen_akey_afiles(key, unique_akeys=True):
            if self.get_contentlocation(akey) \
                    or self.repo.is_available(akey, batch=True, key=True):
                return True
        # it is unclear to MIH why this must be UNKNOWN rather than FALSE
        # but this is how I found it
        raise RemoteError('Key not present')

    def remove(self, key):
        raise UnsupportedRequest('This special remote cannot remove content')
        # # TODO: proxy query to the underlying tarball under annex that if
        # # tarball was removed (not available at all) -- report success,
        # # otherwise failure (current the only one)
        # akey, afile = self._get_akey_afile(key)
        # if False:
        #     # TODO: proxy, checking present of local tarball is not
        #     # sufficient
        #     #  not exists(self.get_key_path(key)):
        #     self.send("REMOVE-SUCCESS", akey)
        # else:
        #     self.send("REMOVE-FAILURE", akey,
        #               "Removal from file archives is not supported")

    def whereis(self, key):
        return False
        # although more logical is to report back success, it leads to imho
        # more confusing duplication. See
        # http://git-annex.branchable.com/design/external_special_remote_protocol/#comment-3f9588f6a972ae566347b6f467b53b54
        # try:
        #     key, file = self._get_akey_afile(key)
        #     self.send("WHEREIS-SUCCESS", "file %s within archive %s" % (file, key))
        # except ValueError:
        #     self.send("WHEREIS-FAILURE")

    def transfer_retrieve(self, key, file):
        akeys_tried = []
        # the same file could come from multiple files within the same archive
        # So far it doesn't make sense to "try all" of them since if one fails
        # it means the others would fail too, so it makes sense to immediately
        # prune the list so we keep only the ones from unique akeys.
        # May be whenever we support extraction directly from the tarballs
        # we should go through all and choose the one easiest to get or smth.
        for akey, afile in self._gen_akey_afiles(
                key, sorted=True, unique_akeys=True):
            if not akey:
                lgr.warning("Got an empty archive key %r for key %s. Skipping",
                            akey, key)
                continue
            akeys_tried.append(akey)
            try:
                with lock_if_check_fails(
                    check=(self.get_contentlocation, (akey,)),
                    lock_path=(
                        lambda k: op.join(self.repo.path,
                                          '.git',
                                          'datalad-archives-%s' % k),
                        (akey,)),
                    operation="annex-get"
                ) as (akey_fpath, lock):
                    if lock:
                        assert not akey_fpath
                        self._annex_get_archive_by_key(akey)
                        akey_fpath = self.get_contentlocation(akey)

                if not akey_fpath:
                    raise RuntimeError(
                        "We were reported to fetch it alright but now can't "
                        "get its location.  Check logic"
                    )

                akey_path = op.join(self.repo.path, akey_fpath)
                assert op.exists(akey_path), \
                       "Key file %s is not present" % akey_path

                # Extract that bloody file from the bloody archive
                # TODO: implement/use caching, for now a simple one
                #  actually patool doesn't support extraction of a single file
                #  https://github.com/wummel/patool/issues/20
                # so
                pwd = getpwd()
                lgr.debug(
                    "Getting file %s from %s while PWD=%s",
                    afile, akey_path, pwd)
                was_extracted = self.cache[akey_path].is_extracted
                apath = self.cache[akey_path].get_extracted_file(afile)
                link_file_load(apath, file)
                if not was_extracted and self.cache[akey_path].is_extracted:
                    self.message(
                        "%s special remote is using an extraction cache "
                        "under %s. Remove it with DataLad's 'clean' "
                        "command to save disk space." %
                        (ARCHIVES_SPECIAL_REMOTE,
                         self.cache[akey_path].path),
                        type='info',
                    )
                return
            except Exception as exc:
                ce = CapturedException(exc)
                self.message(
                    "Failed to fetch {akey} containing {key}: {msg}".format(
                        akey=akey,
                        key=key,
                        # we need to get rid of any newlines, or we might
                        # break the special remote protocol
                        msg=str(ce).replace('\n', '|')
                    ))
                continue

        raise RemoteError(
            "Failed to fetch any archive containing {key}. "
            "Tried: {akeys_tried}".format(**locals())
        )

    def claimurl(self, url):
        scheme = urlparse(url).scheme
        if scheme in self.SUPPORTED_SCHEMES:
            return True
        else:
            return False

    def _annex_get_archive_by_key(self, akey):
        # TODO: make it more stringent?
        # Command could have fail to run if key was not present locally yet
        # Thus retrieve the key using annex
        # TODO: we need to report user somehow about this happening and
        # progress on the download
        from humanize import naturalsize

        from datalad.support.annexrepo import AnnexJsonProtocol

        akey_size = self.repo.get_size_from_key(akey)
        self.message(
            "To obtain some keys we need to fetch an archive "
            "of size %s"
            % (naturalsize(akey_size) if akey_size else "unknown"),
            type='info',
        )

        try:
            self.repo._call_annex(
                ["get", "--json", "--json-progress", "--key", akey],
                protocol=AnnexJsonProtocol,
            )
        except Exception:
            self.message(f'Failed to fetch archive with key {akey}')
            raise


def main():
    """cmdline entry point"""
    super_main(
        cls=ArchiveAnnexCustomRemote,
        remote_name='datalad-archives',
        description=\
        "extract content from archives (.tar{,.gz}, .zip, etc) which are "
        "in turn managed by git-annex.  See `datalad add-archive-content` "
        "command",
    )
