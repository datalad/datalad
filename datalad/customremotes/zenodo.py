# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Custom remote to upload files directly into zenodo using it as a regular special git-annex remote"""

__docformat__ = 'restructuredtext'

import logging
lgr = logging.getLogger('datalad.customremotes.datalad')

from ..utils import swallow_logs
from .base import AnnexCustomRemote
from ..dochelpers import exc_str

from ..downloaders.providers import Providers
from ..downloaders.base import TargetFileAbsent
from .main import main as super_main


class ZenodoAnnexCustomRemote(AnnexCustomRemote):
    """TODO
    """

    AVAILABILITY = "global"
    SUPPORTED_SCHEMES = ()

    # def __init__(self, **kwargs):
    #     super(ZenodoAnnexCustomRemote, self).__init__(**kwargs)
    #     # annex requests load by KEY not but URL which it originally asked
    #     # about.  So for a key we might get back multiple URLs and as a
    #     # heuristic let's use the most recently asked one
    #
    #     self._last_url = None  # for heuristic to choose among multiple URLs
    #     self._providers = Providers.from_config_files()

    #
    # Helper methods

    # Protocol implementation
    def _transfer(self, cmd, key, file):
        import pdb; pdb.set_trace()
        raise NotImplementedError()

    def _initremote(self, *args):
        """Custom initialization of the special custom remote."""
        import pdb; pdb.set_trace()
        pass

    def _prepare(self, *args):
        """Prepare special custom remote."""
        import pdb; pdb.set_trace()
        pass

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
                downloaded_path = self._providers.download(
                    url, path=path, overwrite=True
                )
                lgr.info("Successfully downloaded %s into %s" % (url, downloaded_path))
                self.send('TRANSFER-SUCCESS', cmd, key)
                return
            except Exception as exc:
                self.debug("Failed to download url %s for key %s: %s" % (url, key, exc_str(exc)))

        self.send('TRANSFER-FAILURE', cmd, key,
                  "Failed to download from any of %d locations" % len(urls))


def main():
    """cmdline entry point"""
    super_main(backend="zenodo")
