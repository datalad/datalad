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

from collections import Counter
import logging
from urllib.parse import urlparse

from annexremote import (
    RemoteError,
    SpecialRemote,
    UnsupportedRequest,
)
from datalad.downloaders.providers import Providers
from datalad.support.exceptions import (
    CapturedException,
    TargetFileAbsent,
)
lgr = logging.getLogger('datalad.customremotes.datalad')


class DataladAnnexCustomRemote(SpecialRemote):
    """Special custom remote allowing to obtain files from archives

     Archives should also be under annex control.
    """

    SUPPORTED_SCHEMES = ('http', 'https', 's3', 'shub')

    def __init__(self, annex, **kwargs):
        # OPT: a counter to increment upon successful encounter of the scheme
        # (ATM only in gen_URLS but later could also be used in other requests).
        # This would allow to consider schemes in order of decreasing success instead
        # of arbitrary hardcoded order
        self._scheme_hits = Counter({s: 0 for s in self.SUPPORTED_SCHEMES})

        super().__init__(annex)
        # annex requests load by KEY not but URL which it originally asked
        # about.  So for a key we might get back multiple URLs and as a
        # heuristic let's use the most recently asked one

        self._providers = Providers.from_config_files()

        # TODO self.info = {}, self.configs = {}

    # Helper methods
    def gen_URLS(self, key):
        """Yield URL(s) associated with a key, and keep stats on protocols."""
        nurls = 0
        for scheme, _ in self._scheme_hits.most_common():
            scheme_ = scheme + ":"
            scheme_urls = self.annex.geturls(key, scheme_)
            if scheme_urls:
                # note: generator would cease to exist thus not asking
                # for URLs for other schemes if this scheme is good enough
                self._scheme_hits[scheme] += 1
                for url in scheme_urls:
                    yield url
        self.annex.debug("Got %d URL(s) for key %s", nurls, key)

    # Protocol implementation
    def initremote(self):
        pass

    def prepare(self):
        pass

    def transfer_retrieve(self, key, file):
        lgr.debug("RETRIEVE key %s into/from %s", key, file)  # was INFO level

        urls = []

        # TODO: priorities etc depending on previous experience or settings
        for url in self.gen_URLS(key):
            urls.append(url)
            try:
                downloaded_path = self._providers.download(
                    url, path=file, overwrite=True
                )
                lgr.info("Successfully downloaded %s into %s", url, downloaded_path)
                return
            except Exception as exc:
                ce = CapturedException(exc)
                self.annex.debug("Failed to download url %s for key %s: %s"
                                 % (url, key, ce))
        raise RemoteError(
            f"Failed to download from any of {len(urls)} locations")

    def transfer_store(self, key, local_file):
        raise UnsupportedRequest('This special remote cannot store content')

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
        lgr.debug("VERIFYING key %s", key)
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

    def remove(self, key):
        raise RemoteError("Removal of content from urls is not possible")

    def whereis(self, key):
        # All that information is stored in annex itself,
        # we can't complement anything
        raise RemoteError()


def main():
    """cmdline entry point"""
    from annexremote import Master
    master = Master()
    remote = DataladAnnexCustomRemote(master)
    master.LinkRemote(remote)
    master.Listen()
