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

import errno
import os
import sys
import urllib2

from os.path import exists, join as opj, basename, abspath

import logging

lgr = logging.getLogger('datalad.customremotes.archive')


from ..cmd import link_file_load, Runner
from ..utils import rotree, rmtree

from .base import AnnexCustomRemote

class AnnexArchiveCache(object):
    # TODO: make caching persistent across sessions/runs, with cleanup
    # IDEA: extract under .git/annex/tmp so later on annex unused could clean it
    #       all up
    def __init__(self, path):
        #if exists(path):
        #    self._clean_cache()

        self._path = path

        lgr.debug("Initiating clean cache under %s" % self.path)

        if not exists(path):
            try:
                os.makedirs(path)
                lgr.info("Cache initialized")
            except:
                lgr.error("Failed to initialize cached under %s"
                           % (self.path))
                raise

    @property
    def path(self):
        return self._path

    def clean(self):
        if os.environ.get('DATALAD_TESTS_KEEPTEMP'):
            lgr.info("As instruction, not cleaning up the cache under %s"
                      % self.path)
            return
        lgr.debug("Cleaning up the cache")
        if exists(self._path):
            # TODO:  we must be careful here -- to not modify permissions of files
            #        only of directories
            rmtree(self._path)

    def get_extracted_path(self, archive):
        """Given archive -- return full path to it within cache (extracted)
        """
        return opj(self._path, "%s_" % basename(archive))

    def get_file_path(self, archive, afile):
        return opj(self.get_extracted_path(archive), afile)

    # TODO: remove?
    def has_file_ready(self, archive, afile):
        lgr.debug("Checking file {afile} from archive {archive}".format(**locals()))
        return exists(self.get_file_path(archive, afile))

    def get_extracted_archive(self, archive):
        earchive = self.get_extracted_path(archive)
        if not exists(earchive):
            # we need to extract the archive
            # TODO: extract to _tmp and then move in a single command so we
            # don't end up picking up broken pieces
            lgr.debug("Extracting {archive} under {earchive}".format(**locals()))
            os.makedirs(earchive)
            assert(exists(earchive))
            # TODO: didn't manage to override stdout even with a patch, WTF?
            #import patoolib # with hope to manage to override patoolib's assigned to stdout
            #patoolib.extract_archive(archive, outdir=earchive, out=None)
            # so for now just call patool
            Runner().run(["patool", "extract", "--outdir", earchive, archive])
            lgr.debug("Adjusting permissions to read-only for the extracted contents")
            rotree(earchive)
            assert(exists(earchive))
        return earchive

    def get_extracted_file(self, archive, afile):
        lgr.debug("Requested file {afile} from archive {archive}".format(**locals()))
        # TODO: That could be a good place to provide "compatibility" layer if
        # filenames within archive are too obscure for local file system.
        # We could somehow adjust them while extracting and here channel back
        # "fixed" up names since they are only to point to the load
        path = opj(self.get_extracted_archive(archive), urllib2.unquote(afile))
        # TODO: make robust
        lgr.log(1, "Verifying that %s exists" % abspath(path))
        assert(exists(path))
        return path

    # TODO -- inject cleanup upon destroy
    # def __del__(self):
    #    self._clean_cache()


class AnnexArchiveCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives also under annex control

    """

    PREFIX = "archive"
    AVAILABILITY = "local"

    def __init__(self, *args, **kwargs):
        super(AnnexArchiveCustomRemote, self).__init__(*args, **kwargs)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._last_url = None # for heuristic to choose among multiple URLs

        # TODO:  urlencode file names in the url while adding/decode upon retrieval

        self._cache_dir = opj(self.path,
                              '.git', 'datalad', 'tmp', 'archives')
        self._cache = None

    def stop(self, *args):
        if self._cache:
            self._cache.clean()
            self._cache = None
        super(AnnexArchiveCustomRemote, self).stop(*args)

    # Should it become a class method really?
    # @classmethod
    def get_file_url(self, archive_file=None, archive_key=None, file=None):
        """Given archive (file or a key) and a file -- compose URL for access
        """
        assert(file is not None)
        if archive_file is not None:
            if archive_key is not None:
                raise ValueError("Provide archive_file or archive_key - not both")
            archive_key = self._get_file_key(archive_file)
        # todo (out, err) = \
        # annex('lookupkey a.tar.gz')
        assert(archive_key is not None)
        file_quoted = urllib2.quote(file)
        return '%s%s/%s' % (self.url_prefix, archive_key, file_quoted.lstrip('/'))

    @property
    def cache(self):
        if self._cache is None:
            self._cache = AnnexArchiveCache(self._cache_dir)
        return self._cache

    # could well be class method
    def _parse_url(self, url):
        key, file = url[len(self.url_prefix):].split('/', 1)
        return key, file

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
        else: # multiple
            # TODO:  utilize cache to check which archives might already be
            #        present in the cache.
            #    Then if not present in the cache -- check which are present
            #    locally and choose that one to use
            if self._last_url and self._last_url in urls:
                return self._last_url
            else:
                return urls[0] # just the first one

    def _get_akey_afile(self, key):
        """Given a key, figure out target archive key, and file within archive
        """
        url = self._get_key_url(key)
        return self._parse_url(url)

    # Protocol implementation
    def req_CHECKURL(self, url):
        """
        The remote replies with one of CHECKURL-FAILURE, CHECKURL-CONTENTS, or CHECKURL-MULTI.
        CHECKURL-CONTENTS Size|UNKNOWN Filename
            Indicates that the requested url has been verified to exist.
            The Size is the size in bytes, or use "UNKNOWN" if the size could not be determined.
            The Filename can be empty (in which case a default is used), or can specify a filename that is suggested to be used for this url.
        CHECKURL-MULTI Url Size|UNKNOWN Filename ...
            Indicates that the requested url has been verified to exist, and contains multiple files, which can each be accessed using their own url.
            Note that since a list is returned, neither the Url nor the Filename can contain spaces.
        CHECKURL-FAILURE
            Indicates that the requested url could not be accessed.
        """
        # TODO:  what about those MULTI and list to be returned?
        #  should we return all filenames or keys within archive?
        #  might be way too many?
        #  only if just archive portion of url is given or the one pointing to specific file?
        lgr.debug("Current directory: %s, url: %s" % (os.getcwd(), url))
        akey, afile = self._parse_url(url)

        # if for testing we want to force getting the archive extracted
        # _ = self.cache.get_extracted_archive(self._get_key_path(akey)) # TEMP
        efile = self.cache.get_file_path(akey, afile)
        if exists(efile):
            size = os.stat(efile).st_size
        else:
            size = 'UNKNOWN'

        # But reply that present only if archive is present
        if exists(self._get_key_path(akey)):
            # FIXME: providing filename causes annex to not even talk to ask
            # upon drop :-/
            self.send("CHECKURL-CONTENTS", size)#, basename(afile))
        else:
            # TODO: theoretically we should first check if key is available from
            # any remote to know if file is available
            self.send("CHECKURL-FAILURE")
        self._last_url = url

    def req_CHECKPRESENT(self, key):
        """Check if copy is available -- TODO: just proxy the call to annex for underlying tarball

        CHECKPRESENT-SUCCESS Key
            Indicates that a key has been positively verified to be present in the remote.
        CHECKPRESENT-FAILURE Key
            Indicates that a key has been positively verified to not be present in the remote.
        CHECKPRESENT-UNKNOWN Key ErrorMsg
            Indicates that it is not currently possible to verify if the key is present in the remote. (Perhaps the remote cannot be contacted.)
        """
        # TODO: so we need to maintain mapping from urls to keys.  Then
        # we could even store the filename within archive
        # Otherwise it is unrealistic to even require to recompute key if we knew the backend etc
        lgr.debug("VERIFYING key %s" % key)
        akey, afile = self._get_akey_afile(key)
        if exists(self._get_key_path(akey)):
            self.send("CHECKPRESENT-SUCCESS", key)
        else:
            # TODO: proxy the same to annex itself to verify check for archive.
            # If archive is no longer available -- then CHECKPRESENT-FAILURE
            self.send("CHECKPRESENT-UNKNOWN", key)

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned if the remote didn't have the key at the point removal was requested.
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        # TODO: proxy query to the underlying tarball under annex that if
        # tarball was removed (not available at all) -- report success,
        # otherwise failure (current the only one)
        key, file = self._get_akey_afile(key)
        if False: #TODO: proxy, checking present of local tarball is not sufficient  not exists(self.get_key_path(key)):
            self.send("REMOVE-SUCCESS", key)
        else:
            self.send("REMOVE-FAILURE", key,
                      "Cannot remove from the present tarball")

    def _transfer(self, cmd, key, path):

        akey, afile = self._get_akey_afile(key)
        akey_path = self._get_key_path(akey)

        if not exists(akey_path):
            # retrieve the key using annex
            try:
                self.runner(["git", "annex", "get", "--key", akey],
                            cwd=self.path)
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
        apath = self.cache.get_extracted_file(akey_path, afile)
        link_file_load(apath, path)
        self.send('TRANSFER-SUCCESS', cmd, key)
        pass


from .main import main as super_main
def main():
    """cmdline entry point"""
    super_main(backend="archive")