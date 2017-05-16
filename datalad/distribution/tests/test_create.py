# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create action

"""

import os
from os.path import join as opj

from ..dataset import Dataset
from datalad.api import create
from datalad.api import uninstall
from datalad.utils import chpwd
from datalad.utils import rmtree
from datalad.cmd import Runner
from datalad.support.exceptions import CommandError

from datalad.tests.utils import with_tempfile
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_equal
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import with_tree


_dataset_hierarchy_template = {
    'origin': {
        'file1': '',
        'sub': {
            'file2': 'file2',
            'subsub': {
                'file3': 'file3'}}}}


@with_tempfile(mkdir=True)
@with_tempfile
def test_create_raises(path, outside_path):

    ds = Dataset(path)
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
    assert_raises(ValueError, ds.create, outside_path)

    # create a sub:
    ds.create('sub')
    # fail when doing it again without `force`:
    assert_raises(ValueError, ds.create, 'sub')


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
    ds.create(description="funny", native_metadata_type=['bim', 'bam', 'bum'],
              shared_access='world')
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=True)

    # check default backend
    eq_(ds.config.get("annex.backends"), 'MD5E')
    eq_(ds.config.get("core.sharedrepository"), '2')
    runner = Runner()
    # check description in `info`
    cmd = ['git-annex', 'info']
    cmlout = runner.run(cmd, cwd=path)
    assert_in('funny [here]', cmlout[0])
    # check datset ID
    eq_(ds.config.get_value('datalad.dataset', 'id'),
        ds.id)
    assert_equal(
        ds.config.get_value('datalad.metadata', 'nativetype'),
        ('bim', 'bam', 'bum'))


@with_tempfile
def test_create_sub(path):

    ds = Dataset(path)
    ds.create()

    # 1. create sub and add to super:
    subds = ds.create("some/what/deeper")
    ok_(isinstance(subds, Dataset))
    ok_(subds.is_installed())
    ok_clean_git(subds.path, annex=True)

    # subdataset is known to superdataset:
    assert_in("some/what/deeper", ds.get_subdatasets())
    # and was committed:
    ok_clean_git(ds.path)

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
    subds3 = ds.create("third", no_annex=True)
    ok_(isinstance(subds3, Dataset))
    ok_(subds3.is_installed())
    ok_clean_git(subds3.path, annex=False)
    assert_in("third", ds.get_subdatasets())


@with_tree(tree=_dataset_hierarchy_template)
def test_create_subdataset_hierarchy_from_top(path):
    # how it would look like to overlay a subdataset hierarchy onto
    # an existing directory tree
    ds = Dataset(opj(path, 'origin')).create(force=True)
    # we got a dataset ....
    ok_(ds.is_installed())
    # ... but it has untracked content
    ok_(ds.repo.dirty)
    subds = ds.create('sub', force=True)
    ok_(subds.is_installed())
    ok_(subds.repo.dirty)
    subsubds = subds.create('subsub', force=True)
    ok_(subsubds.is_installed())
    ok_(subsubds.repo.dirty)
    ds.save(recursive=True, all_updated=True)
    ok_clean_git(ds.path)
    ok_(ds.id != subds.id != subsubds.id)


@with_tempfile
def test_nested_create(path):
    # to document some more organic usage pattern
    ds = Dataset(path).create()
    ok_clean_git(ds.path)
    lvl2relpath = opj('lvl1', 'lvl2')
    lvl2path = opj(ds.path, lvl2relpath)
    os.makedirs(lvl2path)
    os.makedirs(opj(ds.path, 'lvl1', 'empty'))
    with open(opj(lvl2path, 'file'), 'w') as f:
        f.write('some')
    ok_(ds.save(all_updated=True))
    # later create subdataset in a fresh dir
    subds1 = ds.create(opj('lvl1', 'subds'))
    ok_clean_git(ds.path)
    eq_(ds.get_subdatasets(), [opj('lvl1', 'subds')])
    # later create subdataset in an existing empty dir
    subds2 = ds.create(opj('lvl1', 'empty'))
    ok_clean_git(ds.path)
    # later try to wrap existing content into a new subdataset
    # but that won't work
    assert_raises(ValueError, ds.create, lvl2relpath)
    # even with force, as to do this properly complicated surgery would need to
    # take place
    assert_raises(CommandError, ds.create, lvl2relpath, force=True)
    # only way to make it work is to unannex the content upfront
    ds.repo._run_annex_command('unannex', annex_options=[opj(lvl2relpath, 'file')])
    # nothing to save, git-annex commits the unannex itself
    ok_(not ds.save())
    # still nothing without force
    # "err='lvl1/lvl2' already exists in the index"
    assert_raises(ValueError, ds.create, lvl2relpath)
    # XXX even force doesn't help, because (I assume) GitPython doesn't update
    # its representation of the Git index properly
    ds.create(lvl2relpath, force=True)
    assert_in(lvl2relpath, ds.get_subdatasets())


# Imported from #1016
@with_tree({'ds2': {'file1.txt': 'some'}})
def test_saving_prior(topdir):
    # the problem is that we might be saving what is actually needed to be
    # "created"

    # we would like to place this structure into a hierarchy of two datasets
    # so we create first top one
    ds1 = create(topdir, force=True)
    # and everything is ok, stuff is not added BUT ds1 will be considered dirty
    ok_(ds1.repo.dirty)
    # And then we would like to initiate a sub1 subdataset
    ds2 = create('ds2', dataset=ds1, force=True)
    # But what will happen is file1.txt under ds2 would get committed first into
    # ds1, and then the whole procedure actually crashes since because ds2/file1.txt
    # is committed -- ds2 is already known to git and it just pukes with a bit
    # confusing    'ds2' already exists in the index
    assert_in('ds2', ds1.get_subdatasets())
