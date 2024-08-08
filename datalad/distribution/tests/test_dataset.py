# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test Dataset class

"""

import os
import os.path as op
from os.path import abspath
from os.path import join as opj
from os.path import (
    lexists,
    relpath,
)

import pytest

import datalad.utils as ut
from datalad import cfg as dl_cfg
from datalad.api import (
    clone,
    create,
    get,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import NoDatasetFound
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    SkipTest,
    assert_equal,
    assert_false,
    assert_is,
    assert_is_instance,
    assert_is_none,
    assert_is_not,
    assert_is_not_none,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_true,
    eq_,
    known_failure_windows,
    ok_,
    swallow_logs,
    with_tempfile,
)
from datalad.utils import (
    Path,
    _path_,
    chpwd,
    on_windows,
    rmtree,
)

from ..dataset import (
    Dataset,
    EnsureDataset,
    require_dataset,
    resolve_path,
)


def test_EnsureDataset():

    c = EnsureDataset()

    # fails with anything else than a string or a Dataset:
    assert_raises(ValueError, c, 1)
    assert_raises(ValueError, c, ['a', 'list'])
    assert_raises(ValueError, c, (1, 2, 3))
    assert_raises(ValueError, c, {"what": "ever"})

    # let's a Dataset instance pass, but leaves a path untouched
    for test_path in [opj("some", "path"), Path("some") / "path"]:
        ok_(isinstance(c(test_path), type(test_path)))
        ok_(isinstance(Dataset(test_path), Dataset))

    # Note: Ensuring that string is valid path is not
    # part of the constraint itself, so not explicitly tested here.


# TODO: test remember/recall more extensive?

@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_is_installed(src=None, path=None):
    ca = dict(result_renderer='disabled')
    # a remote dataset with a subdataset underneath
    origds = Dataset(src).create(**ca)
    _ = origds.create('subm 1', **ca)

    ds = Dataset(path)
    assert_false(ds.is_installed())

    # get a clone:
    clone(src, path, **ca)
    ok_(ds.is_installed())
    # submodule still not installed:
    subds = Dataset(ds.pathobj / 'subm 1')
    assert_false(subds.is_installed())
    # We must not be able to create a new repository under a known
    # subdataset path.
    # Note: Unfortunately we would still be able to generate it under
    # subdirectory within submodule, e.g. `subm 1/subdir` but that is
    # not checked here. `create` provides that protection though.
    res = subds.create(on_failure='ignore',
                       return_type='list',
                       result_filter=None,
                       result_xfm=None,
                       **ca)
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, status='error', path=subds.path,
        message=('collision with %s (dataset) in dataset %s',
                 subds.path, ds.path))
    # get the submodule
    with chpwd(ds.path):
        get('subm 1', **ca)
    ok_(subds.is_installed())
    # wipe it out
    rmtree(ds.path)
    assert_false(ds.is_installed())


@with_tempfile(mkdir=True)
def test_dataset_constructor(path=None):
    # dataset needs a path
    assert_raises(TypeError, Dataset)
    assert_raises(ValueError, Dataset, None)
    with chpwd(path):
        assert_raises(NoDatasetFound, Dataset, '^.')
        assert_raises(NoDatasetFound, Dataset, '^')
    dsabs = Dataset(path)
    # always abspath
    ok_(os.path.isabs(dsabs.path))
    eq_(path, dsabs.path)
    # no repo
    eq_(dsabs.repo, None)
    # same result when executed in that path and using relative paths
    with chpwd(path):
        dsrel = Dataset('.')
        eq_(dsrel.path, dsabs.path)
        # no repo either, despite directory existing now
        eq_(dsrel.repo, None)


@with_tempfile(mkdir=True)
def test_repo_cache(path=None):
    ds = Dataset(path)
    # none by default
    eq_(ds.repo, None)
    # make Git repo manually
    git = GitRepo(path=path, create=True)
    repo = ds.repo
    # got one
    assert_false(repo is None)
    # stays that one
    assert_true(ds.repo is repo)
    # now turn into an annex
    annex = AnnexRepo(path=path, create=True)
    # repo instance must change
    assert_false(ds.repo is repo)
    assert_true(isinstance(ds.repo, AnnexRepo))


@with_tempfile(mkdir=True)
def test_subdatasets(path=None):
    # from scratch
    ds = Dataset(path)
    assert_false(ds.is_installed())
    assert_raises(ValueError, ds.subdatasets)
    ds = ds.create()
    assert_true(ds.is_installed())
    eq_(ds.subdatasets(), [])
    # create some file and commit it
    open(os.path.join(ds.path, 'test'), 'w').write('some')
    ds.save(path='test', message="Hello!", version_tag=1)
    assert_true(ds.is_installed())
    # Assuming that tmp location was not under a super-dataset
    eq_(ds.get_superdataset(), None)
    eq_(ds.get_superdataset(topmost=True), ds)

    # add itself as a subdataset (crazy, isn't it?)
    subds = ds.install('subds', source=path,
        result_xfm='datasets', return_type='item-or-list')
    assert_true(subds.is_installed())
    eq_(subds.get_superdataset(), ds)
    eq_(subds.get_superdataset(topmost=True), ds)

    subdss = ds.subdatasets()
    eq_(len(subdss), 1)
    eq_(subds.path, ds.subdatasets(result_xfm='paths')[0])
    eq_(subdss, ds.subdatasets(recursive=True))
    eq_(subdss, ds.subdatasets(state='present'))
    ds.save(message="with subds", version_tag=2)
    ds.recall_state(1)
    assert_true(ds.is_installed())
    eq_(ds.subdatasets(), [])

    # very nested subdataset to test topmost
    subsubds = subds.install(
        _path_('d1/subds'), source=path,
        result_xfm='datasets', return_type='item-or-list')
    assert_true(subsubds.is_installed())
    eq_(subsubds.get_superdataset(), subds)
    # by default, it will only report a subperdataset that actually
    # has the queries dataset as a registered true subdataset
    eq_(subsubds.get_superdataset(topmost=True), subds)
    # by we can also ask for a dataset that is merely above
    eq_(subsubds.get_superdataset(topmost=True, registered_only=False), ds)

    # verify that '^' alias would work
    with chpwd(subsubds.path):
        dstop = Dataset('^')
        eq_(dstop, subds)
        # and while in the dataset we still can resolve into central one
        dscentral = Dataset('///')
        eq_(dscentral.path,
            dl_cfg.obtain('datalad.locations.default-dataset'))

    with chpwd(ds.path):
        dstop = Dataset('^')
        eq_(dstop, ds)

    # TODO actual submodule checkout is still there

    # Test ^. (the dataset for curdir) shortcut
    # At the top should point to the top
    with chpwd(ds.path):
        dstop = Dataset('^.')
        eq_(dstop, ds)

    # and still does within subdir
    os.mkdir(opj(ds.path, 'subdir'))
    with chpwd(opj(ds.path, 'subdir')):
        dstop = Dataset('^.')
        eq_(dstop, ds)

    # within submodule will point to submodule
    with chpwd(subsubds.path):
        dstop = Dataset('^.')
        eq_(dstop, subsubds)


@with_tempfile(mkdir=True)
def test_hat_dataset_more(path=None):
    # from scratch
    ds = Dataset(path).create()
    # add itself as a subdataset (crazy, isn't it?)
    subds = ds.install(
        'subds', source=path,
        result_xfm='datasets', return_type='item-or-list')
    # must find its way all the way up from an untracked dir in a subsubds
    untracked_subdir = op.join(subds.path, 'subdir')
    os.makedirs(untracked_subdir)
    with chpwd(untracked_subdir):
        eq_(Dataset('^'), ds)


@pytest.mark.parametrize("ds_path", ["simple-path", OBSCURE_FILENAME])
@with_tempfile(mkdir=True)
def test_require_dataset(topdir=None, *, ds_path):
    path = opj(topdir, ds_path)
    os.mkdir(path)
    with chpwd(path):
        assert_raises(
            NoDatasetFound,
            require_dataset,
            None)
        create('.')
        # in this folder by default
        assert_equal(
            require_dataset(None).path,
            path)

        assert_equal(
            require_dataset('some', check_installed=False).path,
            abspath('some'))
        assert_raises(
            NoDatasetFound,
            require_dataset,
            'some',
            check_installed=True)


@with_tempfile(mkdir=True)
def test_dataset_id(path=None):

    ds = Dataset(path)
    assert_equal(ds.id, None)
    ds.create()
    dsorigid = ds.id
    # ID is always a UUID
    assert_equal(ds.id.count('-'), 4)
    assert_equal(len(ds.id), 36)

    # Ben: The following part of the test is concerned with creating new objects
    #      and therefore used to reset the flyweight dict while keeping a ref to
    #      the old object for comparison etc. This is ugly and in parts
    #      retesting what is already tested in `test_Dataset_flyweight`. No need
    #      for that. If we del the last ref to an instance and gc.collect(),
    #      then we get a new instance on next request. This test should trust
    #      the result of `test_Dataset_flyweight`.

    # creating a new object for the same path
    # yields the same ID
    del ds
    newds = Dataset(path)
    assert_equal(dsorigid, newds.id)

    # recreating the dataset does NOT change the id
    del newds

    ds = Dataset(path)
    ds.create(annex=False, force=True)
    assert_equal(ds.id, dsorigid)

    # even adding an annex doesn't
    del ds
    ds = Dataset(path)
    ds.create(force=True)
    assert_equal(ds.id, dsorigid)

    # dataset ID and annex UUID have nothing to do with each other
    # if an ID was already generated
    assert_true(ds.repo.uuid != ds.id)

    # even if we generate a dataset from scratch with an annex UUID right away,
    # this is also not the ID
    annexds = Dataset(opj(path, 'scratch')).create()
    assert_true(annexds.id != annexds.repo.uuid)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_Dataset_flyweight(path1=None, path2=None):

    import gc
    import sys

    ds1 = Dataset(path1)
    assert_is_instance(ds1, Dataset)
    # Don't create circular references or anything similar
    assert_equal(1, sys.getrefcount(ds1) - 1)

    ds1.create()

    # Due to issue 4862, we currently still require gc.collect() under unclear
    # circumstances to get rid of an exception traceback when creating in an
    # existing directory. That traceback references the respective function
    # frames which in turn reference the repo instance (they are methods).
    # Doesn't happen on all systems, though. Eventually we need to figure that
    # out.
    # However, still test for the refcount after gc.collect() to ensure we don't
    # introduce new circular references and make the issue worse!
    gc.collect()

    # refcount still fine after repo creation:
    assert_equal(1, sys.getrefcount(ds1) - 1)


    # instantiate again:
    ds2 = Dataset(path1)
    assert_is_instance(ds2, Dataset)
    # the very same object:
    ok_(ds1 is ds2)

    # reference the same via relative path:
    with chpwd(path1):
        ds3 = Dataset(relpath(path1, start=path2))
        ok_(ds1 == ds3)
        ok_(ds1 is ds3)

    # gc knows one such object only:
    eq_(1, len([o for o in gc.get_objects()
                if isinstance(o, Dataset) and o.path == path1]))


    # on windows a symlink is not what you think it is
    if not on_windows:
        # reference the same via symlink:
        with chpwd(path2):
            os.symlink(path1, 'linked')
            ds4 = Dataset('linked')
            ds4_id = id(ds4)
            ok_(ds4 == ds1)
            ok_(ds4 is not ds1)

        # underlying repo, however, IS the same:
        ok_(ds4.repo is ds1.repo)

    # deleting one reference has no effect on the other:
    del ds1
    gc.collect()  # TODO: see first comment above
    ok_(ds2 is not None)
    ok_(ds2.repo is ds3.repo)
    if not on_windows:
        ok_(ds2.repo is ds4.repo)

    # deleting remaining references should lead to garbage collection
    del ds2

    with swallow_logs(new_level=1) as cml:
        del ds3
        gc.collect()  # TODO: see first comment above
        # flyweight vanished:
        assert_not_in(path1, Dataset._unique_instances.keys())
        # no such instance known to gc anymore:
        eq_([], [o for o in gc.get_objects()
                 if isinstance(o, Dataset) and o.path == path1])
        # underlying repo should only be cleaned up, if ds3 was the last
        # reference to it. Otherwise the repo instance should live on
        # (via symlinked ds4):
        finalizer_log = "Finalizer called on: AnnexRepo(%s)" % path1
        if on_windows:
            cml.assert_logged(msg=finalizer_log,
                              level="Level 1",
                              regex=False)
        else:
            assert_not_in(finalizer_log, cml.out)
            # symlinked is still there:
            ok_(ds4 is not None)
            eq_(ds4_id, id(ds4))


@with_tempfile
def test_property_reevaluation(repo1=None):
    ds = Dataset(repo1)
    assert_is_none(ds.repo)
    assert_is_not_none(ds.config)
    first_config = ds.config
    assert_false(ds._cfg_bound)
    assert_is_none(ds.id)

    ds.create()
    assert_repo_status(repo1)
    # after creation, we have `repo`, and `config` was reevaluated to point
    # to the repo's config:
    assert_is_not_none(ds.repo)
    assert_is_not_none(ds.config)
    second_config = ds.config
    assert_true(ds._cfg_bound)
    assert_is(ds.config, ds.repo.config)
    assert_is_not(first_config, second_config)
    assert_is_not_none(ds.id)
    first_id = ds.id

    ds.drop(what='all', reckless='kill', recursive=True)
    # repo is gone, and config is again reevaluated to only provide user/system
    # level config:
    assert_false(lexists(ds.path))
    assert_is_none(ds.repo)
    assert_is_not_none(ds.config)
    third_config = ds.config
    assert_false(ds._cfg_bound)
    assert_is_not(second_config, third_config)
    assert_is_none(ds.id)

    ds.create()
    assert_repo_status(repo1)
    # after recreation everything is sane again:
    assert_is_not_none(ds.repo)
    assert_is_not_none(ds.config)
    assert_is(ds.config, ds.repo.config)
    forth_config = ds.config
    assert_true(ds._cfg_bound)
    assert_is_not(third_config, forth_config)
    assert_is_not_none(ds.id)
    assert_not_equal(ds.id, first_id)


# While os.symlink does work on windows (since vista), os.path.realpath
# doesn't resolve such symlinks. This has all kinds of implications.
# Hopefully this can be dealt with, when we switch to using pathlib
# (see datalad-revolution).
@known_failure_windows
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile
def test_symlinked_dataset_properties(repo1=None, repo2=None, repo3=None, non_repo=None, symlink=None):

    ds = Dataset(repo1).create()

    # now, let ds be a symlink and change that symlink to point to different
    # things:
    ar2 = AnnexRepo(repo2)
    ar3 = AnnexRepo(repo3)
    assert_true(os.path.isabs(non_repo))

    os.symlink(repo1, symlink)
    ds_link = Dataset(symlink)
    assert_is(ds_link.repo, ds.repo)  # same Repo instance
    assert_is_not(ds_link, ds)  # but not the same Dataset instance
    assert_is(ds_link.config, ds.repo.config)
    assert_true(ds_link._cfg_bound)
    assert_is_not_none(ds_link.id)
    # same id, although different Dataset instance:
    assert_equal(ds_link.id, ds.id)

    os.unlink(symlink)
    os.symlink(repo2, symlink)

    assert_is(ds_link.repo, ar2)  # same Repo instance
    assert_is(ds_link.config, ar2.config)
    assert_true(ds_link._cfg_bound)
    # id is None again, since this repository is an annex but there was no
    # Dataset.create() called yet.
    assert_is_none(ds_link.id)

    os.unlink(symlink)
    os.symlink(repo3, symlink)

    assert_is(ds_link.repo, ar3)  # same Repo instance
    assert_is(ds_link.config, ar3.config)
    assert_true(ds_link._cfg_bound)
    # id is None again, since this repository is an annex but there was no
    # Dataset.create() called yet.
    assert_is_none(ds_link.id)

    os.unlink(symlink)
    os.symlink(non_repo, symlink)

    assert_is_none(ds_link.repo)
    assert_is_not(ds_link.config, ar3.config)
    assert_false(ds_link._cfg_bound)
    assert_is_none(ds_link.id)


@with_tempfile(mkdir=True)
def test_resolve_path(path=None):
    if str(Path(path).resolve()) != path:
        raise SkipTest("Test assumptions require non-symlinked parent paths")
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    opath = op.join(path, "origin")
    os.makedirs(opath)
    if not on_windows:
        lpath = op.join(path, "linked")
        os.symlink('origin', lpath)

    ds_global = Dataset(path)
    # path resolution of absolute paths is not influenced by symlinks
    # ignore the linked path on windows, it is not a symlink in the POSIX sense
    for d in (opath,) if on_windows else (opath, lpath):
        ds_local = Dataset(d)
        # no symlink resolution
        eq_(str(resolve_path(d)), d)
        # list comes out as a list
        eq_(resolve_path([d]), [Path(d)])
        # multiple OK
        eq_(resolve_path([d, d]), [Path(d), Path(d)])

        with chpwd(d):
            # be aware: knows about cwd, but this CWD has symlinks resolved
            eq_(str(resolve_path(d).cwd()), opath)
            # using pathlib's `resolve()` will resolve any
            # symlinks
            # also resolve `opath`, as on old windows systems the path might
            # come in crippled (e.g. C:\Users\MIKE~1/...)
            # and comparison would fails unjustified
            eq_(resolve_path('.').resolve(), ut.Path(opath).resolve())
            # no norming, but absolute paths, without resolving links
            eq_(resolve_path('.'), ut.Path(d))
            eq_(str(resolve_path('.')), d)

            # there is no concept of an "explicit" relative path anymore
            # relative is relative, regardless of the specific syntax
            eq_(resolve_path(op.join(os.curdir, 'bu'), ds=ds_global),
                ds_global.pathobj / 'bu')
            # there is no full normpath-ing or other funky resolution of
            # parent directory back-reference
            eq_(str(resolve_path(op.join(os.pardir, 'bu'), ds=ds_global)),
                op.join(ds_global.path, os.pardir, 'bu'))

        # resolve against a dataset given as a path/str
        # (cmdline input scenario)
        eq_(resolve_path('bu', ds=ds_local.path), Path.cwd() / 'bu')
        eq_(resolve_path('bu', ds=ds_global.path), Path.cwd() / 'bu')
        # resolve against a dataset given as a dataset instance
        # (object method scenario)
        eq_(resolve_path('bu', ds=ds_local), ds_local.pathobj / 'bu')
        eq_(resolve_path('bu', ds=ds_global), ds_global.pathobj / 'bu')
        # not being inside a dataset doesn't change the resolution result
        eq_(resolve_path(op.join(os.curdir, 'bu'), ds=ds_global),
            ds_global.pathobj / 'bu')
        eq_(str(resolve_path(op.join(os.pardir, 'bu'), ds=ds_global)),
            op.join(ds_global.path, os.pardir, 'bu'))


# little brother of the test above, but actually (must) run
# under any circumstances
@with_tempfile(mkdir=True)
def test_resolve_path_symlink_edition(path=None):
    deepest = ut.Path(path) / 'one' / 'two' / 'three'
    deepest_str = str(deepest)
    os.makedirs(deepest_str)
    with chpwd(deepest_str):
        # direct absolute
        eq_(deepest, resolve_path(deepest))
        eq_(deepest, resolve_path(deepest_str))
        # explicit direct relative
        eq_(deepest, resolve_path('.'))
        eq_(deepest, resolve_path(op.join('.', '.')))
        eq_(deepest, resolve_path(op.join('..', 'three')))
        eq_(deepest, resolve_path(op.join('..', '..', 'two', 'three')))
        eq_(deepest, resolve_path(op.join('..', '..', '..',
                                              'one', 'two', 'three')))
        # weird ones
        eq_(deepest, resolve_path(op.join('..', '.', 'three')))
        eq_(deepest, resolve_path(op.join('..', 'three', '.')))
        eq_(deepest, resolve_path(op.join('..', 'three', '.')))
        eq_(deepest, resolve_path(op.join('.', '..', 'three')))


@with_tempfile(mkdir=True)
def test_hashable(path=None):
    path = ut.Path(path)
    tryme = set()
    # is it considered hashable at all
    tryme.add(Dataset(path / 'one'))
    eq_(len(tryme), 1)
    # do another one, same class different path
    tryme.add(Dataset(path / 'two'))
    eq_(len(tryme), 2)
    # test whether two different types of repo instances pointing
    # to the same repo on disk are considered different
    Dataset(path).create()
    tryme.add(GitRepo(path))
    eq_(len(tryme), 3)
    tryme.add(AnnexRepo(path))
    eq_(len(tryme), 4)
