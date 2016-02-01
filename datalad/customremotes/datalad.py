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
from ..utils import swallow_logs, swallow_outputs
from .base import AnnexCustomRemote
from ..dochelpers import exc_str

from ..downloaders.providers import Providers
from ..downloaders.base import TargetFileAbsent


class DataladAnnexCustomRemote(AnnexCustomRemote):
    """Special custom remote allowing to obtain files from archives

     Archives should also be under annex control.
    """

    SUPPORTED_SCHEMES = ('http', 'https', 's3')

    AVAILABILITY = "global"

    def __init__(self, persistent_cache=True, **kwargs):
        super(DataladAnnexCustomRemote, self).__init__(**kwargs)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._last_url = None  # for heuristic to choose among multiple URLs
        self._providers = Providers.from_config_files()

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

        try:
            with swallow_logs():
                status = self._providers.get_status(url)
            size = str(status.size) if status.size is not None else 'UNKNOWN'
            resp = ["CHECKURL-CONTENTS", size] + \
                   ([status.filename] if status.filename else [])
        except Exception as exc:
            self.debug("Failed to check url %s: %s" % (url, exc_str(exc)))
            resp = ["CHECKURL-FAILURE"]
        self.send(*resp)

    def req_CHECKPRESENT(self, key):
        """Check if copy is available

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
        lgr.debug("VERIFYING key %s" % key)
        resp = None
        for url in self.get_URLS(key):
            # somewhat duplicate of CHECKURL
            try:
                with swallow_logs():
                    status = self._providers.get_status(url)
                if status:  # TODO:  anything specific to check???
                    resp = "CHECKPRESENT-SUCCESS"
                    break
                # TODO:  for CHECKPRESENT-FAILURE we somehow need to figure out that
                # we can connect to that server but that specific url is N/A,
                # probably check the connection etc
            except TargetFileAbsent as exc:
                self.debug("Target url %s file seems to be missing: %s" % (url, exc_str(exc)))
                if not resp:
                    # if it is already marked as UNKNOWN -- let it stay that way
                    # but if not -- we might as well say that we can no longer access it
                    resp = "CHECKPRESENT-FAILURE"
            except Exception as exc:
                resp = "CHECKPRESENT-UNKNOWN"
                self.debug("Failed to check status of url %s: %s" % (url, exc_str(exc)))
        if resp is None:
            resp = "CHECKPRESENT-UNKNOWN"
        self.send(resp, key)

    def req_REMOVE(self, key):
        """
        REMOVE-SUCCESS Key
            Indicates the key has been removed from the remote. May be returned
            if the remote didn't have the key at the point removal was requested
        REMOVE-FAILURE Key ErrorMsg
            Indicates that the key was unable to be removed from the remote.
        """
        self.send("REMOVE-FAILURE", key,
                  "Removal of content from urls is not possible")

    def req_WHEREIS(self, key):
        """
        WHEREIS-SUCCESS String
            Indicates a location of a key. Typically an url, the string can be anything
            that it makes sense to display to the user about content stored in the special
            remote.
        WHEREIS-FAILURE
            Indicates that no location is known for a key.
        """
        # All that information is stored in annex itself, we can't complement anything
        self.send("WHEREIS-FAILURE")

    def _transfer(self, cmd, key, path):

        # TODO: We might want that one to be a generator so we do not bother requesting
        # all possible urls at once from annex.
        urls = self.get_URLS(key)

        if self._last_url in urls:
            # place it first among candidates... some kind of a heuristic
            urls.pop(self._last_url)
            urls = [self._last_url] + urls

        # TODO: priorities etc depending on previous experience or settings

        for url in urls:
            try:
                downloaded_path = self._providers.download(url, path=path, overwrite=True)
                lgr.info("Succesfully downloaded %s into %s" % (url, downloaded_path))
                self.send('TRANSFER-SUCCESS', cmd, key)
                return
            except Exception as exc:
                self.debug("Failed to download url %s for key %s: %s" % (url, key, exc_str(exc)))

        self.send('TRANSFER-FAILURE', cmd, key,
                  "Failed to download from any of %d locations" % len(urls))


from .main import main as super_main
def main():
    """cmdline entry point"""
    super_main(backend="datalad")
