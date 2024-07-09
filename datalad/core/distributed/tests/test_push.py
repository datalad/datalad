# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test push

"""

import logging
import os

import pytest

from datalad.core.distributed.clone import Clone
from datalad.core.distributed.push import Push
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    IncompleteResultsError,
    InsufficientArgumentsError,
)
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import GitRepo
from datalad.support.network import get_local_file_url
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_not_in_results,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    known_failure_githubci_osx,
    known_failure_githubci_win,
    neq_,
    ok_,
    ok_file_has_content,
    serve_path_via_http,
    skip_if_adjusted_branch,
    skip_if_on_windows,
    skip_ssh,
    slow,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
    path_startswith,
    swallow_outputs,
)

DEFAULT_REFSPEC = "refs/heads/{0}:refs/heads/{0}".format(DEFAULT_BRANCH)

ckwa = dict(
    result_renderer='disabled',
)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_invalid_call(origin=None, tdir=None):
    ds = Dataset(origin).create()
    # no target
    assert_status('impossible', ds.push(on_failure='ignore'))
    # no dataset
    with chpwd(tdir):
        assert_raises(InsufficientArgumentsError, Push.__call__)
    # dataset, but outside path
    assert_raises(IncompleteResultsError, ds.push, path=tdir)
    # given a path constraint that doesn't match anything, will cause
    # nothing to be done
    assert_status('notneeded', ds.push(path=ds.pathobj / 'nothere'))

    # unavailable subdataset
    dummy_sub = ds.create('sub')
    dummy_sub.drop(what='all', reckless='kill', recursive=True)
    assert_in('sub', ds.subdatasets(state='absent', result_xfm='relpaths'))
    # now an explicit call to publish the unavailable subdataset
    assert_raises(ValueError, ds.push, 'sub')

    target = mk_push_target(ds, 'target', tdir, annex=True)
    # revision that doesn't exist
    assert_raises(
        ValueError,
        ds.push, to='target', since='09320957509720437523')

    # If a publish() user accidentally passes since='', which push() spells as
    # since='^', the call is aborted.
    assert_raises(
        ValueError,
        ds.push, to='target', since='')


def mk_push_target(ds, name, path, annex=True, bare=True):
    # life could be simple, but nothing is simple on windows
    #src.create_sibling(dst_path, name='target')
    if annex:
        if bare:
            target = GitRepo(path=path, bare=True, create=True)
            # cannot use call_annex()
            target.call_git(['annex', 'init'])
        else:
            target = AnnexRepo(path, init=True, create=True)
            if not target.is_managed_branch():
                # for managed branches we need more fireworks->below
                target.config.set(
                    'receive.denyCurrentBranch', 'updateInstead',
                    scope='local')
    else:
        target = GitRepo(path=path, bare=bare, create=True)
    ds.siblings('add', name=name, url=path, result_renderer='disabled')
    if annex and not bare and target.is_managed_branch():
        # maximum complication
        # the target repo already has a commit that is unrelated
        # to the source repo, because it has built a reference
        # commit for the managed branch.
        # the only sane approach is to let git-annex establish a shared
        # history
        if AnnexRepo.git_annex_version > "8.20210631":
            ds.repo.call_annex(['sync', '--allow-unrelated-histories'])
        else:
            ds.repo.call_annex(['sync'])
        ds.repo.call_annex(['sync', '--cleanup'])
    return target


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def check_push(annex, src_path, dst_path):
    # prepare src
    src = Dataset(src_path).create(annex=annex)
    src_repo = src.repo
    # push should not add branches to the local dataset
    orig_branches = src_repo.get_branches()
    assert_not_in('synced/' + DEFAULT_BRANCH, orig_branches)

    res = src.push(on_failure='ignore')
    assert_result_count(res, 1)
    assert_in_results(
        res, status='impossible',
        message='No push target given, and none could be auto-detected, '
        'please specify via --to')
    eq_(orig_branches, src_repo.get_branches())
    # target sibling
    target = mk_push_target(src, 'target', dst_path, annex=annex)
    eq_(orig_branches, src_repo.get_branches())

    res = src.push(to="target")
    eq_(orig_branches, src_repo.get_branches())
    assert_result_count(res, 2 if annex else 1)
    assert_in_results(
        res,
        action='publish', status='ok', target='target',
        refspec=DEFAULT_REFSPEC,
        operations=['new-branch'])

    assert_repo_status(src_repo, annex=annex)
    eq_(list(target.get_branch_commits_(DEFAULT_BRANCH)),
        list(src_repo.get_branch_commits_(DEFAULT_BRANCH)))

    # configure a default merge/upstream target
    src.config.set('branch.{}.remote'.format(DEFAULT_BRANCH),
                   'target', scope='local')
    src.config.set('branch.{}.merge'.format(DEFAULT_BRANCH),
                   DEFAULT_BRANCH, scope='local')

    # don't fail when doing it again, no explicit target specification
    # needed anymore
    res = src.push()
    eq_(orig_branches, src_repo.get_branches())
    # and nothing is pushed
    assert_status('notneeded', res)

    assert_repo_status(src_repo, annex=annex)
    eq_(list(target.get_branch_commits_(DEFAULT_BRANCH)),
        list(src_repo.get_branch_commits_(DEFAULT_BRANCH)))

    # some modification:
    (src.pathobj / 'test_mod_file').write_text("Some additional stuff.")
    src.save(to_git=True, message="Modified.")
    (src.pathobj / 'test_mod_annex_file').write_text("Heavy stuff.")
    src.save(to_git=not annex, message="Modified again.")
    assert_repo_status(src_repo, annex=annex)

    # we could say since='HEAD~2' to make things fast, or we are lazy
    # and say since='^' to indicate the state of the tracking remote
    # which is the same, because we made to commits since the last push.
    res = src.push(to='target', since="^", jobs=2)
    assert_in_results(
        res,
        action='publish', status='ok', target='target',
        refspec=DEFAULT_REFSPEC,
        # we get to see what happened
        operations=['fast-forward'])
    if annex:
        # we got to see the copy result for the annexed files
        assert_in_results(
            res,
            action='copy',
            status='ok',
            path=str(src.pathobj / 'test_mod_annex_file'))
        # we published, so we can drop and reobtain
        ok_(src_repo.file_has_content('test_mod_annex_file'))
        src_repo.drop('test_mod_annex_file')
        ok_(not src_repo.file_has_content('test_mod_annex_file'))
        src_repo.get('test_mod_annex_file')
        ok_(src_repo.file_has_content('test_mod_annex_file'))
        ok_file_has_content(
            src_repo.pathobj / 'test_mod_annex_file',
            'Heavy stuff.')

    eq_(list(target.get_branch_commits_(DEFAULT_BRANCH)),
        list(src_repo.get_branch_commits_(DEFAULT_BRANCH)))
    if not (annex and src_repo.is_managed_branch()):
        # the following doesn't make sense in managed branches, because
        # a commit that could be amended is no longer the last commit
        # of a branch after a sync has happened (which did happen
        # during the last push above

        # amend and change commit msg in order to test for force push:
        src_repo.commit("amended", options=['--amend'])
        # push should be rejected (non-fast-forward):
        res = src.push(to='target', since='HEAD~2', on_failure='ignore')
        # fails before even touching the annex branch
        assert_in_results(
            res,
            action='publish', status='error', target='target',
            refspec=DEFAULT_REFSPEC,
            operations=['rejected', 'error'])
        # push with force=True works:
        res = src.push(to='target', since='HEAD~2', force='gitpush')
        assert_in_results(
            res,
            action='publish', status='ok', target='target',
            refspec=DEFAULT_REFSPEC,
            operations=['forced-update'])
        eq_(list(target.get_branch_commits_(DEFAULT_BRANCH)),
            list(src_repo.get_branch_commits_(DEFAULT_BRANCH)))

    # we do not have more branches than we had in the beginning
    # in particular no 'synced/<default branch>'
    eq_(orig_branches, src_repo.get_branches())


@pytest.mark.parametrize("annex", [False, True])
def test_push(annex):
    check_push(annex)


def check_datasets_order(res, order='bottom-up'):
    """Check that all type=dataset records not violating the expected order

    it is somewhat weak test, i.e. records could be produced so we
    do not detect that order is violated, e.g. a/b c/d would satisfy
    either although they might be neither depth nor breadth wise.  But
    this test would allow to catch obvious violations like a, a/b, a
    """
    prev = None
    for r in res:
        if r.get('type') != 'dataset':
            continue
        if prev and r['path'] != prev:
            if order == 'bottom-up':
                assert_false(path_startswith(r['path'], prev))
            elif order == 'top-down':
                assert_false(path_startswith(prev, r['path']))
            else:
                raise ValueError(order)
        prev = r['path']


@slow  # 33sec on Yarik's laptop
@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True, suffix='sub')
@with_tempfile(mkdir=True, suffix='subnoannex')
@with_tempfile(mkdir=True, suffix='subsub')
def test_push_recursive(
        origin_path=None, src_path=None, dst_top=None, dst_sub=None, dst_subnoannex=None, dst_subsub=None):
    # dataset with two submodules and one subsubmodule
    origin = Dataset(origin_path).create()
    origin_subm1 = origin.create('sub m')
    origin_subm1.create('subsub m')
    origin.create('subm noannex', annex=False)
    origin.save()
    assert_repo_status(origin.path)
    # prepare src as a fresh clone with all subdatasets checkout out recursively
    # running on a clone should make the test scenario more different than
    # test_push(), even for the pieces that should be identical
    top = Clone.__call__(source=origin.path, path=src_path)
    subs = top.get('.', recursive=True, get_data=False, result_xfm='datasets')
    # order for '.' should not be relied upon, so sort by path
    sub, subsub, subnoannex = sorted(subs, key=lambda ds: ds.path)

    target_top = mk_push_target(top, 'target', dst_top, annex=True)
    # subdatasets have no remote yet, so recursive publishing should fail:
    res = top.push(to="target", recursive=True, on_failure='ignore')
    check_datasets_order(res)
    assert_in_results(
        res, path=top.path, type='dataset',
        refspec=DEFAULT_REFSPEC,
        operations=['new-branch'], action='publish', status='ok',
        target='target')
    for d in (sub, subsub, subnoannex):
        assert_in_results(
            res, status='error', type='dataset', path=d.path,
            message=("Unknown target sibling '%s'.",
                     'target'))
    # now fix that and set up targets for the submodules
    target_sub = mk_push_target(sub, 'target', dst_sub, annex=True)
    target_subnoannex = mk_push_target(
        subnoannex, 'target', dst_subnoannex, annex=False)
    target_subsub = mk_push_target(subsub, 'target', dst_subsub, annex=True)

    # and same push call as above
    res = top.push(to="target", recursive=True)
    check_datasets_order(res)
    # topds skipped
    assert_in_results(
        res, path=top.path, type='dataset',
        action='publish', status='notneeded', target='target')
    # the rest pushed
    for d in (sub, subsub, subnoannex):
        assert_in_results(
            res, status='ok', type='dataset', path=d.path,
            refspec=DEFAULT_REFSPEC)
    # all corresponding branches match across all datasets
    for s, d in zip((top, sub, subnoannex, subsub),
                    (target_top, target_sub, target_subnoannex,
                     target_subsub)):
        eq_(list(s.repo.get_branch_commits_(DEFAULT_BRANCH)),
            list(d.get_branch_commits_(DEFAULT_BRANCH)))
        if s != subnoannex:
            eq_(list(s.repo.get_branch_commits_("git-annex")),
                list(d.get_branch_commits_("git-annex")))

    # rerun should not result in further pushes of the default branch
    res = top.push(to="target", recursive=True)
    check_datasets_order(res)
    assert_not_in_results(
        res, status='ok', refspec=DEFAULT_REFSPEC)
    assert_in_results(
        res, status='notneeded', refspec=DEFAULT_REFSPEC)

    # now annex a file in subsub
    test_copy_file = subsub.pathobj / 'test_mod_annex_file'
    test_copy_file.write_text("Heavy stuff.")
    # save all the way up
    assert_status(
        ('ok', 'notneeded'),
        top.save(message='subsub got something', recursive=True))
    assert_repo_status(top.path)
    # publish straight up, should be smart by default
    res = top.push(to="target", recursive=True)
    check_datasets_order(res)
    # we see 3 out of 4 datasets pushed (sub noannex was left unchanged)
    for d in (top, sub, subsub):
        assert_in_results(
            res, status='ok', type='dataset', path=d.path,
            refspec=DEFAULT_REFSPEC)
    # file content copied too
    assert_in_results(
        res,
        action='copy',
        status='ok',
        path=str(test_copy_file))
    # verify it is accessible, drop and bring back
    assert_status('ok', top.drop(str(test_copy_file)))
    ok_(not subsub.repo.file_has_content('test_mod_annex_file'))
    top.get(test_copy_file)
    ok_file_has_content(test_copy_file, 'Heavy stuff.')

    # make two modification
    (sub.pathobj / 'test_mod_annex_file').write_text('annex')
    (subnoannex.pathobj / 'test_mod_file').write_text('git')
    # save separately
    top.save(sub.pathobj, message='annexadd', recursive=True)
    top.save(subnoannex.pathobj, message='gitadd', recursive=True)
    # now only publish the latter one
    res = top.push(to="target", since=DEFAULT_BRANCH + '~1', recursive=True)
    # nothing copied, no reports on the other modification
    assert_not_in_results(res, action='copy')
    assert_not_in_results(res, path=sub.path)
    for d in (top, subnoannex):
        assert_in_results(
            res, status='ok', type='dataset', path=d.path,
            refspec=DEFAULT_REFSPEC)
    # an unconditional push should now pick up the remaining changes
    res = top.push(to="target", recursive=True)
    assert_in_results(
        res,
        action='copy',
        status='ok',
        path=str(sub.pathobj / 'test_mod_annex_file'))
    assert_in_results(
        res, status='ok', type='dataset', path=sub.path,
        refspec=DEFAULT_REFSPEC)
    for d in (top, subnoannex, subsub):
        assert_in_results(
            res, status='notneeded', type='dataset', path=d.path,
            refspec=DEFAULT_REFSPEC)

    # if noannex target gets some annex, we still should not fail to push
    target_subnoannex.call_git(['annex', 'init'])
    # just to ensure that we do need something to push
    (subnoannex.pathobj / "newfile").write_text("content")
    subnoannex.save()
    res = subnoannex.push(to="target")
    assert_in_results(res, status='ok', type='dataset')


@slow  # 12sec on Yarik's laptop
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_push_subds_no_recursion(src_path=None, dst_top=None, dst_sub=None, dst_subsub=None):
    # dataset with one submodule and one subsubmodule
    top = Dataset(src_path).create()
    sub = top.create('sub m')
    test_file = sub.pathobj / 'subdir' / 'test_file'
    test_file.parent.mkdir()
    test_file.write_text('some')
    subsub = sub.create(sub.pathobj / 'subdir' / 'subsub m')
    top.save(recursive=True)
    assert_repo_status(top.path)
    target_top = mk_push_target(top, 'target', dst_top, annex=True)
    target_sub = mk_push_target(sub, 'target', dst_sub, annex=True)
    target_subsub = mk_push_target(subsub, 'target', dst_subsub, annex=True)
    # now publish, but NO recursion, instead give the parent dir of
    # both a subdataset and a file in the middle subdataset
    res = top.push(
        to='target',
        # give relative to top dataset to elevate the difficulty a little
        path=str(test_file.relative_to(top.pathobj).parent))
    assert_status('ok', res)
    assert_in_results(res, action='publish', type='dataset', path=top.path)
    assert_in_results(res, action='publish', type='dataset', path=sub.path)
    assert_in_results(res, action='copy', type='file', path=str(test_file))
    # the lowest-level subdataset isn't touched
    assert_not_in_results(
        res, action='publish', type='dataset', path=subsub.path)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_force_checkdatapresent(srcpath=None, dstpath=None):
    src = Dataset(srcpath).create()
    target = mk_push_target(src, 'target', dstpath, annex=True, bare=True)
    (src.pathobj / 'test_mod_annex_file').write_text("Heavy stuff.")
    src.save(to_git=False, message="New annex file")
    assert_repo_status(src.path, annex=True)
    whereis_prior = src.repo.whereis(files=['test_mod_annex_file'])[0]

    res = src.push(to='target', data='nothing')
    # nothing reported to be copied
    assert_not_in_results(res, action='copy')
    # we got the git-push nevertheless
    eq_(src.repo.get_hexsha(DEFAULT_BRANCH), target.get_hexsha(DEFAULT_BRANCH))
    # nothing moved
    eq_(whereis_prior, src.repo.whereis(files=['test_mod_annex_file'])[0])

    # now a push without forced no-transfer
    # we do not give since, so the non-transfered file is picked up
    # and transferred
    annex_branch_state = src.repo.get_hexsha('git-annex')
    res = src.push(to='target', force=None)
    # no branch change, done before
    assert_in_results(res, action='publish', status='notneeded',
                      refspec=DEFAULT_REFSPEC)
    # but availability update
    # reflected as a change in git-annex branch
    assert annex_branch_state != src.repo.get_hexsha('git-annex')
    # and identical state here and on the remote
    assert src.repo.get_hexsha('git-annex') == src.repo.get_hexsha('target/git-annex')

    # as a result of [10.20231129-84-geb59da9dd2](https://git.kitenet.net/index.cgi/git-annex.git/commit/?id=HEAD)
    # which makes git-annex clocks less precise, the git-annex branch change on the remote as a result of
    # `annex copy` has exactly the same content and timestamp in git-annex branch, so the same commit as local,
    # so when we fetch updates from the remote, we end up on the same commit instead of merging
    # updated availability with difference in timestamp within git-annex branch of minuscule difference
    try:
        assert_in_results(res, action='publish', status='notneeded',
                          refspec='refs/heads/git-annex:refs/heads/git-annex')
    except AssertionError:
        # before then -- we would report that update was pushed since update had a
        # slightly different git-annex timestamp locally from the remote, and thus commits
        # were different
        assert_in_results(res, action='publish', status='ok',
                          refspec='refs/heads/git-annex:refs/heads/git-annex')

    assert_in_results(res, status='ok',
                      path=str(src.pathobj / 'test_mod_annex_file'),
                      action='copy')
    # whereis info reflects the change
    ok_(len(whereis_prior) < len(
        src.repo.whereis(files=['test_mod_annex_file'])[0]))

    # do it yet again will do nothing, because all is up-to-date
    assert_status('notneeded', src.push(to='target', force=None))
    # an explicit reference point doesn't change that
    assert_status('notneeded',
                  src.push(to='target', force=None, since='HEAD~1'))

    # now force data transfer
    res = src.push(to='target', force='checkdatapresent')
    # no branch change, done before
    assert_in_results(res, action='publish', status='notneeded',
                      refspec=DEFAULT_REFSPEC)
    # no availability update
    assert_in_results(res, action='publish', status='notneeded',
                      refspec='refs/heads/git-annex:refs/heads/git-annex')
    # but data transfer
    assert_in_results(res, status='ok',
                      path=str(src.pathobj / 'test_mod_annex_file'),
                      action='copy')

    # force data transfer, but data isn't available
    src.repo.drop('test_mod_annex_file')
    res = src.push(to='target', path='.', force='checkdatapresent', on_failure='ignore')
    assert_in_results(res, status='impossible',
                      path=str(src.pathobj / 'test_mod_annex_file'),
                      action='copy',
                      message='Slated for transport, but no content present')


@known_failure_githubci_win  # recent git-annex, https://github.com/datalad/datalad/issues/7185
@with_tempfile(mkdir=True)
@with_tree(tree={'ria-layout-version': '1\n'})
def test_ria_push(srcpath=None, dstpath=None):
    # complex test involving a git remote, a special remote, and a
    # publication dependency
    src = Dataset(srcpath).create()
    testfile = src.pathobj / 'test_mod_annex_file'
    testfile.write_text("Heavy stuff.")
    src.save()
    assert_status(
        'ok',
        src.create_sibling_ria(
            "ria+{}".format(get_local_file_url(dstpath, compatibility='git')),
            "datastore", new_store_ok=True))
    res = src.push(to='datastore')
    assert_in_results(
        res, action='publish', target='datastore', status='ok',
        refspec=DEFAULT_REFSPEC)
    assert_in_results(
        res, action='publish', target='datastore', status='ok',
        refspec='refs/heads/git-annex:refs/heads/git-annex')
    assert_in_results(
        res, action='copy', target='datastore-storage', status='ok',
        path=str(testfile))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_gh1426(origin_path=None, target_path=None):
    # set up a pair of repos, one the published copy of the other
    origin = Dataset(origin_path).create()
    target = mk_push_target(
        origin, 'target', target_path, annex=True, bare=False)
    origin.push(to='target')
    assert_repo_status(origin.path)
    assert_repo_status(target.path)
    eq_(origin.repo.get_hexsha(DEFAULT_BRANCH),
        target.get_hexsha(DEFAULT_BRANCH))

    # gist of #1426 is that a newly added subdataset does not cause the
    # superdataset to get published
    origin.create('sub')
    assert_repo_status(origin.path)
    neq_(origin.repo.get_hexsha(DEFAULT_BRANCH),
         target.get_hexsha(DEFAULT_BRANCH))
    # now push
    res = origin.push(to='target')
    assert_result_count(
        res, 1, status='ok', type='dataset', path=origin.path,
        action='publish', target='target', operations=['fast-forward'])
    eq_(origin.repo.get_hexsha(DEFAULT_BRANCH),
        target.get_hexsha(DEFAULT_BRANCH))


@skip_if_adjusted_branch  # gh-4075
@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tree(tree={'1': '123'})
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_publish_target_url(src=None, desttop=None, desturl=None):
    # https://github.com/datalad/datalad/issues/1762
    ds = Dataset(src).create(force=True)
    ds.save('1')
    ds.create_sibling('ssh://datalad-test:%s/subdir' % desttop,
                      name='target',
                      target_url=desturl + 'subdir/.git')
    results = ds.push(to='target')
    assert results
    ok_file_has_content(Path(desttop, 'subdir', '1'), '123')


@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
@with_tempfile()
def test_gh1763(src=None, target1=None, target2=None, target3=None):
    # this test is very similar to test_publish_depends, but more
    # comprehensible, and directly tests issue 1763
    src = Dataset(src).create(force=True, **ckwa)
    targets = [
        mk_push_target(src, f'target{i}', t, bare=False)
        for i, t in enumerate([target1, target2, target3])
    ]
    src.siblings('configure', name='target0',
                 publish_depends=['target1', 'target2'],
                 **ckwa)
    # a file to annex
    (src.pathobj / 'probe1').write_text('probe1')
    src.save('probe1', to_git=False, **ckwa)
    # make sure the probe is annexed, not straight in Git
    assert_in('probe1', src.repo.get_annexed_files(with_content_only=True))
    # publish to target0, must handle dependency
    src.push(to='target0', **ckwa)
    for target in targets:
        # with a managed branch we are pushing into the corresponding branch
        # and do not see a change in the worktree
        if not target.is_managed_branch():
            # direct test for what is in the checkout
            assert_in(
                'probe1',
                target.get_annexed_files(with_content_only=True))
        # ensure git-annex knows this target has the file
        assert_in(target.config.get('annex.uuid'),
                  src.repo.whereis(['probe1'])[0])


@with_tempfile()
@with_tempfile()
def test_gh1811(srcpath=None, clonepath=None):
    orig = Dataset(srcpath).create()
    (orig.pathobj / 'some').write_text('some')
    orig.save()
    clone = Clone.__call__(source=orig.path, path=clonepath)
    (clone.pathobj / 'somemore').write_text('somemore')
    clone.save()
    clone.repo.call_git(['checkout', 'HEAD~1'])
    res = clone.push(to=DEFAULT_REMOTE, on_failure='ignore')
    assert_result_count(res, 1)
    assert_result_count(
        res, 1,
        path=clone.path, type='dataset', action='publish',
        status='impossible',
        message='There is no active branch, cannot determine remote '
                'branch',
    )


# FIXME: on crippled FS post-update hook enabling via create-sibling doesn't
# work ATM
@skip_if_adjusted_branch
@with_tempfile()
@with_tempfile()
def test_push_wanted(srcpath=None, dstpath=None):
    src = Dataset(srcpath).create()
    (src.pathobj / 'data.0').write_text('0')
    (src.pathobj / 'secure.1').write_text('1')
    (src.pathobj / 'secure.2').write_text('2')
    src.save()

    # Dropping a file to mimic a case of simply not having it locally (thus not
    # to be "pushed")
    src.drop('secure.2', reckless='kill')

    # Annotate sensitive content, actual value "verysecure" does not matter in
    # this example
    src.repo.set_metadata(
        add={'distribution-restrictions': 'verysecure'},
        files=['secure.1', 'secure.2'])

    src.create_sibling(
        dstpath,
        annex_wanted="not metadata=distribution-restrictions=*",
        name='target',
    )
    # check that wanted is obeyed, since set in sibling configuration
    res = src.push(to='target')
    assert_in_results(
        res, action='copy', path=str(src.pathobj / 'data.0'), status='ok')
    for p in ('secure.1', 'secure.2'):
        assert_not_in_results(res, path=str(src.pathobj / p))
    assert_status('notneeded', src.push(to='target'))

    # check the target to really make sure
    dst = Dataset(dstpath)
    # normal file, yes
    eq_((dst.pathobj / 'data.0').read_text(), '0')
    # secure file, no
    if dst.repo.is_managed_branch():
        neq_((dst.pathobj / 'secure.1').read_text(), '1')
    else:
        assert_raises(FileNotFoundError, (dst.pathobj / 'secure.1').read_text)

    # reset wanted config, which must enable push of secure file
    src.repo.set_preferred_content('wanted', '', remote='target')
    res = src.push(to='target')
    assert_in_results(res, path=str(src.pathobj / 'secure.1'))
    eq_((dst.pathobj / 'secure.1').read_text(), '1')


# FIXME: on crippled FS post-update hook enabling via create-sibling doesn't
# work ATM
@skip_if_adjusted_branch
@slow  # 10sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_auto_data_transfer(path=None):
    path = Path(path)
    ds_a = Dataset(path / "a").create()
    (ds_a.pathobj / "foo.dat").write_text("foo")
    ds_a.save()

    # Should be the default, but just in case.
    ds_a.repo.config.set("annex.numcopies", "1", scope="local")
    ds_a.create_sibling(str(path / "b"), name="b")

    # With numcopies=1, no data is copied with data="auto".
    res = ds_a.push(to="b", data="auto", since=None)
    assert_not_in_results(res, action="copy")

    # Even when a file is explicitly given.
    res = ds_a.push(to="b", path="foo.dat", data="auto", since=None)
    assert_not_in_results(res, action="copy")

    # numcopies=2 changes that.
    ds_a.repo.config.set("annex.numcopies", "2", scope="local")
    res = ds_a.push(to="b", data="auto", since=None)
    assert_in_results(
        res, action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "foo.dat"))

    # --since= limits the files considered by --auto.
    (ds_a.pathobj / "bar.dat").write_text("bar")
    ds_a.save()
    (ds_a.pathobj / "baz.dat").write_text("baz")
    ds_a.save()
    res = ds_a.push(to="b", data="auto", since="HEAD~1")
    assert_not_in_results(
        res,
        action="copy", path=str(ds_a.pathobj / "bar.dat"))
    assert_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "baz.dat"))

    # --auto also considers preferred content.
    ds_a.repo.config.unset("annex.numcopies", scope="local")
    ds_a.repo.set_preferred_content("wanted", "nothing", remote="b")
    res = ds_a.push(to="b", data="auto", since=None)
    assert_not_in_results(
        res,
        action="copy", path=str(ds_a.pathobj / "bar.dat"))

    ds_a.repo.set_preferred_content("wanted", "anything", remote="b")
    res = ds_a.push(to="b", data="auto", since=None)
    assert_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "bar.dat"))


# FIXME: on crippled FS post-update hook enabling via create-sibling doesn't
# work ATM
@skip_if_adjusted_branch
@slow  # 16sec on Yarik's laptop
@with_tempfile(mkdir=True)
def test_auto_if_wanted_data_transfer_path_restriction(path=None):
    path = Path(path)
    ds_a = Dataset(path / "a").create()
    ds_a_sub0 = ds_a.create("sub0")
    ds_a_sub1 = ds_a.create("sub1")

    for ds in [ds_a, ds_a_sub0, ds_a_sub1]:
        (ds.pathobj / "sec.dat").write_text("sec")
        (ds.pathobj / "reg.dat").write_text("reg")
    ds_a.save(recursive=True)

    ds_a.create_sibling(str(path / "b"), name="b",
                        annex_wanted="not metadata=distribution-restrictions=*",
                        recursive=True)
    for ds in [ds_a, ds_a_sub0, ds_a_sub1]:
        ds.repo.set_metadata(add={"distribution-restrictions": "doesntmatter"},
                             files=["sec.dat"])

    # wanted-triggered --auto can be restricted to subdataset...
    res = ds_a.push(to="b", path="sub0", data="auto-if-wanted",
                    recursive=True)
    assert_not_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "reg.dat"))
    assert_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a_sub0.pathobj / "reg.dat"))
    assert_not_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a_sub0.pathobj / "sec.dat"))
    assert_not_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a_sub1.pathobj / "reg.dat"))

    # ... and to a wanted file.
    res = ds_a.push(to="b", path="reg.dat", data="auto-if-wanted",
                    recursive=True)
    assert_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "reg.dat"))
    assert_not_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a_sub1.pathobj / "reg.dat"))

    # But asking to transfer a file does not do it if the remote has a
    # wanted setting and doesn't want it.
    res = ds_a.push(to="b", path="sec.dat", data="auto-if-wanted",
                    recursive=True)
    assert_not_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "sec.dat"))

    res = ds_a.push(to="b", path="sec.dat", data="anything", recursive=True)
    assert_in_results(
        res,
        action="copy", target="b", status="ok",
        path=str(ds_a.pathobj / "sec.dat"))


@with_tempfile(mkdir=True)
def test_push_git_annex_branch_when_no_data(path=None):
    path = Path(path)
    ds = Dataset(path / "a").create()
    target = mk_push_target(ds, "target", str(path / "target"),
                            annex=False, bare=True)
    (ds.pathobj / "f0").write_text("0")
    ds.save()
    ds.push(to="target", data="nothing")
    assert_in("git-annex",
              {d["refname:strip=2"]
               for d in target.for_each_ref_(fields="refname:strip=2")})


@known_failure_githubci_osx
@with_tree(tree={"ds": {"f0": "0", "f1": "0", "f2": "0",
                        "f3": "1",
                        "f4": "2", "f5": "2"}})
def test_push_git_annex_branch_many_paths_same_data(path=None):
    path = Path(path)
    ds = Dataset(path / "ds").create(force=True)
    ds.save()
    mk_push_target(ds, "target", str(path / "target"),
                   annex=True, bare=False)
    nbytes = sum(ds.repo.get_content_annexinfo(paths=[f])[f]["bytesize"]
                 for f in [ds.repo.pathobj / "f0",
                           ds.repo.pathobj / "f3",
                           ds.repo.pathobj / "f4"])
    with swallow_logs(new_level=logging.DEBUG) as cml:
        res = ds.push(to="target")
    assert_in("{} bytes of annex data".format(nbytes), cml.out)
    # 3 files point to content already covered by another file.
    assert_result_count(res, 3,
                        action="copy", type="file", status="notneeded")


@known_failure_githubci_osx
@with_tree(tree={"ds": {"f0": "0"}})
def test_push_matching(path=None):
    path = Path(path)
    ds = Dataset(path / "ds").create(force=True)
    ds.config.set('push.default', 'matching', scope='local')
    ds.save()
    remote_ds = mk_push_target(ds, 'local', str(path / 'dssibling'),
                               annex=True, bare=False)
    # that fact that the next one even runs makes sure that we are in a better
    # place than https://github.com/datalad/datalad/issues/4888
    ds.push(to='local')
    # and we pushed the commit in the current branch
    eq_(remote_ds.get_hexsha(DEFAULT_BRANCH),
        ds.repo.get_hexsha(DEFAULT_BRANCH))


@slow  # can run over 30 sec when running in parallel with n=2. Cannot force serial yet, see https://github.com/pytest-dev/pytest-xdist/issues/385
@known_failure_githubci_win  # recent git-annex, https://github.com/datalad/datalad/issues/7184
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_nested_pushclone_cycle_allplatforms(origpath=None, storepath=None, clonepath=None):
    if 'DATALAD_SEED' in os.environ:
        # we are using create-sibling-ria via the cmdline in here
        # this will create random UUIDs for datasets
        # however, given a fixed seed each call to this command will start
        # with the same RNG seed, hence yield the same UUID on the same
        # machine -- leading to a collision
        raise SkipTest(
            'Test incompatible with fixed random number generator seed')
    # the aim here is this high-level test a std create-push-clone cycle for a
    # dataset with a subdataset, with the goal to ensure that correct branches
    # and commits are tracked, regardless of platform behavior and condition
    # of individual clones. Nothing fancy, just that the defaults behave in
    # sensible ways
    from datalad.cmd import WitlessRunner as Runner
    run = Runner().run

    # create original nested dataset
    with chpwd(origpath):
        run(['datalad', 'create', 'super'])
        run(['datalad', 'create', '-d', 'super', str(Path('super', 'sub'))])

    # verify essential linkage properties
    orig_super = Dataset(Path(origpath, 'super'))
    orig_sub = Dataset(orig_super.pathobj / 'sub')

    (orig_super.pathobj / 'file1.txt').write_text('some1')
    (orig_sub.pathobj / 'file2.txt').write_text('some1')
    with chpwd(orig_super.path):
        run(['datalad', 'save', '--recursive'])

    # TODO not yet reported clean with adjusted branches
    #assert_repo_status(orig_super.path)

    # the "true" branch that sub is on, and the gitsha of the HEAD commit of it
    orig_sub_corr_branch = \
        orig_sub.repo.get_corresponding_branch() or orig_sub.repo.get_active_branch()
    orig_sub_corr_commit = orig_sub.repo.get_hexsha(orig_sub_corr_branch)

    # make sure the super trackes this commit
    assert_in_results(
        orig_super.subdatasets(),
        path=orig_sub.path,
        gitshasum=orig_sub_corr_commit,
        # TODO it should also track the branch name
        # Attempted: https://github.com/datalad/datalad/pull/3817
        # But reverted: https://github.com/datalad/datalad/pull/4375
    )

    # publish to a store, to get into a platform-agnostic state
    # (i.e. no impact of an annex-init of any kind)
    store_url = 'ria+' + get_local_file_url(storepath)
    with chpwd(orig_super.path):
        run(['datalad', 'create-sibling-ria', '--recursive',
             '-s', 'store', store_url, '--new-store-ok'])
        run(['datalad', 'push', '--recursive', '--to', 'store'])

    # we are using the 'store' sibling's URL, which should be a plain path
    store_super = AnnexRepo(orig_super.siblings(name='store')[0]['url'], init=False)
    store_sub = AnnexRepo(orig_sub.siblings(name='store')[0]['url'], init=False)

    # both datasets in the store only carry the real branches, and nothing
    # adjusted
    for r in (store_super, store_sub):
        eq_(set(r.get_branches()), set([orig_sub_corr_branch, 'git-annex']))

    # and reobtain from a store
    cloneurl = 'ria+' + get_local_file_url(str(storepath), compatibility='git')
    with chpwd(clonepath):
        run(['datalad', 'clone', cloneurl + '#' + orig_super.id, 'super'])
        run(['datalad', '-C', 'super', 'get', '--recursive', '.'])

    # verify that nothing has changed as a result of a push/clone cycle
    clone_super = Dataset(Path(clonepath, 'super'))
    clone_sub = Dataset(clone_super.pathobj / 'sub')
    assert_in_results(
        clone_super.subdatasets(),
        path=clone_sub.path,
        gitshasum=orig_sub_corr_commit,
    )

    for ds1, ds2, f in ((orig_super, clone_super, 'file1.txt'),
                        (orig_sub, clone_sub, 'file2.txt')):
        eq_((ds1.pathobj / f).read_text(), (ds2.pathobj / f).read_text())

    # get status info that does not recursive into subdatasets, i.e. not
    # looking for uncommitted changes
    # we should see no modification reported
    assert_not_in_results(
        clone_super.status(eval_subdataset_state='commit'),
        state='modified')
    # and now the same for a more expensive full status
    assert_not_in_results(
        clone_super.status(recursive=True),
        state='modified')


@with_tempfile
def test_push_custom_summary(path=None):
    path = Path(path)
    ds = Dataset(path / "ds").create()

    sib = mk_push_target(ds, "sib", str(path / "sib"), bare=False, annex=False)
    (sib.pathobj / "f1").write_text("f1")
    sib.save()

    (ds.pathobj / "f2").write_text("f2")
    ds.save()

    # These options are true by default and our tests usually run with a
    # temporary home, but set them to be sure.
    ds.config.set("advice.pushUpdateRejected", "true", scope="local")
    ds.config.set("advice.pushFetchFirst", "true", scope="local")
    with swallow_outputs() as cmo:
        ds.push(to="sib", result_renderer="default", on_failure="ignore")
        assert_in("Hints:", cmo.out)
        assert_in("action summary:", cmo.out)
