# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create action

"""

import os
import os.path as op

import pytest

from datalad.api import create
from datalad.cmd import WitlessRunner as Runner
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError
from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_status,
    eq_,
    has_symlink_capability,
    ok_,
    ok_exists,
    swallow_outputs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
)

_dataset_hierarchy_template = {
    'origin': {
        'file1': '',
        # Add prefix to prevent DATALAD_TESTS_OBSCURE_PREFIX=- from working as
        # intended. 'git submodule add' cannot handle paths starting with -.
        u'ds-' + OBSCURE_FILENAME: {
            'file2': 'file2',
            'subsub': {
                'file3': 'file3'}}}}

raw = dict(return_type='list', result_filter=None, result_xfm=None, on_failure='ignore')


@with_tempfile(mkdir=True)
@with_tempfile
def test_create_raises(path=None, outside_path=None):
    ds = Dataset(path)
    # incompatible arguments (annex only):
    assert_raises(ValueError, ds.create, annex=False, description='some')

    with open(op.join(path, "somefile.tst"), 'w') as f:
        f.write("some")
    # non-empty without `force`:
    assert_in_results(
        ds.create(force=False, **raw),
        status='error',
        message='will not create a dataset in a non-empty directory, use `--force` option to ignore')
    # non-empty with `force`:
    ds.create(force=True)
    # create sub outside of super:
    assert_in_results(
        ds.create(outside_path, **raw),
        status='error',
        message=(
            'dataset containing given paths is not underneath the reference '
            'dataset %s: %s', ds, outside_path))
    obscure_ds = u"ds-" + OBSCURE_FILENAME
    # create a sub:
    ds.create(obscure_ds)
    # fail when doing it again
    assert_in_results(
        ds.create(obscure_ds, **raw),
        status='error',
        message=('collision with %s (dataset) in dataset %s',
                 str(ds.pathobj / obscure_ds),
                 ds.path)
    )

    # now deinstall the sub and fail trying to create a new one at the
    # same location
    ds.drop(obscure_ds, what='all', reckless='kill', recursive=True)
    assert_in(obscure_ds, ds.subdatasets(state='absent', result_xfm='relpaths'))
    # and now should fail to also create inplace or under
    assert_in_results(
        ds.create(obscure_ds, **raw),
        status='error',
        message=('collision with %s (dataset) in dataset %s',
                 str(ds.pathobj / obscure_ds),
                 ds.path)
    )
    assert_in_results(
        ds.create(op.join(obscure_ds, 'subsub'), **raw),
        status='error',
        message=('collision with %s (dataset) in dataset %s',
                 str(ds.pathobj / obscure_ds),
                 ds.path)
    )
    os.makedirs(op.join(ds.path, 'down'))
    with open(op.join(ds.path, 'down', "someotherfile.tst"), 'w') as f:
        f.write("someother")
    ds.save()
    assert_in_results(
        ds.create('down', **raw),
        status='error',
        message=('collision with content in parent dataset at %s: %s',
                 ds.path,
                 [str(ds.pathobj / 'down' / 'someotherfile.tst')]),
    )


@with_tempfile
def test_create_force_subds(path=None):
    ds = Dataset(path).create()
    subds = ds.create("subds")
    # We get an error when trying calling create in an existing subdataset
    assert_in_results(
        subds.create(force=False, **raw),
        status="error")
    # ... but we can force it
    assert_in_results(
        subds.create(force=True, **raw),
        status="ok")
    # ... even if it is uninstalled.
    subds.drop(what='all', reckless='kill', recursive=True)
    ok_(not subds.is_installed())
    assert_in_results(
        subds.create(force=True, **raw),
        status="ok")


@with_tempfile
@with_tempfile
def test_create_curdir(path=None, path2=None):
    with chpwd(path, mkdir=True):
        create()
    ds = Dataset(path)
    ok_(ds.is_installed())
    assert_repo_status(ds.path, annex=True)

    with chpwd(path2, mkdir=True):
        create(annex=False)
    ds = Dataset(path2)
    ok_(ds.is_installed())
    assert_repo_status(ds.path, annex=False)
    ok_(op.exists(op.join(ds.path, '.noannex')))


@with_tempfile
@with_tempfile
def test_create(probe=None, path=None):
    # only as a probe whether this FS is a crippled one
    ar = AnnexRepo(probe, create=True)

    ds = Dataset(path)
    ds.create(
        description="funny",
        # custom git init option
        initopts=dict(shared='world') if not ar.is_managed_branch() else None)
    ok_(ds.is_installed())
    assert_repo_status(ds.path, annex=True)

    # check default backend
    (ds.pathobj / "f1").write_text("1")
    ds.save()
    eq_(ds.repo.get_file_backend(["f1"]), ['MD5E'])

    if not ar.is_managed_branch():
        eq_(ds.config.get("core.sharedrepository"), '2')
    # check description in `info`
    cmlout = ds.repo.call_annex(['info'])
    assert_in('funny [here]', cmlout)
    # check dataset ID
    eq_(ds.config.get_value('datalad.dataset', 'id'),
        ds.id)


@with_tempfile
def test_create_sub(path=None):

    ds = Dataset(path)
    ds.create()

    # 1. create sub and add to super:
    subds = ds.create(op.join("some", "what", "deeper"))
    ok_(isinstance(subds, Dataset))
    ok_(subds.is_installed())
    assert_repo_status(subds.path, annex=True)
    assert_in(
        'submodule.some/what/deeper.datalad-id={}'.format(
            subds.id),
        list(ds.repo.call_git_items_(['config', '--file', '.gitmodules',
                                      '--list'],
                                     read_only=True))
    )

    # subdataset is known to superdataset:
    assert_in(op.join("some", "what", "deeper"),
              ds.subdatasets(result_xfm='relpaths'))
    # and was committed:
    assert_repo_status(ds.path)

    # subds finds superdataset
    ok_(subds.get_superdataset() == ds)

    # 2. create sub without adding to super:
    subds2 = Dataset(op.join(path, "someother")).create()
    ok_(isinstance(subds2, Dataset))
    ok_(subds2.is_installed())
    assert_repo_status(subds2.path, annex=True)

    # unknown to superdataset:
    assert_not_in("someother", ds.subdatasets(result_xfm='relpaths'))

    # 3. create sub via super:
    subds3 = ds.create("third", annex=False)
    ok_(isinstance(subds3, Dataset))
    ok_(subds3.is_installed())
    assert_repo_status(subds3.path, annex=False)
    assert_in("third", ds.subdatasets(result_xfm='relpaths'))


@with_tempfile
def test_create_sub_gh3463(path=None):
    ds = Dataset(path)
    ds.create()

    # Test non-bound call.
    with chpwd(ds.path):
        create("subds0", dataset=".")
    assert_repo_status(ds.path)

    # Test command-line invocation directly.
    Runner(cwd=ds.path).run(["datalad", "create", "-d.", "subds1"])
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
def test_create_dataset_same_as_path(path=None):
    with chpwd(path):
        ds = create(dataset=".", path=".")
    assert_repo_status(ds.path)


@with_tempfile
def test_create_sub_dataset_dot_no_path(path=None):
    ds = Dataset(path)
    ds.create()

    # Test non-bound call.
    sub0_path = str(ds.pathobj / "sub0")
    os.mkdir(sub0_path)
    with chpwd(sub0_path):
        subds0 = create(dataset=".")
    assert_repo_status(ds.path, untracked=[subds0.path])
    assert_repo_status(subds0.path)

    # Test command-line invocation directly (regression from gh-3484).
    sub1_path = str(ds.pathobj / "sub1")
    os.mkdir(sub1_path)
    Runner(cwd=sub1_path).run(["datalad", "create", "-d."])
    assert_repo_status(ds.path, untracked=[subds0.path, sub1_path])


@with_tree(tree=_dataset_hierarchy_template)
def test_create_subdataset_hierarchy_from_top(path=None):
    # how it would look like to overlay a subdataset hierarchy onto
    # an existing directory tree
    ds = Dataset(op.join(path, 'origin')).create(force=True)
    # we got a dataset ....
    ok_(ds.is_installed())
    # ... but it has untracked content
    ok_(ds.repo.dirty)
    subds = ds.create(u"ds-" + OBSCURE_FILENAME, force=True)
    ok_(subds.is_installed())
    ok_(subds.repo.dirty)
    subsubds = subds.create('subsub', force=True)
    ok_(subsubds.is_installed())
    ok_(subsubds.repo.dirty)
    ok_(ds.id != subds.id != subsubds.id)
    ds.save(updated=True, recursive=True)
    # 'file*' in each repo was untracked before and should remain as such
    # (we don't want a #1419 resurrection
    ok_(ds.repo.dirty)
    ok_(subds.repo.dirty)
    ok_(subsubds.repo.dirty)
    # if we add these three, we should get clean
    ds.save([
        'file1',
        op.join(subds.path, 'file2'),
        op.join(subsubds.path, 'file3')])
    assert_repo_status(ds.path)
    ok_(ds.id != subds.id != subsubds.id)


@with_tempfile
def test_nested_create(path=None):
    # to document some more organic usage pattern
    ds = Dataset(path).create()
    assert_repo_status(ds.path)
    lvl2relpath = op.join('lvl1', 'lvl2')
    lvl2path = op.join(ds.path, lvl2relpath)
    os.makedirs(lvl2path)
    os.makedirs(op.join(ds.path, 'lvl1', 'empty'))
    with open(op.join(lvl2path, 'file'), 'w') as f:
        f.write('some')
    ok_(ds.save())
    # Empty directories are filtered out.
    assert_repo_status(ds.path, untracked=[])
    # later create subdataset in a fresh dir
    # WINDOWS FAILURE IS NEXT LINE
    subds1 = ds.create(op.join('lvl1', 'subds'))
    assert_repo_status(ds.path, untracked=[])
    eq_(ds.subdatasets(result_xfm='relpaths'), [op.join('lvl1', 'subds')])
    # later create subdataset in an existing empty dir
    subds2 = ds.create(op.join('lvl1', 'empty'))
    assert_repo_status(ds.path)
    # later try to wrap existing content into a new subdataset
    # but that won't work
    assert_in_results(
        ds.create(lvl2relpath, **raw),
        status='error',
        message=(
            'collision with content in parent dataset at %s: %s',
            ds.path, [op.join(lvl2path, 'file')]))
    # even with force, as to do this properly complicated surgery would need to
    # take place
    # MIH disable shaky test till proper dedicated upfront check is in-place in `create`
    # gh-1725
    #assert_in_results(
    #    ds.create(lvl2relpath, force=True,
    #              on_failure='ignore', result_xfm=None, result_filter=None),
    #    status='error', action='add')
    # only way to make it work is to unannex the content upfront
    ds.repo.call_annex(['unannex', op.join(lvl2relpath, 'file')])
    # nothing to save, git-annex commits the unannex itself, but only on v5
    ds.repo.commit()
    # still nothing without force
    # "err='lvl1/lvl2' already exists in the index"
    assert_in_results(
        ds.create(lvl2relpath, **raw),
        status='error',
        message='will not create a dataset in a non-empty directory, use `--force` option to ignore')
    # XXX even force doesn't help, because (I assume) GitPython doesn't update
    # its representation of the Git index properly
    ds.create(lvl2relpath, force=True)
    assert_in(lvl2relpath, ds.subdatasets(result_xfm='relpaths'))


# Imported from #1016
@with_tree({'ds2': {'file1.txt': 'some'}})
def test_saving_prior(topdir=None):
    # the problem is that we might be saving what is actually needed to be
    # "created"

    # we would like to place this structure into a hierarchy of two datasets
    # so we create first top one
    ds1 = create(topdir, force=True)
    # and everything is ok, stuff is not added BUT ds1 will be considered dirty
    assert_repo_status(ds1.path, untracked=['ds2'])
    # And then we would like to initiate a sub1 subdataset
    ds2 = create('ds2', dataset=ds1, force=True)
    # But what will happen is file1.txt under ds2 would get committed first into
    # ds1, and then the whole procedure actually crashes since because ds2/file1.txt
    # is committed -- ds2 is already known to git and it just pukes with a bit
    # confusing    'ds2' already exists in the index
    assert_in('ds2', ds1.subdatasets(result_xfm='relpaths'))


@with_tempfile(mkdir=True)
def test_create_withcfg(path=None):
    ds = create(
        dataset=path,
        cfg_proc=['yoda'])
    assert_repo_status(path)
    assert (ds.pathobj / 'README.md').exists()

    # If we are creating a dataset within a reference dataset, we save _after_
    # the procedure runs.
    ds.create('subds', cfg_proc=['yoda'])
    assert_repo_status(path)
    assert (ds.pathobj / 'subds' / 'README.md').exists()


@with_tempfile(mkdir=True)
def test_create_fake_dates(path=None):
    ds = create(path, fake_dates=True)

    ok_(ds.config.getbool("datalad", "fake-dates"))
    ok_(ds.repo.fake_dates_enabled)

    # Another instance detects the fake date configuration.
    ok_(Dataset(path).repo.fake_dates_enabled)

    first_commit = ds.repo.get_revisions(options=["--reverse", "--all"])[0]

    eq_(ds.config.obtain("datalad.fake-dates-start") + 1,
        int(ds.repo.format_commit("%ct", first_commit)))


@with_tempfile(mkdir=True)
def test_cfg_passthrough(path=None):
    runner = Runner()
    _ = runner.run(
        ['datalad',
         '-c', 'annex.tune.objecthash1=true',
         '-c', 'annex.tune.objecthashlower=true',
         'create', path])
    ds = Dataset(path)
    eq_(ds.config.get('annex.tune.objecthash1', None), 'true')
    eq_(ds.config.get('annex.tune.objecthashlower', None), 'true')


@with_tree({"empty": {".git": {}, "ds": {}},
            "nonempty": {".git": {"bogus": "content"}, "ds": {}},
            "git_with_head": {".git": {"HEAD": ""}, "ds": {}}
            })
def test_empty_git_upstairs(topdir=None):
    # create() doesn't get confused by an empty .git/ upstairs (gh-3473)
    assert_in_results(
        create(op.join(topdir, "empty", "ds"), **raw),
        status="ok", type="dataset", action="create")
    # ... and it will ignore non-meaningful content in .git
    assert_in_results(
        create(op.join(topdir, "nonempty", "ds"), **raw),
        status="ok", type="dataset", action="create")
    # ... but it will raise if it detects a valid repo
    # (by existence of .git/HEAD as defined in GitRepo._valid_git_test_path)
    with assert_raises(CommandError):
        create(op.join(topdir, "git_with_head", "ds"), **raw)


@with_tempfile(mkdir=True)
def check_create_obscure(create_kwargs, path):
    with chpwd(path):
        with swallow_outputs():
            ds = create(result_renderer="default", **create_kwargs)
    ok_(ds.is_installed())


@pytest.mark.parametrize("kwarg", ["path", "dataset"])
def test_create_with_obscure_name(kwarg):
    check_create_obscure, {"kwarg": OBSCURE_FILENAME}


@with_tempfile
@with_tempfile(mkdir=True)
def check_create_path_semantics(
        cwd, create_ds, path_arg, base_path, other_path):
    ds = Dataset(base_path).create()
    os.makedirs(op.join(ds.path, 'some'))
    target_path = ds.pathobj / "some" / "what" / "deeper"
    with chpwd(
            other_path if cwd == 'elsewhere' else
            base_path if cwd == 'parentds' else
            str(ds.pathobj / 'some') if cwd == 'subdir' else
            str(Path.cwd())):
        subds = create(
            dataset=ds.path if create_ds == 'abspath'
            else str(ds.pathobj.relative_to(cwd)) if create_ds == 'relpath'
            else ds if create_ds == 'instance'
            else create_ds,
            path=str(target_path) if path_arg == 'abspath'
            else str(target_path.relative_to(ds.pathobj)) if path_arg == 'relpath'
            else op.join('what', 'deeper') if path_arg == 'subdir_relpath'
            else path_arg)
        eq_(subds.pathobj, target_path)


@pytest.mark.parametrize(
    "cwd,create_ds,path_arg",
    [
        ('subdir', None, 'subdir_relpath'),
        ('subdir', 'abspath', 'subdir_relpath'),
        ('subdir', 'abspath', 'abspath'),
        ('parentds', None, 'relpath'),
        ('parentds', 'abspath', 'relpath'),
        ('parentds', 'abspath', 'abspath'),
        (None, 'abspath', 'abspath'),
        (None, 'instance', 'abspath'),
        (None, 'instance', 'relpath'),
        ('elsewhere', 'abspath', 'abspath'),
        ('elsewhere', 'instance', 'abspath'),
        ('elsewhere', 'instance', 'relpath'),
    ]
)
def test_create_relpath_semantics(cwd, create_ds, path_arg):
    check_create_path_semantics(cwd, create_ds, path_arg)


@with_tempfile(mkdir=True)
@with_tempfile()
def test_gh2927(path=None, linkpath=None):
    if has_symlink_capability():
        # make it more complicated by default
        Path(linkpath).symlink_to(path, target_is_directory=True)
        path = linkpath
    ds = Dataset(path).create()
    ds.create('subds_clean')
    assert_status('ok', ds.create(op.join('subds_clean', 'subds_lvl1_clean'),
                                  result_xfm=None, return_type='list'))


@with_tempfile(mkdir=True)
def check_create_initopts_form(form, path=None):
    path = Path(path)

    template_dir = path / "templates"
    template_dir.mkdir()
    (template_dir / "foo").write_text("")

    forms = {"list": [f"--template={template_dir}"],
             "dict": {"template": str(template_dir)}}

    ds = Dataset(path / "ds")
    ds.create(initopts=forms[form])
    ok_exists(ds.repo.dot_git / "foo")


@pytest.mark.parametrize("form", ["dict", "list"])
def test_create_initopts_form(form):
    check_create_initopts_form(form)


@with_tempfile
def test_bad_cfg_proc(path=None):
    ds = Dataset(path)
    # check if error is raised for incorrect cfg_proc
    assert_raises(ValueError, ds.create, path=path, cfg_proc='unknown')
    # verify that no directory got created prior to the error
    assert not op.isdir(path)
