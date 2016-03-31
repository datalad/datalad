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
from os.path import join as opj, abspath
from ..dataset import Dataset
from datalad.api import publish, install
from datalad.distribution.install import get_containing_subdataset
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false
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
        AnnexRepo(opj(src_path, subds), init=True, create=False).git_checkout("master")

    # create plain git at target:
    target = GitRepo(dst_path, create=True)
    target.git_checkout("TMP", "-b")
    source.repo.git_remote_add("target", dst_path)

    publish(dataset=source, dest="target")

    ok_clean_git(src_path, annex=False)
    ok_clean_git(dst_path, annex=False)
    eq_(list(target.git_get_branch_commits("master")),
        list(source.repo.git_get_branch_commits("master")))

    # don't fail when doing it again
    publish(dataset=source, dest="target")

    ok_clean_git(src_path, annex=False)
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
        AnnexRepo(opj(src_path, subds), init=True, create=False).git_checkout("master")

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
    # TODO: Currently, annex init is necessary, due to improper testrepos
    sub1 = AnnexRepo(opj(src_path, 'sub1'), init=True, create=False)
    sub2 = AnnexRepo(opj(src_path, 'sub2'), init=True, create=False)
    sub1.git_remote_add("target", sub1_pub)
    sub2.git_remote_add("target", sub2_pub)

    # publish recursively
    publish(dataset=source, dest="target", recursive=True)

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
        AnnexRepo(opj(src_path, subds), init=True, create=False).git_checkout("master")

    # first, try publishing from super dataset using `path`
    source_super = source
    source_sub = Dataset(opj(src_path, 'sub1'))
    target = GitRepo(target_1, create=True)
    target.git_checkout("TMP", "-b")
    source_sub.repo.git_remote_add("target", target_1)

    publish(dataset=source_super, dest="target", path="sub1")

    eq_(list(GitRepo(target_1, create=False).git_get_branch_commits("master")),
        list(source_sub.repo.git_get_branch_commits("master")))
    eq_(list(GitRepo(target_1, create=False).git_get_branch_commits("git-annex")),
        list(source_sub.repo.git_get_branch_commits("git-annex")))

    # now, publish directly from within submodule:
    target = GitRepo(target_2, create=True)
    target.git_checkout("TMP", "-b")
    source_sub.repo.git_remote_add("target2", target_2)
    publish(dataset=source_sub, dest="target2")

    eq_(list(GitRepo(target_2, create=False).git_get_branch_commits("master")),
        list(source_sub.repo.git_get_branch_commits("master")))
    eq_(list(GitRepo(target_2, create=False).git_get_branch_commits("git-annex")),
        list(source_sub.repo.git_get_branch_commits("git-annex")))


def test_publish_with_data():
    raise SkipTest("TODO")


def test_publish_default_target():
    raise SkipTest("TODO")


def test_publish_add_remote():
    raise SkipTest("TODO")

