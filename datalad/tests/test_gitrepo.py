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
from os.path import join as opj, exists

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_in
from git.exc import GitCommandError

from datalad.support.gitrepo import GitRepo, normalize_paths, _normalize_path
from datalad.tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, on_windows,\
    with_tree, get_most_obscure_supported_name, ok_clean_git
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.cmd import Runner

from .utils import swallow_logs

from .utils import local_testrepo_flavors
from .utils import assert_re_in


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo(dst, src)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(exists(opj(dst, '.git')))

    # do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    # and therefore can't clone to `dst`
    with swallow_logs() as logs:
        assert_raises(GitCommandError, GitRepo, dst, src)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
def test_GitRepo_instance_from_existing(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(exists(opj(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_instance_brand_new(path):

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(exists(opj(path, '.git')))
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

    assert_equal(test_instance.decorated_many(''), '')

    assert_raises(ValueError, test_instance.decorated_many, 1)
    assert_raises(ValueError, test_instance.decorated_one, 1)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_add(orig_path, path):

    gr = GitRepo(path, orig_path)
    out = gr.git_remote_show()
    assert_in('origin', out)
    assert_equal(len(out), 1)
    gr.git_remote_add('github', 'git://github.com/datalad/testrepo--basic--r1')
    out = gr.git_remote_show()
    assert_in('origin', out)
    assert_in('github', out)
    assert_equal(len(out), 2)
    out = gr.git_remote_show('github')
    assert_in('  Fetch URL: git://github.com/datalad/testrepo--basic--r1', out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_remove(orig_path, path):

    gr = GitRepo(path, orig_path)
    gr.git_remote_add('github', 'git://github.com/datalad/testrepo--basic--r1')
    gr.git_remote_remove('github')
    out = gr.git_remote_show()
    assert_equal(len(out), 1)
    assert_in('origin', out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_show(orig_path, path):

    gr = GitRepo(path, orig_path)
    gr.git_remote_add('github', 'git://github.com/datalad/testrepo--basic--r1')
    out = gr.git_remote_show(verbose=True)
    assert_equal(len(out), 4)
    assert_in('origin\t%s (fetch)' % orig_path, out)
    assert_in('origin\t%s (push)' % orig_path, out)
    # Some fellas might have some fancy rewrite rules for pushes, so we can't
    # just check for specific protocol
    assert_re_in('github\tgit(://|@)github.com[:/]datalad/testrepo--basic--r1 \(fetch\)',
              out)
    assert_re_in('github\tgit(://|@)github.com[:/]datalad/testrepo--basic--r1 \(push\)',
              out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_get_remote_url(orig_path, path):

    gr = GitRepo(path, orig_path)
    gr.git_remote_add('github', 'git://github.com/datalad/testrepo--basic--r1')
    assert_equal(gr.git_get_remote_url('origin'), orig_path)
    assert_equal(gr.git_get_remote_url('github'),
                 'git://github.com/datalad/testrepo--basic--r1')


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
@with_tempfile
def test_GitRepo_pull(test_path, orig_path, clone_path):

    origin = GitRepo(orig_path, test_path)
    clone = GitRepo(clone_path, orig_path)
    filename = get_most_obscure_supported_name()

    with open(opj(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.git_add(filename)
    origin.git_commit("new file added.")
    clone.git_pull()
    assert_true(exists(opj(clone_path, filename)))


@with_tempfile
@with_tempfile
def test_GitRepo_push_n_checkout(orig_path, clone_path):

    origin = GitRepo(orig_path)
    clone = GitRepo(clone_path, orig_path)
    filename = get_most_obscure_supported_name()

    with open(opj(clone_path, filename), 'w') as f:
        f.write("New file.")
    clone.git_add(filename)
    clone.git_commit("new file added.")
    # TODO: need checkout first:
    clone.git_push('origin +master:new-branch')
    origin.git_checkout('new-branch')
    assert_true(exists(opj(orig_path, filename)))


@with_tempfile
@with_tempfile
@with_tempfile
def test_GitRepo_remote_update(path1, path2, path3):

    git1 = GitRepo(path1)
    git2 = GitRepo(path2)
    git3 = GitRepo(path3)

    git1.git_remote_add('git2', path2)
    git1.git_remote_add('git3', path3)

    # Setting up remote 'git2'
    with open(opj(path2, 'masterfile'), 'w') as f:
        f.write("git2 in master")
    git2.git_add('masterfile')
    git2.git_commit("Add something to master.")
    git2.git_checkout('branch2', '-b')
    with open(opj(path2, 'branch2file'), 'w') as f:
        f.write("git2 in branch2")
    git2.git_add('branch2file')
    git2.git_commit("Add something to branch2.")

    # Setting up remote 'git3'
    with open(opj(path3, 'masterfile'), 'w') as f:
        f.write("git3 in master")
    git3.git_add('masterfile')
    git3.git_commit("Add something to master.")
    git3.git_checkout('branch3', '-b')
    with open(opj(path3, 'branch3file'), 'w') as f:
        f.write("git3 in branch3")
    git3.git_add('branch3file')
    git3.git_commit("Add something to branch3.")

    git1.git_remote_update()

    # checkouts are 'tests' themselves, since they'll raise CommandError
    # if something went wrong
    git1.git_checkout('branch2')
    git1.git_checkout('branch3')

    branches1 = git1.git_get_branches()
    assert_equal({'branch2', 'branch3'}, set(branches1))


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
@with_tempfile
def test_GitRepo_get_files(src, path, path2clone):

    # TODO: THIS DOES NOT WORK AS EXPECTED! SEE gitrepo.py!

    gr = GitRepo(path, src)
    assert_equal({'INFO.txt', 'test-annex.dat', 'test.dat'},
                 set(gr.git_get_files()))
    #gr.git_checkout('new_branch', '-b')
    ##filename = get_most_obscure_supported_name()
    #filename = 'another_file.dat'
    #with open(opj(path, filename), 'w') as f:
    #    f.write("something")
    #gr.git_add(filename)
    #gr.git_commit("Added.")
    #assert_equal({'INFO.txt', 'test-annex.dat', 'test.dat', filename},
    #             set(gr.git_get_files()))
    #assert_equal({'INFO.txt', 'test-annex.dat', 'test.dat'},
    #             set(gr.git_get_files('master')),
    #             "return value: %s" % gr.git_get_files('master'))
    #gr2 = GitRepo(path2clone, src)
    #gr2.git_remote_add('remoterepo', path)
    #gr2.git_fetch('remoterepo')






# TODO:
#   def git_fetch(self, name, options=''):

