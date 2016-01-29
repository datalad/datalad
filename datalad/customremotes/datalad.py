# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Universal custom remote to support anything our downloaders support"""

__docformat__ = 'restructuredtext'

import os
import re
from os.path import exists, join as opj, basename, abspath

from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote

import logging
lgr = logging.getLogger('datalad.customremotes.datalad')

from ..cmd import link_file_load, Runner
from ..support.exceptions import CommandError
from ..utils import getpwd
from .base import AnnexCustomRemote


class DataladAnnexCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives

     Archives should also be under annex control.
    """

    SUPPORTED_SCHEMES = ('http', 'https', 's3')

    AVAILABILITY = "global"

    # def __init__(self, persistent_cache=True, **kwargs):
    #     super(DataladAnnexCustomRemote, self).__init__(**kwargs)
    #     # annex requests load by KEY not but URL which it originally asked
    #     # about.  So for a key we might get back multiple URLs and as a
    #     # heuristic let's use the most recently asked one
    #
    #     self._last_url = None  # for heuristic to choose among multiple URLs

    #
    # Helper methods

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
        akey_fpath = self.get_contentlocation(akey)  #, relative_to_top=True))
        if akey_fpath:
            akey_path = opj(self.path, akey_fpath)

            # if for testing we want to force getting the archive extracted
            # _ = self.cache.assure_extracted(self._get_key_path(akey)) # TEMP
            efile = self.cache[akey_path].get_extracted_filename(afile)

            if size is None and exists(efile):
                size = os.stat(efile).st_size

            if size is None:
                size = 'UNKNOWN'

            # FIXME: providing filename causes annex to not even talk to ask
            # upon drop :-/
            self.send("CHECKURL-CONTENTS", size)  #, basename(afile))
        else:
            # TODO: theoretically we should first check if key is available from
            # any remote to know if file is available
            self.send("CHECKURL-FAILURE")
        # self._last_url = url

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
        if self.get_contentlocation(akey):
            self.send("CHECKPRESENT-SUCCESS", key)
        else:
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
        akey_fpath = self.get_contentlocation(akey)
        if akey_fpath:  # present
            akey_path = opj(self.path, akey_fpath)
        else:
            # TODO: make it more stringent?
            # Command could have fail to run if key was not present locally yet
            # Thus retrieve the key using annex
            try:
                # TODO: we need to report user somehow about this happening and progress on the download
                self.runner(["git-annex", "get", "--key", akey],
                            cwd=self.path, expect_stderr=True)
            except Exception as e:
                #from celery.contrib import rdb
                #rdb.set_trace()
                self.error("Failed to fetch {akey} containing {key}: {e}".format(**locals()))
                return
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


from .main import main as super_main
def main():
    """cmdline entry point"""
    super_main(backend="datalad")
