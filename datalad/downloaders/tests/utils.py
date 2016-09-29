# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Downloader tests helper utils"""

from unittest import SkipTest

from datalad.downloaders.providers import Providers


def get_test_providers(url=None, reload=False):
    """Return reusable instance of our global providers + verify credentials for url"""
    _test_providers = Providers.from_config_files(reload=reload)
    if url is not None:
        # check if we have credentials for the url
        provider = _test_providers.get_provider(url, only_nondefault=True)
        if provider is None or provider.credential is None:
            # no registered provider, or no credential needed,must be all kosher to access
            pass
        elif not provider.credential.is_known:
            raise SkipTest("This test requires known credentials for %s" % provider.credential.name)
    return _test_providers
get_test_providers.__test__ = False
