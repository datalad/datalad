# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class GitRepo

Note: There's not a lot to test by now.

"""

import os
import os.path

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_in
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, ok_clean_git, on_windows
from datalad.cmd import Runner

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo(dst, src)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    assert_raises(GitCommandError, GitRepo, dst, src)


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
def test_GitRepo_instance_from_existing(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_instance_brand_new(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_GitRepo_add(src, path):

    gr = GitRepo(path, src)
    filename = "test_git_add.dat"
    with open(os.path.join(path, filename), 'w') as f:
        f.write("File to add to git")
    gr.git_add([filename])

    assert_in(filename, gr.get_indexed_files(), "%s not successfully added to %s" % (filename, path))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path):

    gr = GitRepo(path)
    filename = "test_git_add.dat"
    with open(os.path.join(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.git_add([filename])
    gr.git_commit("Testing GitRepo.git_commit().")
    ok_clean_git(path, annex=False, untracked=[])


@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_GitRepo_get_indexed_files(src, path):

    gr = GitRepo(path, src)
    idx_list = gr.get_indexed_files()

    runner = Runner()
    st, out = runner.run(['git', 'ls-files'], return_output=True, cwd=path)
    out_list = out[0].split()

    for item in idx_list:
        assert_in(item, out_list, "%s not found in output of git ls-files in %s" % (item, path))
    for item in out_list:
        assert_in(item, idx_list, "%s not found in output of get_indexed_files in %s" % (item, path))
