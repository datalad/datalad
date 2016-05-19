# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test publish action

"""

import os
from os.path import join as opj, abspath, basename
from ..dataset import Dataset
from datalad.api import publish, install
from datalad.distribution.install import get_containing_subdataset
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_is_instance
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_not_in
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_simple(origin, src_path, dst_path):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")
    # forget we cloned it (provide no 'origin' anymore), which should lead to
    # setting tracking branch to target:
    source.repo.git_remote_remove("origin")

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.git_checkout("TMP", "-b")
    source.repo.git_remote_add("target", dst_path)

    res = publish(dataset=source, dest="target")
    eq_(res, source)

    ok_clean_git(src_path, annex=False)
    ok_clean_git(dst_path, annex=False)
    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))

    # don't fail when doing it again
    res = publish(dataset=source, dest="target")
    eq_(res, source)

    ok_clean_git(src_path, annex=False)
    ok_clean_git(dst_path, annex=False)
    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))
    eq_(list(target.git_get_branch_commits("git-annex")),
        list(source.repo.git_get_branch_commits("git-annex")))

    # 'target/master' should be tracking branch at this point, so
    # try publishing without `dest`:

    # some modification:
    with open(opj(src_path, 'test_mod_file'), "w") as f:
        f.write("Some additional stuff.")
    source.repo.git_add(opj(src_path, 'test_mod_file'))
    source.repo.git_commit("Modified.")
    ok_clean_git(src_path, annex=False)

    res = publish(dataset=source)
    eq_(res, source)

    ok_clean_git(dst_path, annex=False)
    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))
    eq_(list(target.git_get_branch_commits("git-annex")),
        list(source.repo.git_get_branch_commits("git-annex")))


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_recursive(origin, src_path, dst_path, sub1_pub, sub2_pub):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.git_checkout("TMP", "-b")
    source.repo.git_remote_add("target", dst_path)

    # subdatasets have no remote yet, so recursive publishing should fail:
    with assert_raises(ValueError) as cm:
        publish(dataset=source, dest="target", recursive=True)
    assert_in("No sibling 'target' found.", str(cm.exception))

    # now, set up targets for the submodules:
    sub1_target = GitRepo(sub1_pub, create=True)
    sub1_target.git_checkout("TMP", "-b")
    sub2_target = GitRepo(sub2_pub, create=True)
    sub2_target.git_checkout("TMP", "-b")
    sub1 = GitRepo(opj(src_path, 'sub1'), create=False)
    sub2 = GitRepo(opj(src_path, 'sub2'), create=False)
    sub1.git_remote_add("target", sub1_pub)
    sub2.git_remote_add("target", sub2_pub)

    # publish recursively
    res = publish(dataset=source, dest="target", recursive=True)

    # testing result list
    # (Note: Dataset lacks __eq__ for now. Should this be based on path only?)
    assert_is_instance(res, list)
    for item in res:
        assert_is_instance(item, Dataset)
    eq_(res[0].path, src_path)
    eq_(res[1].path, sub1.path)
    eq_(res[2].path, sub2.path)

    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))
    eq_(list(target.git_get_branch_commits("git-annex")),
        list(source.repo.git_get_branch_commits("git-annex")))
    eq_(list(sub1_target.git_get_branch_commits("master")),
        list(sub1.git_get_branch_commits("master")))
    eq_(list(sub1_target.git_get_branch_commits("git-annex")),
        list(sub1.git_get_branch_commits("git-annex")))
    eq_(list(sub2_target.git_get_branch_commits("master")),
        list(sub2.git_get_branch_commits("master")))
    eq_(list(sub2_target.git_get_branch_commits("git-annex")),
        list(sub2.git_get_branch_commits("git-annex")))


@with_testrepos('submodule_annex', flavors=['clone'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_submodule(origin, src_path, target_1, target_2):
    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")

    # first, try publishing from super dataset using `path`
    source_super = source
    source_sub = Dataset(opj(src_path, 'sub1'))
    target = GitRepo(target_1, create=True)
    target.git_checkout("TMP", "-b")
    source_sub.repo.git_remote_add("target", target_1)

    res = publish(dataset=source_super, dest="target", path="sub1")
    assert_is_instance(res, Dataset)
    eq_(res.path, source_sub.path)

    eq_(list(GitRepo(target_1, create=False).git_get_branch_commits("master")),
        list(source_sub.repo.git_get_branch_commits("master")))
    eq_(list(GitRepo(target_1, create=False).git_get_branch_commits("git-annex")),
        list(source_sub.repo.git_get_branch_commits("git-annex")))

    # now, publish directly from within submodule:
    target = GitRepo(target_2, create=True)
    target.git_checkout("TMP", "-b")
    source_sub.repo.git_remote_add("target2", target_2)

    res = publish(dataset=source_sub, dest="target2")
    eq_(res, source_sub)

    eq_(list(GitRepo(target_2, create=False).git_get_branch_commits("master")),
        list(source_sub.repo.git_get_branch_commits("master")))
    eq_(list(GitRepo(target_2, create=False).git_get_branch_commits("git-annex")),
        list(source_sub.repo.git_get_branch_commits("git-annex")))


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_with_data(origin, src_path, dst_path):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")
    source.repo.get('test-annex.dat')

    # create plain git at target:
    target = AnnexRepo(dst_path, create=True)
    target.git_checkout("TMP", "-b")
    source.repo.git_remote_add("target", dst_path)

    res = publish(dataset=source, dest="target", with_data=['test-annex.dat'])
    eq_(res, source)

    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))
    # TODO: last commit in git-annex branch differs. Probably fine,
    # but figure out, when exactly to expect this for proper testing:
    eq_(list(target.git_get_branch_commits("git-annex"))[1:],
        list(source.repo.git_get_branch_commits("git-annex"))[1:])

    # we need compare target/master:
    target.git_checkout("master")
    eq_(target.file_has_content(['test-annex.dat']), [True])


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_publish_file_handle(origin, src_path, dst_path):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")
    source.repo.get('test-annex.dat')

    # create plain git at target:
    target = AnnexRepo(dst_path, create=True)
    # actually not needed for this test, but provide same setup as
    # everywhere else:
    target.git_checkout("TMP", "-b")
    source.repo.git_remote_add("target", dst_path)

    # directly publish a file handle, not the dataset itself:
    res = publish(dataset=source, dest="target", path="test-annex.dat")
    eq_(res, opj(source.path, 'test-annex.dat'))

    # only file was published, not the dataset itself:
    assert_not_in("master", target.git_get_branches())
    eq_(Dataset(dst_path).get_dataset_handles(), [])
    assert_not_in("test.dat", target.git_get_files())

    # content is now available from 'target':
    assert_in("target",
              source.repo.annex_whereis('test-annex.dat',
                                        output="descriptions"))
    source.repo.annex_drop('test-annex.dat')
    eq_(source.repo.file_has_content(['test-annex.dat']), [False])
    source.repo._run_annex_command('get', annex_options=['test-annex.dat',
                                                         '--from=target'])
    eq_(source.repo.file_has_content(['test-annex.dat']), [True])

    # TODO: While content appears to be available from 'target' if requested by
    # source, target's annex doesn't know about the file.
    # Figure out, whether this should behave differently and how ...
    # eq_(target.file_has_content(['test-annex.dat']), [True])


# Note: add remote currently disabled in publish
#
# @with_testrepos('submodule_annex', flavors=['local'])
# @with_tempfile(mkdir=True)
# @with_tempfile(mkdir=True)
# def test_publish_add_remote(origin, src_path, dst_path):
#
#     # prepare src
#     source = install(path=src_path, source=origin, recursive=True)
#     # TODO: For now, circumnavigate the detached head issue.
#     # Figure out, what to do.
#     for subds in source.get_dataset_handles(recursive=True):
#         AnnexRepo(opj(src_path, subds), init=True, create=True).git_checkout("master")
#     sub1 = GitRepo(opj(src_path, 'sub1'))
#     sub2 = GitRepo(opj(src_path, 'sub2'))
#
#     # create plain git at target locations:
#     # we want to test URL-template, so create the desired list in FS at
#     # destination:
#     pub_path_super = opj(dst_path, basename(src_path))
#     pub_path_sub1 = opj(dst_path, basename(src_path) + '-sub1')
#     pub_path_sub2 = opj(dst_path, basename(src_path) + '-sub2')
#     super_target = GitRepo(pub_path_super, create=True)
#     super_target.git_checkout("TMP", "-b")
#     sub1_target = GitRepo(pub_path_sub1, create=True)
#     sub1_target.git_checkout("TMP", "-b")
#     sub2_target = GitRepo(pub_path_sub2, create=True)
#     sub2_target.git_checkout("TMP", "-b")
#
#     url_template = dst_path + os.path.sep + '%NAME'
#
#     res = publish(dataset=source, dest="target",
#             dest_url=url_template,
#             recursive=True)
#
#     # testing result list
#     # (Note: Dataset lacks __eq__ for now. Should this be based on path only?)
#     assert_is_instance(res, list)
#     for item in res:
#         assert_is_instance(item, Dataset)
#     eq_(res[0].path, src_path)
#     eq_(res[1].path, sub1.path)
#     eq_(res[2].path, sub2.path)
#
#
#     eq_(list(super_target.git_get_branch_commits("master")),
#         list(source.repo.git_get_branch_commits("master")))
#     eq_(list(super_target.git_get_branch_commits("git-annex")),
#         list(source.repo.git_get_branch_commits("git-annex")))
#
#     eq_(list(sub1_target.git_get_branch_commits("master")),
#         list(sub1.git_get_branch_commits("master")))
#     eq_(list(sub1_target.git_get_branch_commits("git-annex")),
#         list(sub1.git_get_branch_commits("git-annex")))
#
#     eq_(list(sub2_target.git_get_branch_commits("master")),
#         list(sub2.git_get_branch_commits("master")))
#     eq_(list(sub2_target.git_get_branch_commits("git-annex")),
#         list(sub2.git_get_branch_commits("git-annex")))
