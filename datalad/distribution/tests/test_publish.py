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
from os.path import join as opj
from os.path import exists
from os.path import lexists
from ..dataset import Dataset
from datalad.api import publish, install
from datalad.dochelpers import exc_str
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.utils import chpwd

from nose.tools import eq_, ok_, assert_is_instance
from nose.tools import assert_false as nok_
from datalad.tests.utils import with_tempfile, assert_in, \
    with_testrepos, assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import skip_ssh


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_invalid_call(origin, tdir):
    ds = Dataset(origin)
    ds.uninstall('subm 1', check=False)
    # nothing
    assert_raises(ValueError, publish, '/notthere')
    # known, but not present
    assert_raises(ValueError, publish, opj(ds.path, 'subm 1'))
    # --since without dataset is now supported as long as it
    # could be identified
    # assert_raises(InsufficientArgumentsError, publish, since='HEAD')
    # but if it couldn't be, then should indeed crash
    with chpwd(tdir):
        assert_raises(InsufficientArgumentsError, publish, since='HEAD')


@skip_ssh
@with_tempfile
@with_tempfile
def test_smth_about_not_supported(p1, p2):
    source = Dataset(p1).create()
    source.create_sibling(
        'ssh://localhost' + p2,
        name='target1')
    # source.publish(to='target1')
    with chpwd(p1):
        # since we have only a single commit -- there is no HEAD^
        assert_raises(ValueError, publish, to='target1', since='HEAD^')
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

    res = publish(dataset=source, to="target")
    eq_(res, ([source], []))

    ok_clean_git(source.repo, annex=None)
    ok_clean_git(target, annex=None)
    eq_(list(target.get_branch_commits("master")),
        list(source.repo.get_branch_commits("master")))

    # don't fail when doing it again
    res = publish(dataset=source, to="target")
    # and nothing is pushed
    eq_(res, ([], []))

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
    source.repo.add(opj(src_path, 'test_mod_file'), git=True,
                    commit=True, msg="Modified.")
    ok_clean_git(source.repo, annex=None)

    res = publish(dataset=source, to='target')
    eq_(res, ([source], []))

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


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_recursive(origin, src_path, dst_path, sub1_pub, sub2_pub):

    # prepare src
    source = install(src_path, source=origin, recursive=True)

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.checkout("TMP", ["-b"])
    source.repo.add_remote("target", dst_path)

    # subdatasets have no remote yet, so recursive publishing should fail:
    with assert_raises(ValueError) as cm:
        publish(dataset=source, to="target", recursive=True)
    assert_in("Unknown target sibling 'target'", exc_str(cm.exception))

    # now, set up targets for the submodules:
    sub1_target = GitRepo(sub1_pub, create=True)
    sub1_target.checkout("TMP", ["-b"])
    sub2_target = AnnexRepo(sub2_pub, create=True)
    # we will be testing presence of the file content, so let's make it progress
    sub2_target.config.set('receive.denyCurrentBranch', 'updateInstead', where='local')
    sub1 = GitRepo(opj(src_path, 'subm 1'), create=False)
    sub2 = GitRepo(opj(src_path, 'subm 2'), create=False)
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
    # (Note: Dataset lacks __eq__ for now. Should this be based on path only?)
    assert_is_instance(res, tuple)
    assert_is_instance(res[0], list)
    assert_is_instance(res[1], list)
    eq_(res[1], [])  # nothing failed/was skipped
    for item in res[0]:
        assert_is_instance(item, Dataset)
    eq_({res[0][0].path, res[0][1].path, res[0][2].path},
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

    # test for publishing with  --since.  By default since no changes, nothing pushed
    res_ = publish(dataset=source, recursive=True)
    eq_(set(r.path for r in res_[0]), set())

    # still nothing gets pushed, because origin is up to date
    res_ = publish(dataset=source, recursive=True, since='HEAD^')
    eq_(set(r.path for r in res_[0]), set([]))

    # and we should not fail if we run it from within the dataset
    with chpwd(source.path):
        res_ = publish(recursive=True, since='HEAD^')
        eq_(set(r.path for r in res_[0]), set([]))

    # Let's now update one subm
    with open(opj(sub2.path, "file.txt"), 'w') as f:
        f.write('')
    # add to subdataset, does not alter super dataset!
    # MIH: use `to_git` because original test author used
    # and explicit `GitRepo.add` -- keeping this for now
    Dataset(sub2.path).add('file.txt', to_git=True)

    # Let's now update one subm
    create_tree(sub2.path, {'file.dat': 'content'})
    # add to subdataset, without reflecting the change in its super(s)
    Dataset(sub2.path).add('file.dat')

    # note: will publish to origin here since that is what it tracks
    res_published, res_skipped = publish(dataset=source, recursive=True)
    # only updates published, i.e. just the subdataset, super wasn't altered
    # nothing copied!
    eq_(res_published, [Dataset(sub2.path)])
    eq_(res_skipped, [])

    # since published to origin -- destination should not get that file
    nok_(lexists(opj(sub2_target.path, 'file.dat')))
    res_published, res_skipped = publish(dataset=source, to='target', recursive=True)
    eq_(res_published, [Dataset(sub2.path)])
    # Note: with updateInstead only in target2 and not saving change in
    # super-dataset we would have made remote dataset, if we had entire
    # hierarchy, to be somewhat inconsistent.
    # But here, since target datasets are independent -- it is ok

    # and the file itself was not transferred but now exists
    ok_(lexists(opj(sub2_target.path, 'file.dat')))
    nok_(sub2_target.file_has_content('file.dat'))

    # but now we can redo publish recursively, at least stating to consider
    # explicitly to copy .
    res_published, res_skipped = publish(
        '.',
        dataset=source, to='target',
        recursive=True
    )
    ok_(sub2_target.file_has_content('file.dat'))
    eq_(res_published, ['file.dat'])  # note that this report makes little sense without path to the repository


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
    sub1_target = GitRepo(sub1_pub, create=True)
    sub1_target.checkout("TMP", ["-b"])
    sub2_target = GitRepo(sub2_pub, create=True)
    sub2_target.checkout("TMP", ["-b"])
    sub1 = GitRepo(opj(src_path, 'subm 1'), create=False)
    sub2 = GitRepo(opj(src_path, 'subm 2'), create=False)
    sub1.add_remote("target", sub1_pub)
    sub2.add_remote("target", sub2_pub)

    # TMP: Insert the fetch to prevent GitPython to fail after the push,
    # because it cannot resolve the SHA of the old commit of the remote,
    # that git reports back after the push.
    # TODO: Figure out, when to fetch things in general; Alternatively:
    # Is there an option for push, that prevents GitPython from failing?
    source.repo.fetch("target")
    res = publish(dataset=source, to="target", path=['test-annex.dat'])
    # first it would publish data and then push
    eq_(res, (['test-annex.dat', source], []))
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

    source.repo.fetch("target")
    res = publish(dataset=source, to="target", path=['.'])
    # there is nothing to publish on 2nd attempt
    #eq_(res, ([source, 'test-annex.dat'], []))
    eq_(res, ([], []))

    source.repo.fetch("target")
    import glob
    res = publish(dataset=source, to="target", path=glob.glob1(source.path, '*'))
    # Note: This leads to recursive publishing, since expansion of '*'
    #       contains the submodules themselves in this setup

    # collect result paths:
    result_paths = []
    for item in res[0]:
        result_paths.append(item.path if isinstance(item, Dataset) else item)

    # only the subdatasets, targets are plain git repos, hence
    # no file content is pushed, all content in super was pushed
    # before
    eq_({sub1.path, sub2.path},
        set(result_paths))


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
    # TODO next line would require `add_sibling` to be called with force
    # see gh-1235
    #source.config.add(depvar, 'stupid', where='local')
    #eq_(source.config.get(depvar, None), 'stupid')

    # two remote sibling on two "different" hosts
    source.create_sibling(
        'ssh://localhost' + target1_path,
        annex_wanted='standard',
        annex_group='backup',
        name='target1')
    # fails with unknown remote
    assert_raises(
        ValueError,
        source.create_sibling,
        'ssh://datalad-test' + target2_path,
        name='target2',
        existing='reconfigure',  # because 'target2' is known in polluted cfg
        publish_depends='bogus')
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
    source.add('probe1')
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
