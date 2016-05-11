# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test update action

"""

import os
from os.path import join as opj, abspath, basename
from ..dataset import Dataset
from datalad.api import update, install
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
from datalad.tests.utils import ok_clean_git, swallow_outputs


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_simple(origin, src_path, dst_path):

    # prepare src
    source = install(path=src_path, source=origin, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in source.get_dataset_handles(recursive=True):
        AnnexRepo(opj(src_path, subds), init=True,
                  create=True).git_checkout("master")
    # forget we cloned it (provide no 'origin' anymore), which should lead to
    # setting tracking branch to target:
    source.repo.git_remote_remove("origin")

    # get a clone to update later on:
    dest = install(path=dst_path, source=src_path, recursive=True)
    # TODO: For now, circumnavigate the detached head issue.
    # Figure out, what to do.
    for subds in dest.get_dataset_handles(recursive=True):
        AnnexRepo(opj(dst_path, subds), init=True,
                  create=True).git_checkout("master")
    # test setup done;
    # assert all fine
    ok_clean_git(dst_path)
    ok_clean_git(src_path)

    # update yields nothing => up-to-date
    # TODO: how to test besides not failing?
    dest.update()
    ok_clean_git(dst_path)

    # modify origin:
    with open(opj(src_path, "update.txt"), "w") as f:
        f.write("Additional content")
    source.install(path="update.txt")
    source.remember_state("Added update.txt")
    ok_clean_git(src_path)

    # update without `merge` only fetches:
    dest.update()
    # modification is not known to active branch:
    assert_not_in("update.txt",
                  dest.repo.git_get_files(dest.repo.git_get_active_branch()))
    # modification is known to branch origin/master
    assert_in("update.txt", dest.repo.git_get_files("origin/master"))

    # merge:
    dest.update(merge=True)
    # modification is now known to active branch:
    assert_in("update.txt",
              dest.repo.git_get_files(dest.repo.git_get_active_branch()))
    # it's known to annex, but has no content yet:
    dest.repo.get_file_key("update.txt")  # raises if unknown
    eq_([False], dest.repo.file_has_content(["update.txt"]))


def test_update_recursive():
    raise SkipTest("TODO")


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_fetch_all(src, remote_1, remote_2):
    rmt1 = AnnexRepo(remote_1, src)
    rmt2 = AnnexRepo(remote_2, src)

    ds = Dataset(src)
    ds.add_sibling(name="sibling_1", url=remote_1)
    ds.add_sibling(name="sibling_2", url=remote_2)

    # modify the remotes:
    with open(opj(remote_1, "first.txt"), "w") as f:
        f.write("some file load")
    rmt1.add_to_annex("first.txt")
    # TODO: Modify an already present file!

    with open(opj(remote_2, "second.txt"), "w") as f:
        f.write("different file load")
    rmt2.git_add("second.txt")
    rmt2.git_commit("Add file to git.")

    # fetch all remotes
    ds.update(fetch_all=True)

    # no merge, so changes are not in active branch:
    assert_not_in("first.txt",
                  ds.repo.git_get_files(ds.repo.git_get_active_branch()))
    assert_not_in("second.txt",
                  ds.repo.git_get_files(ds.repo.git_get_active_branch()))
    # but we know the changes in remote branches:
    assert_in("first.txt", ds.repo.git_get_files("sibling_1/master"))
    assert_in("second.txt", ds.repo.git_get_files("sibling_2/master"))

    # no merge strategy for multiple remotes yet:
    assert_raises(NotImplementedError, ds.update, merge=True, fetch_all=True)

    # merge a certain remote:
    ds.update(name="sibling_1", merge=True)

    # changes from sibling_2 still not present:
    assert_not_in("second.txt",
                  ds.repo.git_get_files(ds.repo.git_get_active_branch()))
    # changes from sibling_1 merged:
    assert_in("first.txt",
              ds.repo.git_get_files(ds.repo.git_get_active_branch()))
    # it's known to annex, but has no content yet:
    ds.repo.get_file_key("first.txt")  # raises if unknown
    eq_([False], ds.repo.file_has_content(["first.txt"]))

