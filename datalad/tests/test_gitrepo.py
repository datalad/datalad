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

from os.path import join as opj

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_in
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo, normalize_paths, _normalize_path
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, on_windows,\
    with_tree, get_most_obscure_supported_name, ok_clean_git
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.cmd import Runner

from .utils import swallow_logs

from .utils import local_testrepo_flavors


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo(dst, src)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(opj(dst, '.git')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    with swallow_logs() as logs:
        assert_raises(GitCommandError, GitRepo, dst, src)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
def test_GitRepo_instance_from_existing(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(opj(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_instance_brand_new(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(os.path.exists(opj(path, '.git')))
    ok_clean_git(path, annex=False)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_add(src, path):

    gr = GitRepo(path, src)
    filename = get_most_obscure_supported_name()
    with open(opj(path, filename), 'w') as f:
        f.write("File to add to git")
    gr.git_add(filename)

    assert_in(filename, gr.get_indexed_files(), "%s not successfully added to %s" % (filename, path))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path):

    gr = GitRepo(path)
    filename = get_most_obscure_supported_name()
    with open(opj(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.git_add(filename)
    gr.git_commit("Testing GitRepo.git_commit().")
    ok_clean_git(path, annex=False, untracked=[])


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_get_indexed_files(src, path):

    gr = GitRepo(path, src)
    idx_list = gr.get_indexed_files()

    runner = Runner()
    out = runner(['git', 'ls-files'], cwd=path)
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

    # result = _normalize_path(gr.path, opj('.', 'testfile'))
    # assert_equal(result, "testfile", "_normalize_path() returned %s" % result)
    #
    # result = _normalize_path(gr.path, opj('testdir', '..', 'testfile'))
    # assert_equal(result, "testfile", "_normalize_path() returned %s" % result)
    # Note: By now, normpath within normalize_paths() is disabled, therefore
    # disable these tests.

    result = _normalize_path(gr.path, opj('testdir', 'testfile'))
    assert_equal(result, opj("testdir", "testfile"), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, opj(git_path, "testfile"))
    assert_equal(result, "testfile", "_normalize_path() returned %s" % result)

    # now we are inside, so relative paths are relative to cwd and have
    # to be converted to be relative to annex_path:
    os.chdir(opj(git_path, 'd1', 'd2'))

    result = _normalize_path(gr.path, "testfile")
    assert_equal(result, opj('d1', 'd2', 'testfile'), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, opj('..', 'testfile'))
    assert_equal(result, opj('d1', 'testfile'), "_normalize_path() returned %s" % result)

    assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, opj(git_path, '..', 'outside'))

    result = _normalize_path(gr.path, opj(git_path, 'd1', 'testfile'))
    assert_equal(result, opj('d1', 'testfile'), "_normalize_path() returned %s" % result)

    os.chdir(cwd)


def test_GitRepo_files_decorator():

    class testclass(object):
        def __init__(self):
            self.path = opj('some', 'where')

        @normalize_paths
        def decorated_many(self, files):
            return files

        @normalize_paths
        def decorated_one(self, file_):
            return file_


    test_instance = testclass()

    # When a single file passed -- single path returned
    obscure_filename = get_most_obscure_supported_name()
    file_to_test = opj(test_instance.path, 'deep', obscure_filename)
    assert_equal(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))
    assert_equal(test_instance.decorated_one(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))

    file_to_test = obscure_filename
    assert_equal(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))
    assert_equal(test_instance.decorated_one(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))


    file_to_test = opj(obscure_filename, 'beyond', 'obscure')
    assert_equal(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))

    file_to_test = opj(os.getcwd(), 'somewhere', 'else', obscure_filename)
    assert_raises(FileNotInRepositoryError, test_instance.decorated_many,
                  file_to_test)

    # If a list passed -- list returned
    files_to_test = ['now', opj('a list', 'of'), 'paths']
    expect = []
    for item in files_to_test:
        expect.append(_normalize_path(test_instance.path, item))
    assert_equal(test_instance.decorated_many(files_to_test), expect)

    assert_raises(ValueError, test_instance.decorated_many, 1)
