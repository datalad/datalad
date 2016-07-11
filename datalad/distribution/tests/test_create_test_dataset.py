# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create testdataset helpers

"""
from glob import glob
from os.path import join as opj

from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_
from datalad.tests.utils import ok_clean_git
from datalad.utils import swallow_logs
from datalad.utils import chpwd
from datalad.distribution.create_test_dataset import _parse_spec

from nose.tools import eq_


@with_tempfile(mkdir=True)
def test_create(outdir):
    from datalad.api import create
    assert_raises(ValueError, create, outdir, description='Precious data', no_annex=True)


def test_parse_spec():
    eq_(_parse_spec('0/3/-1'), [(0, 0), (3, 3), (0, 1)])
    eq_(_parse_spec('4-10'), [(4, 10)])


def test_create_test_dataset():
    # rudimentary smoke test
    from datalad.api import create_test_dataset
    with swallow_logs():
        dss = create_test_dataset(spec='2/1-2')
    ok_(4 <= len(dss) <= 6)  # at least four - two on top level, 1 in each
    for ds in dss:
        ok_clean_git(ds, annex=False)  # soem of them are annex but we just don't check
        ok_(len(glob(opj(ds, 'file*'))))


@with_tempfile(mkdir=True)
def test_create_test_dataset_new_relpath(topdir):
    from datalad.api import create_test_dataset
    with swallow_logs(), chpwd(topdir):
        dss = create_test_dataset('testds', spec='1')
    eq_(len(dss), 1)
