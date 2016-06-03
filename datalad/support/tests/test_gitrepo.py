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
from os.path import join as opj, exists, realpath, curdir, pardir, abspath

from git.exc import GitCommandError, NoSuchPathError, InvalidGitRepositoryError
from nose.tools import assert_raises, assert_is_instance, assert_true, \
    eq_, assert_in, assert_false, assert_not_equal, assert_not_in

from datalad.support.gitrepo import GitRepo, normalize_paths, _normalize_path, \
    split_remote_branch
from ...tests.utils import SkipTest
from ...tests.utils import assert_re_in
from ...tests.utils import local_testrepo_flavors
from ...tests.utils import ok_
from ...tests.utils import skip_if_no_network
from ...tests.utils import swallow_logs
from ...tests.utils import with_tempfile, with_testrepos, \
    assert_cwd_unchanged, with_tree, \
    get_most_obscure_supported_name, ok_clean_git
from ...tests.utils import skip_ssh
from ...tests.utils_testrepos import BasicAnnexTestRepo
from ...cmd import Runner
from ...support.exceptions import FileNotInRepositoryError
from ...utils import getpwd, chpwd


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
@with_tempfile
def test_GitRepo_instance_from_not_existing(path, path2):
    # 1. create=False and path doesn't exist:
    assert_raises(NoSuchPathError, GitRepo, path, create=False)
    assert_false(exists(path))

    # 2. create=False, path exists, but no git repo:
    os.mkdir(path)
    assert_true(exists(path))
    assert_raises(InvalidGitRepositoryError, GitRepo, path, create=False)
    assert_false(exists(opj(path, '.git')))

    # 3. create=True, path doesn't exist:
    gr = GitRepo(path2, create=True)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(exists(opj(path2, '.git')))
    ok_clean_git(path2, annex=False)

    # 4. create=True, path exists, but no git repo:
    gr = GitRepo(path, create=True)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_true(exists(opj(path, '.git')))
    ok_clean_git(path, annex=False)


@with_tempfile
@with_tempfile
def test_GitRepo_equals(path1, path2):

    repo1 = GitRepo(path1)
    repo2 = GitRepo(path1)
    ok_(repo1 == repo2)
    eq_(repo1, repo2)
    repo2 = GitRepo(path2)
    assert_not_equal(repo1, repo2)
    ok_(repo1 != repo2)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_add(src, path):

    gr = GitRepo(path, src)
    filename = get_most_obscure_supported_name()
    with open(opj(path, filename), 'w') as f:
        f.write("File to add to git")
    gr.add(filename)

    assert_in(filename, gr.get_indexed_files(), "%s not successfully added to %s" % (filename, path))


@assert_cwd_unchanged
@with_tree(tree={
    'd': {'f1': 'content1',
          'f2': 'content2'},
    'file': 'content3',
    'd2': {'f1': 'content1',
          'f2': 'content2'},
    'file2': 'content3'

    })
def test_GitRepo_remove(path):

    gr = GitRepo(path, create=True)
    gr.add('*')
    gr.commit("committing all the files")

    eq_(gr.remove('file'), ['file'])
    eq_(set(gr.remove('d', r=True, f=True)), {'d/f1', 'd/f2'})

    eq_(set(gr.remove('*', r=True, f=True)), {'file2', 'd2/f1', 'd2/f2'})

@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path):

    gr = GitRepo(path)
    filename = get_most_obscure_supported_name()
    with open(opj(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.add(filename)
    gr.commit("Testing GitRepo.commit().")
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

    gr = GitRepo(git_path)

    # cwd is currently outside the repo, so any relative path
    # should be interpreted as relative to `annex_path`
    assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, getpwd())

    result = _normalize_path(gr.path, "testfile")
    eq_(result, "testfile", "_normalize_path() returned %s" % result)

    # result = _normalize_path(gr.path, opj('.', 'testfile'))
    # eq_(result, "testfile", "_normalize_path() returned %s" % result)
    #
    # result = _normalize_path(gr.path, opj('testdir', '..', 'testfile'))
    # eq_(result, "testfile", "_normalize_path() returned %s" % result)
    # Note: By now, normpath within normalize_paths() is disabled, therefore
    # disable these tests.

    result = _normalize_path(gr.path, opj('testdir', 'testfile'))
    eq_(result, opj("testdir", "testfile"), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, opj(git_path, "testfile"))
    eq_(result, "testfile", "_normalize_path() returned %s" % result)

    # now we are inside, so
    # OLD PHILOSOPHY: relative paths are relative to cwd and have
    # to be converted to be relative to annex_path
    # NEW PHILOSOPHY: still relative to repo! unless starts with . (curdir) or .. (pardir)
    with chpwd(opj(git_path, 'd1', 'd2')):

        result = _normalize_path(gr.path, "testfile")
        eq_(result, 'testfile', "_normalize_path() returned %s" % result)

        # if not joined as directory name but just a prefix to the filename, should
        # behave correctly
        for d in (curdir, pardir):
            result = _normalize_path(gr.path, d + "testfile")
            eq_(result, d + 'testfile', "_normalize_path() returned %s" % result)

        result = _normalize_path(gr.path, opj(curdir, "testfile"))
        eq_(result, opj('d1', 'd2', 'testfile'), "_normalize_path() returned %s" % result)

        result = _normalize_path(gr.path, opj(pardir, 'testfile'))
        eq_(result, opj('d1', 'testfile'), "_normalize_path() returned %s" % result)

        assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, opj(git_path, '..', 'outside'))

        result = _normalize_path(gr.path, opj(git_path, 'd1', 'testfile'))
        eq_(result, opj('d1', 'testfile'), "_normalize_path() returned %s" % result)


def test_GitRepo_files_decorator():

    class testclass(object):
        def __init__(self):
            self.path = opj('some', 'where')

        # TODO
        # yoh:  logic is alien to me below why to have two since both look identical!
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
    # file doesn't exist
    eq_(test_instance.decorated_one(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))
    eq_(test_instance.decorated_one(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))

    file_to_test = obscure_filename
    eq_(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))
    eq_(test_instance.decorated_one(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))


    file_to_test = opj(obscure_filename, 'beyond', 'obscure')
    eq_(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))

    file_to_test = opj(getpwd(), 'somewhere', 'else', obscure_filename)
    assert_raises(FileNotInRepositoryError, test_instance.decorated_many,
                  file_to_test)

    # If a list passed -- list returned
    files_to_test = ['now', opj('a list', 'of'), 'paths']
    expect = []
    for item in files_to_test:
        expect.append(_normalize_path(test_instance.path, item))
    eq_(test_instance.decorated_many(files_to_test), expect)

    eq_(test_instance.decorated_many(''), [])

    assert_raises(ValueError, test_instance.decorated_many, 1)
    assert_raises(ValueError, test_instance.decorated_one, 1)


@skip_if_no_network
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_add(orig_path, path):

    gr = GitRepo(path, orig_path)
    out = gr.show_remotes()
    assert_in('origin', out)
    eq_(len(out), 1)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    out = gr.show_remotes()
    assert_in('origin', out)
    assert_in('github', out)
    eq_(len(out), 2)
    out = gr.show_remotes('github')
    assert_in('  Fetch URL: git://github.com/datalad/testrepo--basic--r1', out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_remove(orig_path, path):

    gr = GitRepo(path, orig_path)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    gr.remove_remote('github')
    out = gr.show_remotes()
    eq_(len(out), 1)
    assert_in('origin', out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_show(orig_path, path):

    gr = GitRepo(path, orig_path)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    out = gr.show_remotes(verbose=True)
    eq_(len(out), 4)
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
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    eq_(gr.get_remote_url('origin'), orig_path)
    eq_(gr.get_remote_url('github'),
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
    origin.add(filename)
    origin.commit("new file added.")
    clone.pull()
    assert_true(exists(opj(clone_path, filename)))


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
@with_tempfile
def test_GitRepo_fetch(test_path, orig_path, clone_path):

    origin = GitRepo(orig_path, test_path)
    clone = GitRepo(clone_path, orig_path)
    filename = get_most_obscure_supported_name()

    origin.checkout("new_branch", "-b")
    with open(opj(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.add(filename)
    origin.commit("new file added.")

    clone.fetch(remote='origin')

    ok_clean_git(clone.path, annex=False)
    assert_in("origin/new_branch", clone.get_remote_branches())
    assert_in(filename, clone.get_files("origin/new_branch"))
    assert_false(exists(opj(clone_path, filename)))  # not checked out


@skip_ssh
@with_testrepos('.*basic.*', flavors=['local'])
@with_tempfile
def test_GitRepo_ssh_fetch(remote_path, repo_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=False)
    url = "ssh://localhost" + abspath(remote_path)
    socket_path = opj(ssh_manager.socket_dir, 'localhost')
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # we don't know any branches of the remote:
    eq_([], repo.get_remote_branches())

    repo.fetch(remote="ssh-remote")
    ok_clean_git(repo.path, annex=False)

    # the connection is known to the SSH manager, since fetch() requested it:
    assert_in(socket_path, ssh_manager._connections)
    # and socket was created:
    ok_(exists(socket_path))

    # we actually fetched it:
    assert_in('ssh-remote/master', repo.get_remote_branches())


@skip_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_pull(remote_path, repo_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=True)
    url = "ssh://localhost" + abspath(remote_path)
    socket_path = opj(ssh_manager.socket_dir, 'localhost')
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify remote:
    remote_repo.checkout("ssh-test", "-b")
    with open(opj(remote_repo.path, "ssh_testfile.dat"), "w") as f:
        f.write("whatever")
    remote_repo.add("ssh_testfile.dat")
    remote_repo.commit("ssh_testfile.dat added.")

    # file is not locally known yet:
    assert_not_in("ssh_testfile.dat", repo.get_indexed_files())

    # pull changes:
    repo.pull(remote="ssh-remote", refspec=remote_repo.get_active_branch())
    ok_clean_git(repo.path, annex=False)

    # the connection is known to the SSH manager, since fetch() requested it:
    assert_in(socket_path, ssh_manager._connections)
    # and socket was created:
    ok_(exists(socket_path))

    # we actually pulled the changes
    assert_in("ssh_testfile.dat", repo.get_indexed_files())


@skip_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_push(repo_path, remote_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=True)
    url = "ssh://localhost" + abspath(remote_path)
    socket_path = opj(ssh_manager.socket_dir, 'localhost')
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify local repo:
    repo.checkout("ssh-test", "-b")
    with open(opj(repo.path, "ssh_testfile.dat"), "w") as f:
        f.write("whatever")
    repo.add("ssh_testfile.dat")
    repo.commit("ssh_testfile.dat added.")

    # file is not known to the remote yet:
    assert_not_in("ssh_testfile.dat", remote_repo.get_indexed_files())

    # push changes:
    repo.push(remote="ssh-remote", refspec="ssh-test")

    # the connection is known to the SSH manager, since fetch() requested it:
    assert_in(socket_path, ssh_manager._connections)
    # and socket was created:
    ok_(exists(socket_path))

    # remote now knows the changes:
    assert_in("ssh-test", remote_repo.get_branches())
    assert_in("ssh_testfile.dat", remote_repo.get_files("ssh-test"))


@with_tempfile
@with_tempfile
def test_GitRepo_push_n_checkout(orig_path, clone_path):

    origin = GitRepo(orig_path)
    clone = GitRepo(clone_path, orig_path)
    filename = get_most_obscure_supported_name()

    with open(opj(clone_path, filename), 'w') as f:
        f.write("New file.")
    clone.add(filename)
    clone.commit("new file added.")
    # TODO: need checkout first:
    clone.push('origin', '+master:new-branch')
    origin.checkout('new-branch')
    assert_true(exists(opj(orig_path, filename)))


@with_tempfile
@with_tempfile
@with_tempfile
def test_GitRepo_remote_update(path1, path2, path3):

    git1 = GitRepo(path1)
    git2 = GitRepo(path2)
    git3 = GitRepo(path3)

    git1.add_remote('git2', path2)
    git1.add_remote('git3', path3)

    # Setting up remote 'git2'
    with open(opj(path2, 'masterfile'), 'w') as f:
        f.write("git2 in master")
    git2.add('masterfile')
    git2.commit("Add something to master.")
    git2.checkout('branch2', '-b')
    with open(opj(path2, 'branch2file'), 'w') as f:
        f.write("git2 in branch2")
    git2.add('branch2file')
    git2.commit("Add something to branch2.")

    # Setting up remote 'git3'
    with open(opj(path3, 'masterfile'), 'w') as f:
        f.write("git3 in master")
    git3.add('masterfile')
    git3.commit("Add something to master.")
    git3.checkout('branch3', '-b')
    with open(opj(path3, 'branch3file'), 'w') as f:
        f.write("git3 in branch3")
    git3.add('branch3file')
    git3.commit("Add something to branch3.")

    git1.update_remote()

    # checkouts are 'tests' themselves, since they'll raise CommandError
    # if something went wrong
    git1.checkout('branch2')
    git1.checkout('branch3')

    branches1 = git1.get_branches()
    eq_({'branch2', 'branch3'}, set(branches1))


# TODO: Why was it "flavors=local_testrepo_flavors" ? What's the windows issue here?
@with_testrepos('.*git.*', flavors=['clone'])
@with_tempfile
def test_GitRepo_get_files(url, path):

    gr = GitRepo(path, url)

    # get the expected files via os for comparison:
    os_files = set()
    for (dirpath, dirnames, filenames) in os.walk(path):
        rel_dir = os.path.relpath(dirpath, start=path)
        if rel_dir.startswith(".git"):
            continue
        for file_ in filenames:
            os_files.add(opj(rel_dir, file_).lstrip("./"))

    # get the files via GitRepo:
    local_files = set(gr.get_files())
    remote_files = set(gr.get_files(branch="origin/master"))

    eq_(local_files, set(gr.get_indexed_files()))
    eq_(local_files, remote_files)
    eq_(local_files, os_files)

    # create a different branch:
    gr.checkout('new_branch', '-b')
    filename = 'another_file.dat'
    with open(opj(path, filename), 'w') as f:
        f.write("something")
    gr.add(filename)
    gr.commit("Added.")

    # now get the files again:
    local_files = set(gr.get_files())
    eq_(local_files, os_files.union({filename}))
    # retrieve remote branch again, which should not have changed:
    remote_files = set(gr.get_files(branch="origin/master"))
    eq_(remote_files, os_files)
    eq_(set([filename]), local_files.difference(remote_files))

    # switch back and query non-active branch:
    gr.checkout('master')
    local_files = set(gr.get_files())
    branch_files = set(gr.get_files(branch="new_branch"))
    eq_(set([filename]), branch_files.difference(local_files))


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile(mkdir=True)
def test_GitRepo_get_toppath(repo, tempdir):
    reporeal = realpath(repo)
    eq_(GitRepo.get_toppath(repo), reporeal)
    # Generate some nested directory
    nested = opj(repo, "d1", "d2")
    os.makedirs(nested)
    eq_(GitRepo.get_toppath(nested), reporeal)
    # and if not under git, should return None
    eq_(GitRepo.get_toppath(tempdir), None)

def test_GitRepo_dirty():
    trepo = BasicAnnexTestRepo()
    repo = trepo.repo
    # empty at this point -- should not be dirty as well. TODO
    assert_false(repo.dirty)
    trepo.create()
    assert_false(repo.dirty)

    # new file added to index
    trepo.create_file('newfiletest.dat', '123\n', annex=False)
    assert_true(repo.dirty)
    repo.commit("just a commit")
    assert_false(repo.dirty)

    # file modified to be the same
    trepo.create_file('newfiletest.dat', '123\n', annex=False)
    assert_false(repo.dirty)

    # file modified
    trepo.create_file('newfiletest.dat', '12\n', annex=False)
    assert_true(repo.dirty)
    repo.commit("just a commit")
    assert_false(repo.dirty)

    # new file not added to index
    trepo.create_file('newfiletest2.dat', '123\n', add=False, annex=False)
    assert_true(repo.dirty)
    os.unlink(opj(repo.path, 'newfiletest2.dat'))
    assert_false(repo.dirty)

    # new annexed file
    trepo.create_file('newfiletest2.dat', '123\n', annex=True)
    assert_true(repo.dirty)
    repo.commit("just a commit")
    assert_false(repo.dirty)


@with_tempfile(mkdir=True)
def test_GitRepo_get_merge_base(src):
    repo = GitRepo(src, create=True)
    with open(opj(src, 'file.txt'), 'w') as f:
        f.write('load')
    repo.add('*')
    repo.commit('committing')

    assert_raises(ValueError, repo.get_merge_base, [])
    branch1 = repo.get_active_branch()
    branch1_hexsha = repo.get_hexsha()
    eq_(len(branch1_hexsha), 40)
    eq_(repo.get_merge_base(branch1), branch1_hexsha)

    # Let's create a detached branch
    branch2 = "_detach_"
    repo.checkout(branch2, options="--orphan")
    # it will have all the files
    # Must not do:  https://github.com/gitpython-developers/GitPython/issues/375
    # repo.git_add('.')
    repo.add('*')
    # NOTE: fun part is that we should have at least a different commit message
    # so it results in a different checksum ;)
    repo.commit("committing again")
    assert(repo.get_indexed_files())  # we did commit
    assert(repo.get_merge_base(branch1) is None)
    assert(repo.get_merge_base([branch2, branch1]) is None)

    # Let's merge them up -- then merge base should match the master
    repo.merge(branch1)
    eq_(repo.get_merge_base(branch1), branch1_hexsha)

    # if points to some empty/non-existing branch - should also be None
    assert(repo.get_merge_base(['nonexistent', branch2]) is None)


@with_tempfile(mkdir=True)
def test_GitRepo_git_get_branch_commits(src):

    repo = GitRepo(src, create=True)
    with open(opj(src, 'file.txt'), 'w') as f:
        f.write('load')
    repo.add('*')
    repo.commit('committing')

    commits = list(repo.get_branch_commits('master'))
    eq_(len(commits), 1)
    commits_stop0 = list(repo.get_branch_commits('master', stop=commits[0].hexsha))
    eq_(commits_stop0, [])
    commits_hexsha = list(repo.get_branch_commits('master', value='hexsha'))
    commits_hexsha_left = list(repo.get_branch_commits('master', value='hexsha', limit='left-only'))
    eq_([commits[0].hexsha], commits_hexsha)
    # our unittest is rudimentary ;-)
    eq_(commits_hexsha_left, commits_hexsha)

    raise SkipTest("TODO: Was more of a smoke test -- improve testing")


def test_split_remote_branch():
    r, b = split_remote_branch("MyRemote/SimpleBranch")
    eq_(r, "MyRemote")
    eq_(b, "SimpleBranch")
    r, b = split_remote_branch("MyRemote/Branch/with/slashes")
    eq_(r, "MyRemote")
    eq_(b, "Branch/with/slashes")
    assert_raises(AssertionError, split_remote_branch, "NoSlashesAtAll")
    assert_raises(AssertionError, split_remote_branch, "TrailingSlash/")


def test_get_added_files_commit_msg():
    f = GitRepo._get_added_files_commit_msg
    eq_(f([]), 'No files were added')
    eq_(f(["f1"]), 'Added 1 file\n\nFiles:\nf1')
    eq_(f(["f1", "f2"]), 'Added 2 files\n\nFiles:\nf1\nf2')