# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class GitRepo

"""

import os
import os.path

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_in
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo, files_decorator, _normalize_path
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, on_windows,\
    with_tree, get_most_obscure_supported_name, ok_clean_git
from datalad.support.exceptions import FileNotInRepositoryError
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
    gr.git_add(filename)

    assert_in(filename, gr.get_indexed_files(), "%s not successfully added to %s" % (filename, path))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path):

    gr = GitRepo(path)
    filename = "test_git_add.dat"
    with open(os.path.join(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.git_add(filename)
    gr.git_commit("Testing GitRepo.git_commit().")
    ok_clean_git(path, annex=False, untracked=[])


@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_GitRepo_get_indexed_files(src, path):

    gr = GitRepo(path, src)
    idx_list = gr.get_indexed_files()

    runner = Runner()
    out = runner(['git', 'ls-files'], return_output=True, cwd=path)
    out_list = out[0].split()

    for item in idx_list:
        assert_in(item, out_list, "%s not found in output of git ls-files in %s" % (item, path))
    for item in out_list:
        assert_in(item, idx_list, "%s not found in output of get_indexed_files in %s" % (item, path))


@with_tree([
    ('empty', ''),
    ('d1', (
        ('empty', ''),
        ('d2',
            (('empty', ''),
             )),
        )),
    ])
@assert_cwd_unchanged(ok_to_chdir=True)
def test_normalize_path(git_path):

    cwd = os.getcwd()
    gr = GitRepo(git_path)

    # cwd is currently outside the repo, so any relative path
    # should be interpreted as relative to `annex_path`
    assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, os.getcwd())

    result = _normalize_path(gr.path, "testfile")
    assert_equal(result, "testfile", "_normalize_path() returned %s" % result)

    # result = _normalize_path(gr.path, os.path.join('.', 'testfile'))
    # assert_equal(result, "testfile", "_normalize_path() returned %s" % result)
    #
    # result = _normalize_path(gr.path, os.path.join('testdir', '..', 'testfile'))
    # assert_equal(result, "testfile", "_normalize_path() returned %s" % result)
    # Note: By now, normpath within normalize_paths() is disabled, therefore
    # disable these tests.

    result = _normalize_path(gr.path, os.path.join('testdir', 'testfile'))
    assert_equal(result, os.path.join("testdir", "testfile"), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, os.path.join(git_path, "testfile"))
    assert_equal(result, "testfile", "_normalize_path() returned %s" % result)

    # now we are inside, so relative paths are relative to cwd and have
    # to be converted to be relative to annex_path:
    os.chdir(os.path.join(git_path, 'd1', 'd2'))

    result = _normalize_path(gr.path, "testfile")
    assert_equal(result, os.path.join('d1', 'd2', 'testfile'), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, os.path.join('..', 'testfile'))
    assert_equal(result, os.path.join('d1', 'testfile'), "_normalize_path() returned %s" % result)

    assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, os.path.join(git_path, '..', 'outside'))

    result = _normalize_path(gr.path, os.path.join(git_path, 'd1', 'testfile'))
    assert_equal(result, os.path.join('d1', 'testfile'), "_normalize_path() returned %s" % result)

    os.chdir(cwd)


def test_GitRepo_files_decorator():

    class testclass(object):
        def __init__(self):
            self.path = os.path.join('some', 'where')

        @files_decorator
        def decorated(self, files):
            return files

    test_instance = testclass()

    files_to_test = os.path.join(test_instance.path, 'deep', get_most_obscure_supported_name())
    assert_equal(test_instance.decorated(files_to_test),
                 [_normalize_path(test_instance.path, files_to_test)])

    files_to_test = get_most_obscure_supported_name()
    assert_equal(test_instance.decorated(files_to_test),
                 [_normalize_path(test_instance.path, files_to_test)])

    files_to_test = os.path.join(get_most_obscure_supported_name(), 'beyond', 'obscure')
    assert_equal(test_instance.decorated(files_to_test),
                 [_normalize_path(test_instance.path, files_to_test)])

    files_to_test = os.path.join(os.getcwd(), 'somewhere', 'else', get_most_obscure_supported_name())
    assert_raises(FileNotInRepositoryError, test_instance.decorated, files_to_test)

    files_to_test = ['now', os.path.join('a list', 'of'), 'paths']
    expect = []
    for item in files_to_test:
        expect.append(_normalize_path(test_instance.path, item))
    assert_equal(test_instance.decorated(files_to_test), expect)

    assert_raises(ValueError, test_instance.decorated, 1)
