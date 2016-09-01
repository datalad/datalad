# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create action

"""


from os.path import join as opj

from ..dataset import Dataset
from datalad.api import create
from datalad.utils import chpwd
from datalad.cmd import Runner

from datalad.tests.utils import with_tempfile
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_clean_git


@with_tempfile(mkdir=True)
@with_tempfile
def test_create_raises(path, outside_path):

    ds = Dataset(path)
    # no superdataset to add to:
    assert_raises(ValueError, ds.create, add_to_super=True)
    # incompatible arguments (annex only):
    assert_raises(ValueError, ds.create, no_annex=True, description='some')
    assert_raises(ValueError, ds.create, no_annex=True, annex_opts=['some'])
    assert_raises(ValueError, ds.create, no_annex=True, annex_init_opts=['some'])

    with open(opj(path, "somefile.tst"), 'w') as f:
        f.write("some")
    # non-empty without `force`:
    assert_raises(ValueError, ds.create, force=False)
    # non-empty with `force`:
    ds.create(force=True)
    # create sub outside of super:
    assert_raises(ValueError, ds.create_subdataset, outside_path)

    # create a sub:
    ds.create_subdataset('sub')
    # fail when doing it again without `force`:
    assert_raises(ValueError, ds.create_subdataset, 'sub')


@with_tempfile
@with_tempfile
def test_create_curdir(path, path2):
    with chpwd(path, mkdir=True):
        create()
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=True)

    with chpwd(path2, mkdir=True):
        create(no_annex=True)
    ds = Dataset(path2)
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=False)


@with_tempfile
def test_create(path):
    ds = Dataset(path)
    ds.create(description="funny")
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=True)

    # check default backend
    eq_(ds.repo.repo.config_reader().get_value("annex", "backends"),
        'MD5E')
    runner = Runner()
    # check description in `info`
    cmd = ['git-annex', 'info']
    cmlout = runner.run(cmd, cwd=path)
    assert_in('funny [here]', cmlout[0])


@with_tempfile
def test_create_sub(path):

    ds = Dataset(path)
    ds.create()

    # 1. create sub and add to super:
    subds = Dataset(opj(path, "some/what/deeper")).create(add_to_super=True)
    ok_(isinstance(subds, Dataset))
    ok_(subds.is_installed())
    ok_clean_git(subds.path, annex=True)

    # subdataset is known to superdataset:
    assert_in("some/what/deeper", ds.get_subdatasets())
    # but wasn't committed:
    ok_(ds.repo.dirty)

    # subds finds superdataset
    ok_(subds.get_superdataset() == ds)

    # 2. create sub without adding to super:
    subds2 = Dataset(opj(path, "someother")).create()
    ok_(isinstance(subds2, Dataset))
    ok_(subds2.is_installed())
    ok_clean_git(subds2.path, annex=True)

    # unknown to superdataset:
    assert_not_in("someother", ds.get_subdatasets())

    # 3. create sub via super:
    subds3 = ds.create_subdataset("third", no_annex=True)
    ok_(isinstance(subds3, Dataset))
    ok_(subds3.is_installed())
    ok_clean_git(subds3.path, annex=False)
    assert_in("third", ds.get_subdatasets())
