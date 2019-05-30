# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test publish action

"""



import logging
import os
from os.path import join as opj
from os.path import exists
from os.path import lexists
from ..dataset import Dataset
from datalad.api import publish, install
from datalad.api import install
from datalad.api import create
from datalad.dochelpers import exc_str
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.utils import chpwd

from nose.tools import eq_, ok_, assert_is_instance
from nose.tools import assert_false as nok_
from datalad.tests.utils import with_tempfile, assert_in, \
    with_testrepos, assert_not_in
from datalad.utils import _path_
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false
from datalad.tests.utils import assert_not_equal
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import neq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import assert_status
from datalad.tests.utils import with_tree
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import known_failure_windows


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_invalid_call(origin, tdir):
    ds = Dataset(origin)
    ds.uninstall('subm 1', check=False)
    # nothing
    assert_status('error', publish('/notthere', on_failure='ignore'))
    # known, but not present
    assert_status('impossible', publish(opj(ds.path, 'subm 1'), on_failure='ignore'))
    # --since without dataset is now supported as long as it
    # could be identified
    # assert_raises(InsufficientArgumentsError, publish, since='HEAD')
    # but if it couldn't be, then should indeed crash
    with chpwd(tdir):
        assert_raises(InsufficientArgumentsError, publish, since='HEAD')
    # new dataset, with unavailable subdataset
    dummy = Dataset(tdir).create()
    dummy_sub = dummy.create('sub')
    dummy_sub.uninstall()
    assert_in('sub', dummy.subdatasets(fulfilled=False, result_xfm='relpaths'))
    # now an explicit call to publish the unavailable subdataset
    assert_result_count(
        dummy.publish('sub', on_failure='ignore'),
        1,
        path=dummy_sub.path,
        status='impossible',
        type='dataset')


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tempfile
@with_tempfile
def test_smth_about_not_supported(p1, p2):
    source = Dataset(p1).create()
    from datalad.support.network import PathRI
    source.create_sibling(
        'ssh://localhost' + PathRI(p2).posixpath,
        name='target1')
    # source.publish(to='target1')
    with chpwd(p1):
        # since we have only two commits (set backend, init dataset)
        # -- there is no HEAD^^
        assert_result_count(
            publish(to='target1', since='HEAD^^', on_failure='ignore'),
            1,
            status='impossible',
            message="fatal: bad revision 'HEAD^^'")
        # but now let's add one more commit, we should be able to pusblish
        source.repo.commit("msg", options=['--allow-empty'])
        publish(to='target1', since='HEAD^')  # must not fail now


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_simple(origin, src_path, dst_path):

    # prepare src
    source = install(src_path, source=origin, recursive=True)
    # forget we cloned it (provide no 'origin' anymore), which should lead to
    # setting tracking branch to target:
    source.repo.remove_remote("origin")

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.checkout("TMP", ["-b"])
    source.repo.add_remote("target", dst_path)

    res = publish(dataset=source, to="target", result_xfm='datasets')
    eq_(res, [source])

    ok_clean_git(source.repo, annex=None)
    ok_clean_git(target, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))

    # don't fail when doing it again
    res = publish(dataset=source, to="target")
    # and nothing is pushed
    assert_result_count(res, 1, status='notneeded')

    ok_clean_git(source.repo, annex=None)
    ok_clean_git(target, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))
    eq_(list(target.get_branch_commits("git-annex")),
        list(source.repo.get_branch_commits("git-annex")))

    # 'target/master' should be tracking branch at this point, so
    # try publishing without `to`:
    # MIH: Nope, we don't automatically add this anymore

    # some modification:
    with open(opj(src_path, 'test_mod_file'), "w") as f:
        f.write("Some additional stuff.")
    source.save(opj(src_path, 'test_mod_file'), to_git=True,
                message="Modified.")
    ok_clean_git(source.repo, annex=None)

    res = publish(dataset=source, to='target', result_xfm='datasets')
    eq_(res, [source])

    ok_clean_git(dst_path, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))
    # Since git-annex 6.20170220, post-receive hook gets triggered
    # which results in entry being added for that repo into uuid.log on remote
    # end since then finally git-annex senses that it needs to init that remote,
    # so it might have 1 more commit than local.
    # see https://github.com/datalad/datalad/issues/1319
    ok_(set(source.repo.get_branch_commits("git-annex")).issubset(
        set(target.get_branch_commits("git-annex"))))


@with_testrepos('basic_git', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_plain_git(origin, src_path, dst_path):
    # TODO: Since it's mostly the same, melt with test_publish_simple

    # prepare src
    source = install(src_path, source=origin, recursive=True)
    # forget we cloned it (provide no 'origin' anymore), which should lead to
    # setting tracking branch to target:
    source.repo.remove_remote("origin")

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.checkout("TMP", ["-b"])
    source.repo.add_remote("target", dst_path)

    res = publish(dataset=source, to="target", result_xfm='datasets')
    eq_(res, [source])

    ok_clean_git(source.repo, annex=None)
    ok_clean_git(target, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))

    # don't fail when doing it again
    res = publish(dataset=source, to="target")
    # and nothing is pushed
    assert_result_count(res, 1, status='notneeded')

    ok_clean_git(source.repo, annex=None)
    ok_clean_git(target, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))

    # some modification:
    with open(opj(src_path, 'test_mod_file'), "w") as f:
        f.write("Some additional stuff.")
    source.save(opj(src_path, 'test_mod_file'), to_git=True,
               message="Modified.")
    ok_clean_git(source.repo, annex=None)

    res = publish(dataset=source, to='target', result_xfm='datasets')
    eq_(res, [source])

    ok_clean_git(dst_path, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))

    # amend and change commit msg in order to test for force push:
    source.repo.commit("amended", options=['--amend'])
    # push should be rejected (non-fast-forward):
    assert_raises(IncompleteResultsError,
                  publish, dataset=source, to='target', result_xfm='datasets')
    # push with force=True works:
    res = publish(dataset=source, to='target', result_xfm='datasets', force=True)
    eq_(res, [source])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_recursive(pristine_origin, origin_path, src_path, dst_path, sub1_pub, sub2_pub):

    # we will be publishing back to origin, so to not alter testrepo
    # we will first clone it
    origin = install(origin_path, source=pristine_origin, recursive=True)
    # prepare src
    source = install(src_path, source=origin.path, recursive=True)
    # we will be trying to push into this later on, need to give permissions...
    origin_sub2 = Dataset(opj(origin_path, '2'))
    origin_sub2.config.set(
        'receive.denyCurrentBranch', 'updateInstead', where='local')
    ## TODO this manual fixup is needed due to gh-1548 -- needs proper solution
    #os.remove(opj(origin_sub2.path, '.git'))
    #os.rename(opj(origin_path, '.git', 'modules', '2'), opj(origin_sub2.path, '.git'))

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.checkout("TMP", ["-b"])
    source.repo.add_remote("target", dst_path)

    # subdatasets have no remote yet, so recursive publishing should fail:
    res = publish(dataset=source, to="target", recursive=True, on_failure='ignore')
    assert_result_count(res, 3)
    assert_result_count(
        res, 1, status='ok', type='dataset', path=source.path)
    assert_result_count(
        res, 2, status='error',
        message=("Unknown target sibling '%s' for publication", 'target'))

    # now, set up targets for the submodules:
    sub1_target = GitRepo(sub1_pub, create=True)
    sub1_target.checkout("TMP", ["-b"])
    sub2_target = AnnexRepo(sub2_pub, create=True)
    # we will be testing presence of the file content, so let's make it progress
    sub2_target.config.set('receive.denyCurrentBranch', 'updateInstead', where='local')
    sub1 = GitRepo(opj(src_path, 'subm 1'), create=False)
    sub2 = GitRepo(opj(src_path, '2'), create=False)
    sub1.add_remote("target", sub1_pub)
    sub2.add_remote("target", sub2_pub)

    # publish recursively
    with swallow_logs(new_level=logging.DEBUG) as cml:
        res = publish(dataset=source, to="target", recursive=True)
        assert_not_in(
            'forced update', cml.out,
            "we probably haven't merged git-annex before pushing"
        )

    # testing result list
    # base dataset was already published above, notneeded again
    assert_status(('ok', 'notneeded'), res)  # nothing failed
    assert_result_count(
        res, 3, type='dataset')
    eq_({r['path'] for r in res},
        {src_path, sub1.path, sub2.path})

    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))
    eq_(list(target.get_branch_commits("git-annex")),
        list(source.repo.get_branch_commits("git-annex")))
    eq_(list(sub1_target.get_branch_commits("master")),
        list(sub1.get_branch_commits("master")))
    eq_(list(sub1_target.get_branch_commits("git-annex")),
        list(sub1.get_branch_commits("git-annex")))
    eq_(list(sub2_target.get_branch_commits("master")),
        list(sub2.get_branch_commits("master")))
    eq_(list(sub2_target.get_branch_commits("git-annex")),
        list(sub2.get_branch_commits("git-annex")))

    # we are tracking origin but origin has different git-annex, since we
    # cloned from it, so it is not aware of our git-annex
    neq_(list(origin.repo.get_branch_commits("git-annex")),
         list(source.repo.get_branch_commits("git-annex")))
    # So if we first publish to it recursively, we would update
    # all sub-datasets since git-annex branch would need to be pushed
    res_ = publish(dataset=source, recursive=True)
    assert_result_count(res_, 1, status='ok', path=source.path)
    assert_result_count(res_, 1, status='ok', path=sub1.path)
    assert_result_count(res_, 1, status='ok', path=sub2.path)
    # and now should carry the same state for git-annex
    eq_(list(origin.repo.get_branch_commits("git-annex")),
        list(source.repo.get_branch_commits("git-annex")))

    # test for publishing with  --since.  By default since no changes, nothing pushed
    res_ = publish(dataset=source, recursive=True)
    assert_result_count(
        res_, 3, status='notneeded', type='dataset')

    # still nothing gets pushed, because origin is up to date
    res_ = publish(dataset=source, recursive=True, since='HEAD^')
    assert_result_count(
        res_, 3, status='notneeded', type='dataset')

    # and we should not fail if we run it from within the dataset
    with chpwd(source.path):
        res_ = publish(recursive=True, since='HEAD^')
        assert_result_count(
            res_, 3, status='notneeded', type='dataset')

    # Let's now update one subm
    with open(opj(sub2.path, "file.txt"), 'w') as f:
        f.write('')
    # add to subdataset, does not alter super dataset!
    # MIH: use `to_git` because original test author used
    # and explicit `GitRepo.add` -- keeping this for now
    Dataset(sub2.path).save('file.txt', to_git=True)

    # Let's now update one subm
    create_tree(sub2.path, {'file.dat': 'content'})
    # add to subdataset, without reflecting the change in its super(s)
    Dataset(sub2.path).save('file.dat')

    # note: will publish to origin here since that is what it tracks
    res_ = publish(dataset=source, recursive=True, on_failure='ignore')
    ## only updates published, i.e. just the subdataset, super wasn't altered
    ## nothing copied!
    assert_status(('ok', 'notneeded'), res_)
    assert_result_count(res_, 1, status='ok', path=sub2.path, type='dataset')
    assert_result_count(res_, 0, path=opj(sub2.path, 'file.dat'), type='file')

    # since published to origin -- destination should not get that file
    nok_(lexists(opj(sub2_target.path, 'file.dat')))
    res_ = publish(dataset=source, to='target', recursive=True)
    assert_status(('ok', 'notneeded'), res_)
    assert_result_count(res_, 1, status='ok', path=sub2.path, type='dataset')
    assert_result_count(res_, 0, path=opj(sub2.path, 'file.dat'), type='file')

    # Note: with updateInstead only in target2 and not saving change in
    # super-dataset we would have made remote dataset, if we had entire
    # hierarchy, to be somewhat inconsistent.
    # But here, since target datasets are independent -- it is ok

    # and the file itself was transferred
    ok_(lexists(opj(sub2_target.path, 'file.dat')))
    nok_(sub2_target.file_has_content('file.dat'))

    ## but now we can redo publish recursively, with explicitly requested data transfer
    res_ = publish(
        dataset=source, to='target',
        recursive=True,
        transfer_data='all'
    )
    ok_(sub2_target.file_has_content('file.dat'))
    assert_result_count(
        res_, 1, status='ok', path=opj(sub2.path, 'file.dat'))

    # Let's save those present changes and publish while implying "since last
    # merge point"
    source.save(message="Changes in subm2")
    # and test if it could deduce the remote/branch to push to
    source.config.set('branch.master.remote', 'target', where='local')
    with chpwd(source.path):
        res_ = publish(since='', recursive=True)
    # TODO: somehow test that there were no even attempt to diff within "subm 1"
    # since if `--since=''` worked correctly, nothing has changed there and it
    # should have not been even touched
    assert_status(('ok', 'notneeded'), res_)
    assert_result_count(res_, 1, status='ok', path=source.path, type='dataset')


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_publish_with_data(origin, src_path, dst_path, sub1_pub, sub2_pub, dst_clone_path):

    # prepare src
    source = install(src_path, source=origin, recursive=True)
    source.repo.get('test-annex.dat')

    # create plain git at target:
    target = AnnexRepo(dst_path, create=True)
    target.checkout("TMP", ["-b"])
    source.repo.add_remote("target", dst_path)

    # now, set up targets for the submodules:
    # the need to be annexes, because we want to be able to copy data to them
    # further down
    sub1_target = AnnexRepo(sub1_pub, create=True)
    sub1_target.checkout("TMP", ["-b"])
    sub2_target = AnnexRepo(sub2_pub, create=True)
    sub2_target.checkout("TMP", ["-b"])
    sub1 = GitRepo(opj(src_path, 'subm 1'), create=False)
    sub2 = GitRepo(opj(src_path, '2'), create=False)
    sub1.add_remote("target", sub1_pub)
    sub2.add_remote("target", sub2_pub)

    res = publish(dataset=source, to="target", path=['test-annex.dat'], result_xfm='paths')
    # first it would publish data and then push
    # TODO order is not fixed (yet)
    #eq_(res, [opj(source.path, 'test-annex.dat'), source.path])
    eq_(set(res), set([opj(source.path, 'test-annex.dat'), source.path]))
    # XXX master was not checked out in dst!

    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))
    # TODO: last commit in git-annex branch differs. Probably fine,
    # but figure out, when exactly to expect this for proper testing:
    # yoh: they differ because local annex records information about now
    # file being available in that remote, and remote one does it via a call in
    # the hook I guess.  So they both get the same information but in two
    # different commits.  I do not observe such behavior of remote having git-annex
    # automagically updated in older clones
    # which do not have post-receive hook on remote side
    eq_(list(target.get_branch_commits("git-annex"))[1:],
        list(source.repo.get_branch_commits("git-annex"))[1:])

    # we need compare target/master:
    target.checkout("master")
    ok_(target.file_has_content('test-annex.dat'))

    # make sure that whatever we published is actually consumable
    dst_clone = install(
        dst_clone_path, source=dst_path,
        result_xfm='datasets', return_type='item-or-list')
    nok_(dst_clone.repo.file_has_content('test-annex.dat'))
    res = dst_clone.get('test-annex.dat')
    ok_(dst_clone.repo.file_has_content('test-annex.dat'))

    res = publish(dataset=source, to="target", path=['.'])
    # there is nothing to publish on 2nd attempt
    #eq_(res, ([source, 'test-annex.dat'], []))
    assert_result_count(res, 1, status='notneeded')

    import glob
    res = publish(dataset=source, to="target", path=glob.glob1(source.path, '*'))
    # Note: This leads to recursive publishing, since expansion of '*'
    #       contains the submodules themselves in this setup

    # only the subdatasets, targets are plain git repos, hence
    # no file content is pushed, all content in super was pushed
    # before
    assert_result_count(res, 3)
    assert_result_count(res, 1, status='ok', path=sub1.path)
    assert_result_count(res, 1, status='ok', path=sub2.path)
    assert_result_count(res, 1, status='notneeded', path=source.path)

    # if we publish again -- nothing to be published
    res = source.publish(to="target")
    assert_result_count(res, 1, status='notneeded', path=source.path)
    # if we drop a file and publish again -- dataset should be published
    # since git-annex branch was updated
    source.drop('test-annex.dat')
    res = source.publish(to="target")
    assert_result_count(res, 1, status='ok', path=source.path)
    # and empty again if we try again
    res = source.publish(to="target")
    assert_result_count(res, 1, status='notneeded', path=source.path)


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
@with_tempfile()
def test_publish_depends(
        origin,
        src_path,
        target1_path,
        target2_path,
        target3_path):
    # prepare src
    source = install(src_path, source=origin, recursive=True)
    source.repo.get('test-annex.dat')
    # pollute config
    depvar = 'remote.target2.datalad-publish-depends'
    source.config.add(depvar, 'stupid', where='local')
    eq_(source.config.get(depvar, None), 'stupid')

    # two remote sibling on two "different" hosts
    source.create_sibling(
        'ssh://localhost' + target1_path,
        annex_wanted='standard',
        annex_group='backup',
        name='target1')
    # fails with unknown remote
    res = source.create_sibling(
        'ssh://datalad-test' + target2_path,
        name='target2',
        existing='reconfigure',  # because 'target2' is known in polluted cfg
        publish_depends='bogus',
        on_failure='ignore')
    assert_result_count(
        res, 1,
        status='error',
        message=(
            'unknown sibling(s) specified as publication dependency: %s',
            set(['bogus'])))
    # for real
    source.create_sibling(
        'ssh://datalad-test' + target2_path,
        name='target2',
        existing='reconfigure',  # because 'target2' is known in polluted cfg
        annex_wanted='standard',
        annex_group='backup',
        publish_depends='target1')
    # wiped out previous dependencies
    eq_(source.config.get(depvar, None), 'target1')
    # and one more remote, on the same host but associated with a dependency
    source.create_sibling(
        'ssh://datalad-test' + target3_path,
        name='target3')
    ok_clean_git(src_path)
    # introduce change in source
    create_tree(src_path, {'probe1': 'probe1'})
    source.save('probe1')
    ok_clean_git(src_path)
    # only the source has the probe
    ok_file_has_content(opj(src_path, 'probe1'), 'probe1')
    for p in (target1_path, target2_path, target3_path):
        assert_false(lexists(opj(p, 'probe1')))
    # publish to a standalone remote
    source.publish(to='target3')
    ok_(lexists(opj(target3_path, 'probe1')))
    # but it has no data copied
    target3 = Dataset(target3_path)
    nok_(target3.repo.file_has_content('probe1'))

    # but if we publish specifying its path, it gets copied
    source.publish('probe1', to='target3')
    ok_file_has_content(opj(target3_path, 'probe1'), 'probe1')

    # no others are affected in either case
    for p in (target1_path, target2_path):
        assert_false(lexists(opj(p, 'probe1')))

    # publish to all remaining, but via a dependency
    source.publish(to='target2')
    for p in (target1_path, target2_path, target3_path):
        ok_file_has_content(opj(p, 'probe1'), 'probe1')


@known_failure_windows
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_gh1426(origin_path, target_path):
    # set up a pair of repos, one the published copy of the other
    origin = create(origin_path)
    target = AnnexRepo(target_path, create=True)
    target.config.set(
        'receive.denyCurrentBranch', 'updateInstead', where='local')
    origin.siblings('add', name='target', url=target_path)
    origin.publish(to='target')
    ok_clean_git(origin.path)
    ok_clean_git(target.path)
    eq_(origin.repo.get_hexsha(), target.get_hexsha())

    # gist of #1426 is that a newly added subdataset does not cause the
    # superdataset to get published
    origin.create('sub')
    ok_clean_git(origin.path)
    assert_not_equal(origin.repo.get_hexsha(), target.get_hexsha())
    # now push
    res = origin.publish(to='target')
    assert_result_count(res, 1)
    assert_result_count(res, 1, status='ok', type='dataset', path=origin.path)
    eq_(origin.repo.get_hexsha(), target.get_hexsha())


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_gh1691(origin, src_path, dst_path):

    # prepare src; no subdatasets installed, but mount points present
    source = install(src_path, source=origin, recursive=False)
    ok_(exists(opj(src_path, "subm 1")))
    assert_false(Dataset(opj(src_path, "subm 1")).is_installed())

    # some content modification of the superdataset
    create_tree(src_path, {'probe1': 'probe1'})
    source.save('probe1')
    ok_clean_git(src_path)

    # create the target(s):
    source.create_sibling(
        'ssh://localhost:' + dst_path,
        name='target', recursive=True)

    # publish recursively, which silently ignores non-installed datasets
    results = source.publish(to='target', recursive=True)
    assert_result_count(results, 1)
    assert_result_count(results, 1, status='ok', type='dataset', path=source.path)

    # if however, a non-installed subdataset is requsted explicitly, it'll fail
    results = source.publish(path='subm 1', to='target', on_failure='ignore')
    assert_result_count(results, 1, status='impossible', type='dataset', action='publish')


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tree(tree={'1': '123'})
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_publish_target_url(src, desttop, desturl):
    # https://github.com/datalad/datalad/issues/1762
    ds = Dataset(src).create(force=True)
    ds.save('1')
    ds.create_sibling('ssh://localhost:%s/subdir' % desttop,
                      name='target',
                      target_url=desturl + 'subdir/.git')
    results = ds.publish(to='target', transfer_data='all')
    assert results
    ok_file_has_content(_path_(desttop, 'subdir/1'), '123')


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
def test_gh1763(src, target1, target2):
    # this test is very similar to test_publish_depends, but more
    # comprehensible, and directly tests issue 1763
    src = Dataset(src).create(force=True)
    src.create_sibling(
        'ssh://datalad-test' + target1,
        name='target1')
    src.create_sibling(
        'ssh://datalad-test' + target2,
        name='target2',
        publish_depends='target1')
    # a file to annex
    create_tree(src.path, {'probe1': 'probe1'})
    src.save('probe1', to_git=False)
    # make sure the probe is annexed, not straight in Git
    assert_in('probe1', src.repo.get_annexed_files(with_content_only=True))
    # publish to target2, must handle dependency
    src.publish(to='target2', transfer_data='all')
    for target in (target1, target2):
        assert_in(
            'probe1',
            Dataset(target).repo.get_annexed_files(with_content_only=True))
