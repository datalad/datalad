# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DataLad aims to expose (scientific) data available online as a unified data
distribution with the convenience of git-annex repositories as a backend."""

from .version import __version__

import datalad.log

# be friendly on systems with ancient numpy -- no tests, but at least
# importable
try:
    from numpy.testing import Tester
    test = Tester().test
    bench = Tester().bench
    del Tester
except ImportError:
    def test(*args, **kwargs): raise RuntimeError('Need numpy >= 1.2 for datalad.tests()')
