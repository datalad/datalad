# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..path import (
    abspath,
    curdir,
    robust_abspath,
)
from ...utils import (
    chpwd,
    rmtree,
)
from ...tests.utils import (
    assert_raises,
    eq_,
    with_tempfile,
)


@with_tempfile(mkdir=True)
def test_robust_abspath(tdir):
    with chpwd(tdir):
        eq_(robust_abspath(curdir), tdir)
        rmtree(tdir)
        assert_raises(OSError, abspath, curdir)
        eq_(robust_abspath(curdir), tdir)
