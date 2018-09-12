# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
from ..path import (
    abspath,
    curdir,
    robust_abspath,
)
from ...dochelpers import exc_str
from ...utils import (
    chpwd,
    rmtree,
)
from ...tests.utils import (
    assert_raises,
    eq_,
    with_tempfile,
    SkipTest,
)


@with_tempfile(mkdir=True)
def test_robust_abspath(tdir):
    with chpwd(tdir):
        eq_(robust_abspath(curdir), tdir)
        try:
            if os.environ.get('DATALAD_ASSERT_NO_OPEN_FILES'):
                raise Exception("cannot test under such pressure")
            rmtree(tdir)
        except Exception as exc:
            # probably windows or above exception
            raise SkipTest(
                "Cannot test in current environment: %s" % exc_str(exc))

        assert_raises(OSError, abspath, curdir)
        eq_(robust_abspath(curdir), tdir)
