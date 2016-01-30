# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Downlaoder tests helper utils"""

from unittest import SkipTest

from datalad.downloaders import Providers

_test_providers = None

def get_test_providers(url=None):
    """Return reusable instance of our global providers"""
    global _test_providers
    if not _test_providers:
        _test_providers = Providers.from_config_files()
    if url is not None:
        # check if we have credentials for the url
        provider = _test_providers.get_provider(url)
        if not provider.credential.is_known:
            raise SkipTest("This test requires known credentials for %s" % provider.credential.name)
    return _test_providers
get_test_providers.__test__ = False