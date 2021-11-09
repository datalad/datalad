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

import logging
from urllib.parse import urlparse

from annexremote import RemoteError

from datalad.downloaders.providers import Providers
from datalad.support.exceptions import (
    CapturedException,
    TargetFileAbsent,
)

from .base import AnnexCustomRemote

lgr = logging.getLogger('datalad.customremotes.datalad')


class DataladAnnexCustomRemote(AnnexCustomRemote):
    """git-annex special-remote frontend for DataLad's downloader facility
    """

    SUPPORTED_SCHEMES = ('http', 'https', 's3', 'shub')

    def __init__(self, annex, **kwargs):
        super().__init__(annex)

        self._providers = Providers.from_config_files()

    def transfer_retrieve(self, key, file):
        urls = []
        # TODO: priorities etc depending on previous experience or settings
        for url in self.gen_URLS(key):
            urls.append(url)
            try:
                downloaded_path = self._providers.download(
                    url, path=file, overwrite=True
                )
                assert(downloaded_path == file)
                return
            except Exception as exc:
                ce = CapturedException(exc)
                self.annex.debug("Failed to download url %s for key %s: %s"
                                 % (url, key, ce))
        raise RemoteError(
            f"Failed to download from any of {len(urls)} locations")

    def checkurl(self, url):
        try:
            status = self._providers.get_status(url)
            props = dict(filename=status.filename, url=url)
            if status.size is not None:
                props['size'] = status.size
            return [props]
        except Exception as exc:
            ce = CapturedException(exc)
            self.annex.debug("Failed to check url %s: %s" % (url, ce))
            return False

    def checkpresent(self, key):
        resp = None
        for url in self.gen_URLS(key):
            # somewhat duplicate of CHECKURL
            try:
                status = self._providers.get_status(url)
                if status:  # TODO:  anything specific to check???
                    return True
                # TODO:  for CHECKPRESENT-FAILURE we somehow need to figure out that
                # we can connect to that server but that specific url is N/A,
                # probably check the connection etc
            except TargetFileAbsent as exc:
                ce = CapturedException(exc)
                self.annex.debug("Target url %s file seems to be missing: %s" % (url, ce))
                if not resp:
                    # if it is already marked as UNKNOWN -- let it stay that way
                    # but if not -- we might as well say that we can no longer access it
                    return False
            except Exception as exc:
                ce = CapturedException(exc)
                self.annex.debug("Failed to check status of url %s: %s" % (url, ce))
        if resp is None:
            raise RemoteError(f'Could not determine presence of key {key}')
        else:
            return False

    def claimurl(self, url):
        scheme = urlparse(url).scheme
        if scheme in self.SUPPORTED_SCHEMES:
            return True
        else:
            return False


def main():
    """cmdline entry point"""
    from annexremote import Master
    master = Master()
    remote = DataladAnnexCustomRemote(master)
    master.LinkRemote(remote)
    master.Listen()
