# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Result utility tests

"""

from datalad.interface.results import (
    annexjson2result,
)
from datalad.distribution.dataset import Dataset

from datalad.tests.utils import (
    eq_,
    with_tempfile,
)


@ with_tempfile
def test_annexjson2result(dspath):
    # no explicit success means 'error'
    eq_(annexjson2result(dict(), None),
        dict(status='error'))
    # unrecognized -> error
    eq_(annexjson2result(dict(success='random'), None),
        dict(status='error'))
    # success is possible ;-)
    eq_(annexjson2result(dict(success=True), None),
        dict(status='ok'))

    # path handling
    # needs a dataset
    ds = Dataset(dspath)
    eq_(annexjson2result(dict(file='file1'), ds),
        dict(status='error',
             path=str(ds.pathobj / 'file1')))
    # on all platforms, paths are reported in platform conventions
    # although git-annex reports in posix
    eq_(annexjson2result(dict(file='dir1/file1'), ds),
        dict(status='error',
             path=str(ds.pathobj / 'dir1' / 'file1')))
