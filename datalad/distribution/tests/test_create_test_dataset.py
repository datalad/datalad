# ex: set sts=4 ts=4 sw=4 et:
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

from datalad.core.local.repo import repo_from_path
from datalad.distribution.create_test_dataset import _parse_spec
from datalad.tests.utils_pytest import (
    assert_raises,
    assert_repo_status,
    eq_,
    ok_,
    with_tempfile,
)
from datalad.utils import (
    chpwd,
    swallow_logs,
    swallow_outputs,
)


@with_tempfile(mkdir=True)
def test_create(outdir=None):
    from datalad.api import create
    assert_raises(ValueError, create, outdir, description='Precious data', annex=False)


def test_parse_spec():
    eq_(_parse_spec('0/3/-1'), [(0, 0), (3, 3), (0, 1)])
    eq_(_parse_spec('4-10'), [(4, 10)])
    eq_(_parse_spec(''), [])


def test_create_test_dataset():
    # rudimentary smoke test
    from datalad.api import create_test_dataset
    with swallow_logs(), swallow_outputs():
        dss = create_test_dataset(spec='2/1-2')
    ok_(5 <= len(dss) <= 7)  # at least five - 1 top, two on top level, 1 in each
    for ds in dss:
        assert_repo_status(ds, annex=None)  # some of them are annex but we just don't check
        ok_(len(glob(opj(ds, 'file*'))))


def test_create_1test_dataset():
    # and just a single dataset
    from datalad.api import create_test_dataset
    with swallow_outputs():
        dss = create_test_dataset()
    eq_(len(dss), 1)
    assert_repo_status(dss[0], annex=False)


@with_tempfile(mkdir=True)
def test_new_relpath(topdir=None):
    from datalad.api import create_test_dataset
    with swallow_logs(), chpwd(topdir), swallow_outputs():
        dss = create_test_dataset('testds', spec='1')
    eq_(dss[0], opj(topdir, 'testds'))
    eq_(len(dss), 2)  # 1 top + 1 sub-dataset as demanded
    for ds in dss:
        assert_repo_status(ds, annex=False)


@with_tempfile()
def test_hierarchy(topdir=None):
    # GH 1178
    from datalad.api import create_test_dataset
    with swallow_logs(), swallow_outputs():
        dss = create_test_dataset(topdir, spec='1/1')

    eq_(len(dss), 3)
    eq_(dss[0], topdir)
    for ids, ds in enumerate(dss):
        assert_repo_status(ds, annex=False)
        # each one should have 2 commits (but the last one)-- one for file and
        # another one for sub-dataset
        repo = repo_from_path(ds)
        if not hasattr(repo, 'is_managed_branch') or not repo.is_managed_branch():
            eq_(len(list(repo.get_branch_commits_())), 1 + int(ids < 2))
