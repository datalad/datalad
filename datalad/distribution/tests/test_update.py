# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test update action

"""

import os
import os.path as op
from os.path import exists
from os.path import join as opj
from unittest.mock import patch

import pytest

from datalad import cfg as dl_cfg
from datalad.api import (
    clone,
    install,
    remove,
    update,
)
from datalad.distribution.update import _process_how_args
from datalad.support.annexrepo import AnnexRepo
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_false,
    assert_in,
    assert_in_results,
    assert_is_instance,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    create_tree,
    eq_,
    known_failure_windows,
    maybe_adjust_repo,
    neq_,
    ok_,
    ok_file_has_content,
    skip_if_adjusted_branch,
    slow,
    with_tempfile,
    with_testrepos,
)
from datalad.utils import (
    Path,
    chpwd,
    knows_annex,
    rmtree,
)

from ..dataset import Dataset


@slow
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_simple(origin=None, src_path=None, dst_path=None):
    ca = dict(result_renderer='disabled')
    # a remote dataset with a subdataset underneath
    origds = Dataset(origin).create(**ca)
    # naming is weird, but a legacy artifact
    _ = origds.create('subm 1', **ca)
    _ = origds.create('2', **ca)

    # prepare src
    source = install(src_path, source=origin, recursive=True)
    # forget we cloned it by removing remote, which should lead to
    # setting tracking branch to target:
    source.repo.remove_remote(DEFAULT_REMOTE)
    # also forget the declared absolute location of the submodules, and turn them
    # relative to this/a clone
    for sub in source.subdatasets(result_xfm=lambda x: x['gitmodule_name']):
        source.subdatasets(path=sub, set_property=[('url', './{}'.format(sub))])

    # dataset without sibling will not need updates
    assert_status('notneeded', source.update())
    # deprecation message doesn't ruin things
    assert_status('notneeded', source.update(fetch_all=True))
    # but error if unknown sibling is given
    assert_status('impossible', source.update(sibling='funky', on_failure='ignore'))

    # get a clone to update later on:
    dest = install(dst_path, source=src_path, recursive=True)
    # test setup done;
    # assert all fine
    assert_repo_status(dst_path)
    assert_repo_status(src_path)

    # update yields nothing => up-to-date
    assert_status('ok', dest.update())
    assert_repo_status(dst_path)

    # modify remote:
    with open(opj(src_path, "update.txt"), "w") as f:
        f.write("Additional content")
    source.save(path="update.txt", message="Added update.txt")
    assert_repo_status(src_path)

    # update without `merge` only fetches:
    assert_status('ok', dest.update())
    # modification is not known to active branch:
    assert_not_in("update.txt",
                  dest.repo.get_files(dest.repo.get_active_branch()))
    # modification is known to branch <default remote>/<default branch>
    assert_in("update.txt",
              dest.repo.get_files(DEFAULT_REMOTE + "/" + DEFAULT_BRANCH))

    # merge:
    assert_status('ok', dest.update(merge=True))
    # modification is now known to active branch:
    assert_in("update.txt",
              dest.repo.get_files(dest.repo.get_active_branch()))
    # it's known to annex, but has no content yet:
    annexprops = dest.repo.get_file_annexinfo("update.txt",
                                              eval_availability=True)
    annexprops['key']  # blows if unknown
    eq_(False, annexprops['has_content'])

    # check subdataset path constraints, baseline (parent + 2 subds)
    assert_result_count(dest.update(recursive=True),
                        3, status='ok', type='dataset')
    # no recursion and invalid path still updates the parent
    res = dest.update(path='whatever')
    assert_result_count(res, 1, status='ok', type='dataset')
    assert_result_count(res, 1, status='ok', path=dest.path)
    # invalid path with recursion also does
    res = dest.update(recursive=True, path='whatever')
    assert_result_count(res, 1, status='ok', type='dataset')
    assert_result_count(res, 1, status='ok', path=dest.path)
    # valid path and no recursion only updates the parent
    res = dest.update(path='subm 1')
    assert_result_count(res, 1, status='ok', type='dataset')
    assert_result_count(res, 1, status='ok', path=dest.path)
    # valid path and recursion updates matching
    res = dest.update(recursive=True, path='subm 1')
    assert_result_count(res, 2, status='ok', type='dataset')
    assert_result_count(res, 1, status='ok', path=dest.path)
    assert_result_count(res, 1, status='ok', path=str(dest.pathobj / 'subm 1'))
    # additional invalid path doesn't hurt
    res = dest.update(recursive=True, path=['subm 1', 'mike'])
    assert_result_count(res, 2, status='ok', type='dataset')
    # full match
    res = dest.update(recursive=True, path=['subm 1', '2'])
    assert_result_count(res, 3, status='ok', type='dataset')

    # test that update doesn't crash if we specify only a single path (submod) to
    # operate on
    with chpwd(dest.path):
        # in 0.11.x it would be a single result since "pwd" dataset is not
        # considered, and would be relative path (as specified).
        # In 0.12.0 - it would include implicit pwd dataset, and paths would be absolute
        res_update = update(path=['subm 1'], recursive=True)
        assert_result_count(res_update, 2)
        for p in dest.path, str(dest.pathobj / 'subm 1'):
            assert_in_results(res_update, path=p, action='update', status='ok', type='dataset')

        # and with merge we would also try to save (but there would be no changes)
        res_merge = update(path=['subm 1'], recursive=True, merge=True)
        assert_result_count(res_merge, 2, action='update')
        # 2 of "updates" really.
        assert_in_results(res_merge, action='update', status='ok', type='dataset')
        assert_in_results(res_merge, action='save', status='notneeded', type='dataset')

    # smoke-test if recursive update doesn't fail if submodule is removed
    # and that we can run it from within a dataset without providing it
    # explicitly
    assert_result_count(
        dest.remove('subm 1'), 1,
        status='ok', action='remove', path=opj(dest.path, 'subm 1'))
    with chpwd(dest.path):
        assert_result_count(
            update(recursive=True), 2,
            status='ok', type='dataset')
    assert_result_count(
        dest.update(merge=True, recursive=True), 2,
        action='update', status='ok', type='dataset')

    # and now test recursive update with merging in differences
    create_tree(opj(source.path, '2'), {'load.dat': 'heavy'})
    source.save(opj('2', 'load.dat'),
                message="saving changes within subm2",
                recursive=True)
    assert_result_count(
        dest.update(merge=True, recursive=True), 2,
        action='update', status='ok', type='dataset')
    # and now we can get new file
    dest.get(opj('2', 'load.dat'))
    ok_file_has_content(opj(dest.path, '2', 'load.dat'), 'heavy')


@with_tempfile
@with_tempfile
def test_update_git_smoke(src_path=None, dst_path=None):
    # Apparently was just failing on git repos for basic lack of coverage, hence this quick test
    ds = Dataset(src_path).create(annex=False)
    target = install(
        dst_path, source=src_path,
        result_xfm='datasets', return_type='item-or-list')
    create_tree(ds.path, {'file.dat': '123'})
    ds.save('file.dat')
    assert_result_count(
        target.update(recursive=True, merge=True), 1,
        action='update', status='ok', type='dataset')
    ok_file_has_content(opj(target.path, 'file.dat'), '123')


@slow  # ~9s
@with_tempfile(mkdir=True)
def test_update_fetch_all(path=None):
    path = Path(path)
    remote_1 = str(path / "remote_1")
    remote_2 = str(path / "remote_2")

    ds = Dataset(path / "src").create()
    src = ds.repo.path

    ds_rmt1 = clone(source=src, path=remote_1)
    ds_rmt2 = clone(source=src, path=remote_2)

    ds.siblings('add', name="sibling_1", url=remote_1)
    ds.siblings('add', name="sibling_2", url=remote_2)

    # modify the remotes:
    (ds_rmt1.pathobj / "first.txt").write_text("some file load")
    ds_rmt1.save()

    # TODO: Modify an already present file!

    (ds_rmt2.pathobj / "second.txt").write_text("different file load")
    ds_rmt2.save()

    # Let's init some special remote which we couldn't really update/fetch
    if not dl_cfg.get('datalad.tests.dataladremote'):
        ds.repo.init_remote(
            'datalad',
            ['encryption=none', 'type=external', 'externaltype=datalad'])
    # fetch all remotes
    assert_result_count(
        ds.update(), 1, status='ok', type='dataset')

    # no merge, so changes are not in active branch:
    assert_not_in("first.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    assert_not_in("second.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    # but we know the changes in remote branches:
    assert_in("first.txt", ds.repo.get_files("sibling_1/" + DEFAULT_BRANCH))
    assert_in("second.txt", ds.repo.get_files("sibling_2/" + DEFAULT_BRANCH))

    # no merge strategy for multiple remotes yet:
    # more clever now, there is a tracking branch that provides a remote
    #assert_raises(NotImplementedError, ds.update, merge=True)

    # merge a certain remote:
    assert_result_count(
        ds.update(sibling='sibling_1', merge=True),
        1, action='update', status='ok', type='dataset')

    # changes from sibling_2 still not present:
    assert_not_in("second.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    # changes from sibling_1 merged:
    assert_in("first.txt",
              ds.repo.get_files(ds.repo.get_active_branch()))
    # it's known to annex, but has no content yet:
    annexprops = ds.repo.get_file_annexinfo(
        "first.txt", eval_availability=True)
    annexprops['key']  # blows if unknown
    eq_(False, annexprops['has_content'])


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_newthings_coming_down(originpath=None, destpath=None):
    origin = GitRepo(originpath, create=True)
    create_tree(originpath, {'load.dat': 'heavy'})
    Dataset(originpath).save('load.dat')
    ds = install(
        source=originpath, path=destpath,
        result_xfm='datasets', return_type='item-or-list')
    assert_is_instance(ds.repo, GitRepo)
    assert_in(DEFAULT_REMOTE, ds.repo.get_remotes())
    # turn origin into an annex
    origin = AnnexRepo(originpath, create=True)
    # clone doesn't know yet
    assert_false(knows_annex(ds.path))
    # but after an update it should
    # no merge, only one sibling, no parameters should be specific enough
    assert_result_count(ds.update(), 1, status='ok', type='dataset')
    assert(knows_annex(ds.path))
    # no branches appeared
    eq_(ds.repo.get_branches(), [DEFAULT_BRANCH])
    # now merge, and get an annex
    assert_result_count(ds.update(merge=True),
                        1, action='update', status='ok', type='dataset')
    assert_in('git-annex', ds.repo.get_branches())
    assert_is_instance(ds.repo, AnnexRepo)
    # should be fully functional
    testfname = opj(ds.path, 'load.dat')
    assert_false(ds.repo.file_has_content(testfname))
    ds.get('.')
    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    # check that a new tag comes down
    origin.tag('first!')
    assert_result_count(ds.update(), 1, status='ok', type='dataset')
    eq_(ds.repo.get_tags(output='name')[0], 'first!')

    # and now we destroy the remote annex
    origin.call_git(['config', '--remove-section', 'annex'])
    rmtree(opj(origin.path, '.git', 'annex'), chmod_files=True)
    origin.call_git(['branch', '-D', 'git-annex'])
    origin = GitRepo(originpath)
    assert_false(knows_annex(originpath))

    # and update the local clone
    # for now this should simply not fail (see gh-793), later might be enhanced to a
    # graceful downgrade
    before_branches = ds.repo.get_branches()
    ok_(any("git-annex" in b
            for b in ds.repo.get_remote_branches()))
    assert_result_count(ds.update(), 1, status='ok', type='dataset')
    eq_(before_branches, ds.repo.get_branches())
    # annex branch got pruned
    assert_false(any("git-annex" in b
                     for b in ds.repo.get_remote_branches()))
    # check that a new tag comes down even if repo types mismatch
    origin.tag('second!')
    assert_result_count(ds.update(), 1, status='ok', type='dataset')
    eq_(ds.repo.get_tags(output='name')[-1], 'second!')


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_volatile_subds(originpath=None, otherpath=None, destpath=None):
    origin = Dataset(originpath).create()
    repo = origin.repo
    if repo.is_managed_branch() and repo.git_annex_version <= "8.20201129":
        # Fails before git-annex's fd161da2c (adjustTree: Consider submodule
        # deletions, 2021-01-06).
        raise SkipTest(
            "On adjusted branch, test requires fix in more recent git-annex")
    ds = install(
        source=originpath, path=destpath,
        result_xfm='datasets', return_type='item-or-list')
    # as a submodule
    sname = 'subm 1'
    osm1 = origin.create(sname)
    assert_result_count(ds.update(), 1, status='ok', type='dataset')
    # nothing without a merge, no inappropriate magic
    assert_not_in(sname, ds.subdatasets(result_xfm='relpaths'))
    assert_result_count(ds.update(merge=True),
                        1, action='update', status='ok', type='dataset')
    # and we should be able to do update with recursive invocation
    assert_result_count(ds.update(merge=True, recursive=True),
                        1, action='update', status='ok', type='dataset')
    # known, and placeholder exists
    assert_in(sname, ds.subdatasets(result_xfm='relpaths'))
    ok_(exists(opj(ds.path, sname)))

    # remove from origin
    origin.remove(sname, reckless='availability')
    assert_result_count(ds.update(merge=True),
                        1, action='update', status='ok', type='dataset')
    # gone locally, wasn't checked out
    assert_not_in(sname, ds.subdatasets(result_xfm='relpaths'))
    assert_false(exists(opj(ds.path, sname)))

    # re-introduce at origin
    osm1 = origin.create(sname)
    create_tree(osm1.path, {'load.dat': 'heavy'})
    origin.save(opj(osm1.path, 'load.dat'))
    assert_result_count(ds.update(merge=True),
                        1, action='update', status='ok', type='dataset')
    # grab new content of uninstall subdataset, right away
    ds.get(opj(ds.path, sname, 'load.dat'))
    ok_file_has_content(opj(ds.path, sname, 'load.dat'), 'heavy')

    # modify ds and subds at origin
    create_tree(origin.path, {'mike': 'this', sname: {'probe': 'little'}})
    origin.save(recursive=True)
    assert_repo_status(origin.path)

    # updates for both datasets should come down the pipe
    assert_result_count(ds.update(merge=True, recursive=True),
                        2, action='update', status='ok', type='dataset')
    assert_repo_status(ds.path)

    # now remove just-installed subdataset from origin again
    origin.remove(sname, reckless='kill')
    assert_not_in(sname, origin.subdatasets(result_xfm='relpaths'))
    assert_in(sname, ds.subdatasets(result_xfm='relpaths'))
    # merge should disconnect the installed subdataset, but leave the actual
    # ex-subdataset alone
    assert_result_count(ds.update(merge=True, recursive=True),
                        1, action='update', type='dataset')
    assert_not_in(sname, ds.subdatasets(result_xfm='relpaths'))
    ok_file_has_content(opj(ds.path, sname, 'load.dat'), 'heavy')
    ok_(Dataset(opj(ds.path, sname)).is_installed())

    # now remove the now disconnected subdataset for further tests
    remove(dataset=op.join(ds.path, sname), reckless='kill')
    assert_repo_status(ds.path)

    # new separate subdataset, not within the origin dataset
    otherds = Dataset(otherpath).create()
    # install separate dataset as a submodule
    ds.install(source=otherds.path, path='other')
    create_tree(otherds.path, {'brand': 'new'})
    otherds.save()
    assert_repo_status(otherds.path)
    # pull in changes
    res = ds.update(merge=True, recursive=True)
    assert_result_count(
        res, 2, status='ok', action='update', type='dataset')
    # the next is to check for #2858
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_reobtain_data(originpath=None, destpath=None):
    origin = Dataset(originpath).create()
    ds = install(
        source=originpath, path=destpath,
        result_xfm='datasets', return_type='item-or-list')
    # no harm
    assert_result_count(ds.update(merge=True, reobtain_data=True),
                        1, action="update", status="ok")
    # content
    create_tree(origin.path, {'load.dat': 'heavy'})
    origin.save(opj(origin.path, 'load.dat'))
    # update does not bring data automatically
    assert_result_count(ds.update(merge=True, reobtain_data=True),
                        1, action="update", status="ok")
    assert_in('load.dat', ds.repo.get_annexed_files())
    assert_false(ds.repo.file_has_content('load.dat'))
    # now get data
    ds.get('load.dat')
    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    # new content at origin
    create_tree(origin.path, {'novel': 'but boring'})
    origin.save()
    # update must not bring in data for new file
    result = ds.update(merge=True, reobtain_data=True)
    assert_in_results(result, action='get', status='notneeded')

    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    assert_in('novel', ds.repo.get_annexed_files())
    assert_false(ds.repo.file_has_content('novel'))
    # modify content at origin
    os.remove(opj(origin.path, 'load.dat'))
    create_tree(origin.path, {'load.dat': 'light'})
    origin.save()
    # update must update file with existing data, but leave empty one alone
    res = ds.update(merge=True, reobtain_data=True)
    assert_result_count(res, 1, status='ok', type='dataset', action='update')
    assert_result_count(res, 1, status='ok', type='file', action='get')
    ok_file_has_content(opj(ds.path, 'load.dat'), 'light')
    assert_false(ds.repo.file_has_content('novel'))


@with_tempfile(mkdir=True)
def test_multiway_merge(path=None):
    # prepare ds with two siblings, but no tracking branch
    ds = Dataset(op.join(path, 'ds_orig')).create()
    r1 = AnnexRepo(path=op.join(path, 'ds_r1'), git_opts={'bare': True})
    r2 = GitRepo(path=op.join(path, 'ds_r2'), git_opts={'bare': True})
    ds.siblings(action='add', name='r1', url=r1.path)
    ds.siblings(action='add', name='r2', url=r2.path)
    assert_status('ok', ds.push(to='r1'))
    # push unlike publish reports on r2 not being an annex remote with a
    # 'notneeded'
    assert_status(('ok', 'notneeded'), ds.push(to='r2'))
    # just a fetch should be no issue
    assert_status('ok', ds.update())
    # ATM we do not support multi-way merges
    assert_status('impossible', ds.update(merge=True, on_failure='ignore'))


# `git annex sync REMOTE` rather than `git merge TARGET` is used on an
# adjusted branch, so we don't give an error if TARGET can't be
# determined.
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_merge_no_merge_target(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    assert_repo_status(ds_src.path)
    ds_clone.repo.checkout(DEFAULT_BRANCH, options=["-bnew"])
    res = ds_clone.update(merge=True, on_failure="ignore")
    assert_in_results(res, status="impossible", action="update")


# `git annex sync REMOTE` is used on an adjusted branch, but this error
# depends on `git merge TARGET` being used.
@skip_if_adjusted_branch
@slow  # 17sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_merge_conflict(path=None):
    path = Path(path)
    ds_src = Dataset(path / "src").create()
    ds_src_s0 = ds_src.create("s0")
    ds_src_s1 = ds_src.create("s1")
    ds_src.save()

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_s0 = Dataset(path / "clone" / "s0")
    ds_clone_s1 = Dataset(path / "clone" / "s1")

    (ds_src.pathobj / "foo").write_text("src content")
    ds_src.save(to_git=True)

    (ds_clone.pathobj / "foo").write_text("clone content")
    ds_clone.save(to_git=True)

    # Top-level merge failure
    res = ds_clone.update(merge=True, on_failure="ignore")
    assert_in_results(res, action="merge", status="error")
    assert_in_results(res, action="update", status="error")
    # Deal with the conflicts. Note that save() won't handle this gracefully
    # because it will try to commit with a pathspec, which git doesn't allow
    # during a merge.
    ds_clone.repo.call_git(["checkout", "--theirs", "--", "foo"])
    ds_clone.repo.call_git(["add", "--", "foo"])
    ds_clone.repo.call_git(["commit", "--no-edit"])
    assert_repo_status(ds_clone.path)

    # Top-level and subdataset merge failure
    (ds_src_s0.pathobj / "foo").write_text("src s0 content")
    (ds_src_s1.pathobj / "foo").write_text("no conflict")
    ds_src.save(recursive=True, to_git=True)

    (ds_clone_s0.pathobj / "foo").write_text("clone s0 content")
    ds_clone.save(recursive=True, to_git=True)
    res = ds_clone.update(merge=True, recursive=True, on_failure="ignore")
    assert_result_count(res, 2, action="merge", status="error")
    assert_result_count(res, 2, action="update", status="error")
    assert_in_results(res, action="merge", status="ok",
                      path=ds_clone_s1.path)
    assert_in_results(res, action="update", status="ok",
                      path=ds_clone_s1.path)
    # No saving happens if there's a top-level conflict.
    assert_repo_status(ds_clone.path,
                       modified=[ds_clone_s0.path, ds_clone_s1.path])


# `git annex sync REMOTE` is used on an adjusted branch, but this error
# depends on `git merge TARGET` being used.
@skip_if_adjusted_branch
@slow  # 13sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_merge_conflict_in_subdataset_only(path=None):
    path = Path(path)
    ds_src = Dataset(path / "src").create()
    ds_src_sub_conflict = ds_src.create("sub_conflict")
    ds_src_sub_noconflict = ds_src.create("sub_noconflict")
    ds_src.save()

    # Set up a scenario where one subdataset has a conflict between the remote
    # and local version, but the parent dataset does not have a conflict
    # because it hasn't recorded the subdataset state.
    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_sub_conflict = Dataset(path / "clone" / "sub_conflict")
    ds_clone_sub_noconflict = Dataset(path / "clone" / "sub_noconflict")

    (ds_src_sub_conflict.pathobj / "foo").write_text("src content")
    ds_src_sub_conflict.save(to_git=True)

    (ds_clone_sub_conflict.pathobj / "foo").write_text("clone content")
    ds_clone_sub_conflict.save(to_git=True)

    (ds_src_sub_noconflict.pathobj / "foo").write_text("src content")
    ds_src_sub_noconflict.save()

    res = ds_clone.update(merge=True, recursive=True, on_failure="ignore")
    assert_in_results(res, action="merge", status="error",
                      path=ds_clone_sub_conflict.path)
    assert_in_results(res, action="merge", status="ok",
                      path=ds_clone_sub_noconflict.path)
    assert_in_results(res, action="save", status="ok",
                      path=ds_clone.path)
    # We saved the subdataset without a conflict...
    assert_repo_status(ds_clone_sub_noconflict.path)
    # ... but the one with the conflict leaves it for the caller to handle.
    ok_(ds_clone_sub_conflict.repo.call_git(
        ["ls-files", "--unmerged", "--", "foo"], read_only=True).strip())


# `git annex sync REMOTE` is used on an adjusted branch, but this error
# depends on `git merge --ff-only ...` being used.
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_merge_ff_only(path=None):
    path = Path(path)
    ds_src = Dataset(path / "src").create()
    ds_clone_ff = install(source=ds_src.path, path=path / "clone_ff",
                          result_xfm="datasets")

    ds_clone_nonff = install(source=ds_src.path, path=path / "clone_nonff",
                             result_xfm="datasets")

    (ds_clone_nonff.pathobj / "foo").write_text("local change")
    ds_clone_nonff.save(recursive=True)

    (ds_src.pathobj / "bar").write_text("remote change")
    ds_src.save(recursive=True)

    assert_in_results(
        ds_clone_ff.update(merge="ff-only", on_failure="ignore"),
        action="merge", status="ok")

    # ff-only prevents a non-fast-forward ...
    assert_in_results(
        ds_clone_nonff.update(merge="ff-only", on_failure="ignore"),
        action="merge", status="error")
    # ... that would work with "any".
    assert_in_results(
        ds_clone_nonff.update(merge="any", on_failure="ignore"),
        action="merge", status="ok")


@slow  # 11sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_merge_follow_parentds_subdataset_other_branch(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    on_adjusted = ds_src.repo.is_managed_branch()
    ds_src_subds = ds_src.create("subds")
    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_subds = Dataset(ds_clone.pathobj / "subds")

    ds_src_subds.repo.call_git(["checkout", "-b", "other"])
    (ds_src_subds.pathobj / "foo").write_text("foo content")
    ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    res = ds_clone.update(merge=True, follow="parentds", recursive=True,
                          on_failure="ignore")
    if on_adjusted:
        # Our git-annex sync based on approach on adjusted branches is
        # incompatible with follow='parentds'.
        assert_in_results(res, action="update", status="impossible")
        return
    else:
        assert_in_results(res, action="update", status="ok")
    eq_(ds_clone.repo.get_hexsha(), ds_src.repo.get_hexsha())
    ok_(ds_clone_subds.repo.is_under_annex("foo"))

    (ds_src_subds.pathobj / "bar").write_text("bar content")
    ds_src.save(recursive=True)
    ds_clone_subds.repo.checkout(DEFAULT_BRANCH, options=["-bnew"])
    ds_clone.update(merge=True, follow="parentds", recursive=True)
    if not on_adjusted:
        eq_(ds_clone.repo.get_hexsha(), ds_src.repo.get_hexsha())


# This test depends on the source repo being an un-adjusted branch.
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_merge_follow_parentds_subdataset_adjusted_warning(path=None):
    path = Path(path)

    ds_src = Dataset(path / "source").create()
    ds_src_subds = ds_src.create("subds")

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_subds = Dataset(ds_clone.pathobj / "subds")
    maybe_adjust_repo(ds_clone_subds.repo)
    # Note: Were we to save ds_clone here, we would get a merge conflict in the
    # top repo for the submodule (even if using 'git annex sync' rather than
    # 'git merge').

    ds_src_subds.repo.call_git(["checkout", DEFAULT_BRANCH + "^0"])
    (ds_src_subds.pathobj / "foo").write_text("foo content")
    ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    assert_in_results(
        ds_clone.update(merge=True, recursive=True, follow="parentds",
                        on_failure="ignore"),
        status="impossible",
        path=ds_clone_subds.path,
        action="update")
    eq_(ds_clone.repo.get_hexsha(), ds_src.repo.get_hexsha())


@slow  # 12 + 21sec on Yarik's laptop
@pytest.mark.parametrize("on_adjusted", [True, False])
# Skip non-adjusted case for systems that only support adjusted branches.
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_merge_follow_parentds_subdataset_detached(path=None, *, on_adjusted):
    if on_adjusted and DEFAULT_REMOTE != "origin" and \
       external_versions['cmd:annex'] <= "8.20210330":
        raise SkipTest(
            "'git annex init' with adjusted branch currently fails "
            "due to hard-coded 'origin'")

    # Note: For the adjusted case, this is not much more than a smoke test that
    # on an adjusted branch we fail sensibly. The resulting state is not easy
    # to reason about nor desirable.
    path = Path(path)
    # $path/source/s0/s1
    # The additional dataset level is to gain some confidence that this works
    # for nested datasets.
    ds_src = Dataset(path / "source").create()
    ds_src_s0 = ds_src.create("s0")
    ds_src_s1 = ds_src_s0.create("s1")
    ds_src.save(recursive=True)
    if on_adjusted:
        # Note: We adjust after creating all the datasets above to avoid a bug
        # fixed in git-annex 7.20191024, specifically bbdeb1a1a (sync: Fix
        # crash when there are submodules and an adjusted branch is checked
        # out, 2019-10-23).
        for ds in [ds_src, ds_src_s0, ds_src_s1]:
            maybe_adjust_repo(ds.repo)
        ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_s1 = Dataset(ds_clone.pathobj / "s0" / "s1")

    ds_src_s1.repo.checkout(DEFAULT_BRANCH + "^0")
    (ds_src_s1.pathobj / "foo").write_text("foo content")
    ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    res = ds_clone.update(merge=True, recursive=True, follow="parentds",
                          on_failure="ignore")
    if on_adjusted:
        # The top-level update is okay because there is no parent revision to
        # update to.
        assert_in_results(
            res,
            status="ok",
            path=ds_clone.path,
            action="update")
        # The subdataset, on the other hand, is impossible.
        assert_in_results(
            res,
            status="impossible",
            path=ds_clone_s1.path,
            action="update")
        return
    assert_repo_status(ds_clone.path)

    # We brought in the revision and got to the same state of the remote.
    # Blind saving here without bringing in the current subdataset revision
    # would have resulted in a new commit in ds_clone that reverting the
    # last subdataset ID recorded in ds_src.
    eq_(ds_clone.repo.get_hexsha(), ds_src.repo.get_hexsha())

    # Record a revision in the parent and then move HEAD away from it so that
    # the explicit revision fetch fails.
    (ds_src_s1.pathobj / "bar").write_text("bar content")
    ds_src.save(recursive=True)
    ds_src_s1.repo.checkout(DEFAULT_BRANCH)
    # This is the default, but just in case:
    ds_src_s1.repo.config.set("uploadpack.allowAnySHA1InWant", "false",
                              scope="local")
    # Configure the fetcher to use v0 because Git defaults to v2 as of
    # v2.26.0, which allows fetching unadvertised objects regardless
    # of the value of uploadpack.allowAnySHA1InWant.
    ds_clone_s1.repo.config.set("protocol.version", "0", scope="local")
    res = ds_clone.update(merge=True, recursive=True, follow="parentds",
                          on_failure="ignore")
    # The fetch with the explicit ref fails because it isn't advertised.
    assert_in_results(
        res,
        status="impossible",
        path=ds_clone_s1.path,
        action="update")

    # Back to the detached head.
    ds_src_s1.repo.checkout("HEAD@{1}")
    # Set up a case where update() will not resolve the sibling.
    ds_clone_s1.repo.call_git(["branch", "--unset-upstream"])
    ds_clone_s1.config.reload(force=True)
    ds_clone_s1.repo.call_git(["remote", "add", "other", ds_src_s1.path])
    res = ds_clone.update(recursive=True, follow="parentds",
                          on_failure="ignore")
    # In this case, update() won't abort if we call with merge=False, but
    # it does if the revision wasn't brought down in the `fetch(all_=True)`
    # call.
    assert_in_results(
        res,
        status="impossible",
        path=ds_clone_s1.path,
        action="update")


@with_tempfile(mkdir=True)
def test_update_unborn_master(path=None):
    ds_a = Dataset(op.join(path, "ds-a")).create()
    ds_a.repo.call_git(["branch", "-m", DEFAULT_BRANCH, "other"])
    ds_a.repo.checkout(DEFAULT_BRANCH, options=["--orphan"])
    ds_b = install(source=ds_a.path, path=op.join(path, "ds-b"))

    ds_a.repo.checkout("other")
    (ds_a.pathobj / "foo").write_text("content")
    ds_a.save()

    # clone() will try to switch away from an unborn branch if there
    # is another ref available.  Reverse these efforts so that we can
    # test that update() fails reasonably here because we should still
    # be able to update from remotes that datalad didn't clone.
    ds_b.repo.update_ref("HEAD", "refs/heads/" + DEFAULT_BRANCH,
                         symbolic=True)
    assert_false(ds_b.repo.commit_exists("HEAD"))
    assert_status("impossible",
                  ds_b.update(merge=True, on_failure="ignore"))

    ds_b.repo.checkout("other")
    assert_status("ok",
                  ds_b.update(merge=True, on_failure="ignore"))
    eq_(ds_a.repo.get_hexsha(), ds_b.repo.get_hexsha())


@slow  # ~25s
@with_tempfile(mkdir=True)
def test_update_follow_parentds_lazy(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    ds_src_s0 = ds_src.create("s0")
    ds_src_s0_s0 = ds_src_s0.create("s0")
    ds_src_s0.create("s1")
    ds_src_s1 = ds_src.create("s1")
    ds_src.create("s2")
    ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_clone_s0 = Dataset(ds_clone.pathobj / "s0")
    ds_clone_s0_s0 = Dataset(ds_clone.pathobj / "s0" / "s0")
    ds_clone_s0_s1 = Dataset(ds_clone.pathobj / "s0" / "s1")
    ds_clone_s1 = Dataset(ds_clone.pathobj / "s1")
    ds_clone_s2 = Dataset(ds_clone.pathobj / "s2")

    (ds_src_s0_s0.pathobj / "foo").write_text("in s0 s0")
    ds_src_s0_s0.save()
    (ds_src_s1.pathobj / "foo").write_text("in s1")
    ds_src.save(recursive=True)
    # State:
    # .
    # |-- s0
    # |   |-- s0
    # |   `-- s1  * matches registered commit
    # |-- s1
    # `-- s2      * matches registered commit
    res = ds_clone.update(follow="parentds-lazy", merge=True, recursive=True,
                          on_failure="ignore")
    on_adjusted = ds_clone.repo.is_managed_branch()
    # For adjusted branches, follow=parentds* bails with an impossible result,
    # so the s0 update doesn't get brought in and s0_s0 also matches the
    # registered commit.
    n_notneeded_expected = 3 if on_adjusted else 2
    assert_result_count(res, n_notneeded_expected,
                        action="update", status="notneeded")
    assert_in_results(res, action="update", status="notneeded",
                      path=ds_clone_s0_s1.repo.path)
    assert_in_results(res, action="update", status="notneeded",
                      path=ds_clone_s2.repo.path)
    if on_adjusted:
        assert_in_results(res, action="update", status="notneeded",
                          path=ds_clone_s0_s0.repo.path)
        assert_repo_status(ds_clone.path,
                           modified=[ds_clone_s0.repo.path,
                                     ds_clone_s1.repo.path])
    else:
        assert_repo_status(ds_clone.path)


@slow  # ~10s
@with_tempfile(mkdir=True)
def test_update_follow_parentds_lazy_other_branch(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    ds_src_sub = ds_src.create("sub")
    ds_src_sub.repo.checkout(DEFAULT_BRANCH, options=["-bother"])
    (ds_src_sub.pathobj / "foo").write_text("on other branch")
    ds_src_sub.save()
    ds_src_sub.repo.checkout(DEFAULT_BRANCH)
    ds_src.save(recursive=True)
    assert_repo_status(ds_src.path)

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    ds_src_sub.repo.checkout("other")
    ds_src.save(recursive=True)

    with patch("datalad.support.gitrepo.GitRepo.fetch") as fetch_cmd:
        ds_clone.update(follow="parentds", merge="ff-only",
                        recursive=True, on_failure="ignore")
        eq_(fetch_cmd.call_count, 2)

    # With parentds-lazy, an unneeded fetch call in the subdataset is dropped.
    with patch("datalad.support.gitrepo.GitRepo.fetch") as fetch_cmd:
        ds_clone.update(follow="parentds-lazy", merge="ff-only",
                        recursive=True, on_failure="ignore")
        eq_(fetch_cmd.call_count, 1)

    if not ds_clone.repo.is_managed_branch():
        # Now the real thing.
        ds_clone.update(follow="parentds-lazy", merge="ff-only",
                        recursive=True)
        ok_(op.lexists(str(ds_clone.pathobj / "sub" / "foo")))


@with_tempfile(mkdir=True)
def test_update_adjusted_incompatible_with_ff_only(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    maybe_adjust_repo(ds_clone.repo)

    assert_in_results(
        ds_clone.update(merge="ff-only", on_failure="ignore"),
        action="update", status="impossible")
    assert_in_results(
        ds_clone.update(on_failure="ignore"),
        action="update", status="ok")


@pytest.mark.parametrize("follow,action", [
    # Ideally each combination would be checked, but this test is a bit slow.
    ("parentds", "reset"),
    ("sibling", "checkout"),
])
@slow  # ~10s
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_update_how_subds_different(path=None, *, follow, action):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    ds_src_sub = ds_src.create("sub")
    ds_src.save()

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")
    (ds_clone.pathobj / "foo").write_text("foo")
    ds_clone.save()
    ds_clone_sub = Dataset(ds_clone.pathobj / "sub")

    (ds_src_sub.pathobj / "bar").write_text("bar")
    ds_src.save(recursive=True)

    # Add unrecorded state to make --follow=sibling/parentds differ.
    (ds_src_sub.pathobj / "baz").write_text("baz")
    ds_src_sub.save()

    ds_clone_repo = ds_clone.repo
    ds_clone_hexsha_pre = ds_clone_repo.get_hexsha()

    ds_clone_sub_repo = ds_clone_sub.repo
    ds_clone_sub_branch_pre = ds_clone_sub_repo.get_active_branch()

    res = ds_clone.update(follow=follow, how="merge", how_subds=action,
                          recursive=True)

    assert_result_count(res, 1, action="merge", status="ok",
                        path=ds_clone.path)
    assert_result_count(res, 1, action=f"update.{action}", status="ok",
                        path=ds_clone_sub.path)

    ds_clone_hexsha_post = ds_clone_repo.get_hexsha()
    neq_(ds_clone_hexsha_pre, ds_clone_hexsha_post)
    neq_(ds_src.repo.get_hexsha(), ds_clone_hexsha_post)
    ok_(ds_clone_repo.is_ancestor(ds_clone_hexsha_pre, ds_clone_hexsha_post))

    eq_(ds_clone_sub.repo.get_hexsha(),
        ds_src_sub.repo.get_hexsha(None if follow == "sibling" else "HEAD~"))
    ds_clone_sub_branch_post = ds_clone_sub_repo.get_active_branch()

    if action == "checkout":
        neq_(ds_clone_sub_branch_pre, ds_clone_sub_branch_post)
        assert_false(ds_clone_sub_branch_post)
    else:
        eq_(ds_clone_sub_branch_pre, ds_clone_sub_branch_post)


@slow  # ~15s
@skip_if_adjusted_branch
@with_tempfile(mkdir=True)
def test_update_reset_dirty(path=None):
    path = Path(path)
    ds_src = Dataset(path / "source").create()
    ds_src_s1 = ds_src.create("s1")
    ds_src_s2 = ds_src.create("s2")
    ds_src.save()

    ds_clone = install(source=ds_src.path, path=path / "clone",
                       recursive=True, result_xfm="datasets")

    (ds_src_s1.pathobj / "foo").write_text("foo")
    (ds_src_s2.pathobj / "bar").write_text("bar")
    ds_src.save(recursive=True)

    ds_clone_s1 = Dataset(ds_clone.pathobj / "s1")
    ds_clone_s2 = Dataset(ds_clone.pathobj / "s2")
    (ds_clone_s1.pathobj / "dirt").write_text("")

    res = ds_clone.update(follow="sibling", how="reset", recursive=True,
                          on_failure="ignore")

    assert_result_count(res, 1, path=ds_clone.path,
                        action=f"update.reset", status="error")
    assert_result_count(res, 1, path=ds_clone_s1.path,
                        action=f"update.reset", status="error")
    assert_result_count(res, 1, path=ds_clone_s2.path,
                        action=f"update.reset", status="ok")

    # s2 was reset...
    eq_(ds_src_s2.repo.get_hexsha(), ds_clone_s2.repo.get_hexsha())
    # ... but s1 and the top-level dataset stayed behind due to the dirty tree.
    eq_(ds_src.repo.get_hexsha("HEAD~"), ds_clone.repo.get_hexsha())
    eq_(ds_src_s1.repo.get_hexsha("HEAD~"), ds_clone_s1.repo.get_hexsha())

    assert_repo_status(ds_clone.path,
                       modified=[ds_clone_s1.repo.path,
                                 ds_clone_s2.repo.path])


def test_process_how_args():
    # --merge maps onto --how values. It has no equivalent of --how-subds,
    # --which just gets set to --how's value when unspecified.
    eq_(_process_how_args(merge=False, how=None, how_subds=None),
        (None, None))
    eq_(_process_how_args(merge=True, how=None, how_subds=None),
        ("merge", "merge"))
    eq_(_process_how_args(merge="any", how=None, how_subds=None),
        ("merge", "merge"))
    eq_(_process_how_args(merge="ff-only", how=None, how_subds=None),
        ("ff-only", "ff-only"))

    # Values other than the default --merge=False can not be mixed with
    # non-default how values.
    with assert_raises(ValueError):
        _process_how_args(merge=True, how="merge", how_subds=None)
    with assert_raises(ValueError):
        _process_how_args(merge=True, how=None, how_subds="merge")

    # --how-subds inherits the value of --how...
    eq_(_process_how_args(merge=False, how="fetch", how_subds=None),
        (None, None))
    eq_(_process_how_args(merge=False, how="merge", how_subds=None),
        ("merge", "merge"))
    eq_(_process_how_args(merge=False, how="ff-only", how_subds=None),
        ("ff-only", "ff-only"))
    # ... unless --how-subds is explicitly specified.
    eq_(_process_how_args(merge=False, how="merge", how_subds="fetch"),
        ("merge", None))


@with_tempfile(mkdir=True)
def test_update_fetch_failure(path=None):
    path = Path(path)

    ds_a = Dataset(path / "ds_a").create()
    s1 = ds_a.create("s1")
    ds_a.create("s2")

    ds_b = install(source=ds_a.path, path=str(path / "ds-b"), recursive=True)

    # Rename s1 to make fetch fail.
    s1.pathobj.rename(s1.pathobj.parent / "s3")

    res = ds_b.update(recursive=True, on_failure="ignore")
    assert_in_results(
        res,
        status="error",
        path=str(ds_b.pathobj / "s1"),
        action="update")
    assert_in_results(
        res,
        status="ok",
        path=str(ds_b.pathobj / "s2"),
        action="update")
    assert_in_results(
        res,
        status="ok",
        path=ds_b.path,
        action="update")
