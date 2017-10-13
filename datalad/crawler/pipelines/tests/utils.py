# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ....support.annexrepo import AnnexRepo

from ....utils import chpwd
from ....utils import swallow_logs
from ....tests.utils import ok_
from ....utils import make_tempfile

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


def _test_smoke_pipelines(func, args, kwargs={}):
    with make_tempfile(mkdir=True) as tmpdir:
        AnnexRepo(tmpdir, create=True)
        with chpwd(tmpdir):
            with swallow_logs():
                for p in [func(*args, **kwargs)]:
                    ok_(len(p) > 1)
