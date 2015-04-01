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

from nose.tools import assert_raises, assert_is_instance, assert_true
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged
from datalad.cmd import Runner


@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo(dst, src)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    assert_raises(GitCommandError, GitRepo, dst, src)


@assert_cwd_unchanged
@with_testrepos(flavors=['local'])
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
@with_tempfile
def test_GitRepo_add(path):

    gr = GitRepo(path)

    cwd = os.getcwd()
    os.chdir(path)
    filename = "test_git_add.dat"
    f = open(filename, 'w')
    f.write("File to add to git")
    f.close()

    gr.git_add([filename])
    runner = Runner()
    st, out = runner.run(['git', 'ls-files'], return_output=True)
    assert_true(out.__str__().find(filename) > -1, "%s not successfully added to %s" % (filename, path))

    os.chdir(cwd)


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path):

    gr = GitRepo(path)

    cwd = os.getcwd()
    os.chdir(path)
    filename = "test_git_add.dat"
    f = open(filename, 'w')
    f.write("File to add to git")
    f.close()

    gr.git_add([filename])
    gr.git_commit("Testing GitRepo.git_commit().")
    runner = Runner()
    st, out = runner.run(['git', 'status'], return_output=True)
    assert_true(out.__str__().find("nothing to commit, working directory clean") > -1, "commit to %s failed." % path)

    os.chdir(cwd)

