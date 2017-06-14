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

from nose.tools import assert_is_instance

import os
from datalad.tests.utils import *
from datalad.tests.utils_testrepos import BasicAnnexTestRepo
from datalad.utils import getpwd, chpwd

from datalad.support.sshconnector import get_connection_hash

# imports from same module:
# we want to test everything in gitrepo:
from ..gitrepo import *
from ..gitrepo import _normalize_path
from ..exceptions import FileNotInRepositoryError
from .utils import check_repo_deals_with_inode_change


@with_tempfile(mkdir=True)
def test_GitRepo_invalid_path(path):
    with chpwd(path):
        assert_raises(ValueError, GitRepo, path="git://some/url", create=True)
        ok_(not exists(opj(path, "git:")))
        assert_raises(ValueError, GitRepo, path="file://some/relative/path", create=True)
        ok_(not exists(opj(path, "file:")))


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo.clone(src, dst)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_is_instance(gr.repo, gitpy.Repo,
                       "Failed to instantiate GitPython Repo object.")
    assert_true(exists(opj(dst, '.git')))

    # do it again should raise GitCommandError since git will notice there's
    # already a git-repo at that path and therefore can't clone to `dst`
    # Note: Since GitRepo is now a WeakSingletonRepo, this is prevented from
    # happening atm. Disabling for now:
#    raise SkipTest("Disabled for RF: WeakSingletonRepo")
    with swallow_logs() as logs:
        assert_raises(GitCommandError, GitRepo.clone, src, dst)


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
def test_GitRepo_init_options(path):
    # passing an option, not explicitly defined in GitRepo class:
    gr = GitRepo(path, create=True, bare=True)

    cfg = gr.repo.config_reader()
    ok_(cfg.get_value(section="core", option="bare"))


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
@with_testrepos('.*git.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_add(src, path):

    gr = GitRepo.clone(src, path)
    filename = get_most_obscure_supported_name()
    with open(opj(path, filename), 'w') as f:
        f.write("File to add to git")
    added = gr.add(filename)

    assert_equal(added, {'success': True, 'file': filename})
    assert_in(filename, gr.get_indexed_files(),
              "%s not successfully added to %s" % (filename, path))
    # uncommitted:
    ok_(gr.dirty)

    filename = "another.txt"
    with open(opj(path, filename), 'w') as f:
        f.write("Another file to add to git")
    assert_raises(AssertionError, gr.add, filename, git=False)
    assert_raises(AssertionError, gr.add, filename, git=None)

    # include committing:
    added2 = gr.add(filename, commit=True, msg="Add two files.")
    assert_equal(added2, {'success': True, 'file': filename})

    assert_in(filename, gr.get_indexed_files(),
              "%s not successfully added to %s" % (filename, path))
    ok_clean_git(path)


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
    ok_clean_git(gr)
    eq_("Testing GitRepo.commit().{}".format(linesep),
        gr.repo.head.commit.message)

    with open(opj(path, filename), 'w') as f:
        f.write("changed content")

    gr.add(filename)
    gr.commit("commit with options", options=to_options(dry_run=True))
    # wasn't actually committed:
    ok_(gr.dirty)

    # commit with empty message:
    gr.commit()
    ok_clean_git(gr)

    # nothing to commit doesn't raise by default:
    gr.commit()
    # but does with careless=False:
    assert_raises(CommandError, gr.commit, careless=False)

    # committing untracked file raises:
    with open(opj(path, "untracked"), "w") as f:
        f.write("some")
    assert_raises(FileNotInRepositoryError, gr.commit, files="untracked")
    # not existing file as well:
    assert_raises(FileNotInRepositoryError, gr.commit, files="not-existing")


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_get_indexed_files(src, path):

    gr = GitRepo.clone(src, path)
    idx_list = gr.get_indexed_files()

    runner = Runner()
    out = runner(['git', 'ls-files'], cwd=path)
    out_list = list(filter(bool, out[0].split('\n')))

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

    gr = GitRepo.clone(orig_path, path)
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

    gr = GitRepo.clone(orig_path, path)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    gr.remove_remote('github')
    out = gr.show_remotes()
    eq_(len(out), 1)
    assert_in('origin', out)


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_show(orig_path, path):

    gr = GitRepo.clone(orig_path, path)
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

    gr = GitRepo.clone(orig_path, path)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    eq_(gr.get_remote_url('origin'), orig_path)
    eq_(gr.get_remote_url('github'),
                 'git://github.com/datalad/testrepo--basic--r1')


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
@with_tempfile
def test_GitRepo_pull(test_path, orig_path, clone_path):

    origin = GitRepo.clone(test_path, orig_path)
    clone = GitRepo.clone(orig_path, clone_path)
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

    origin = GitRepo.clone(test_path, orig_path)
    clone = GitRepo.clone(orig_path, clone_path)
    filename = get_most_obscure_supported_name()

    origin.checkout("new_branch", ['-b'])
    with open(opj(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.add(filename)
    origin.commit("new file added.")

    fetched = clone.fetch(remote='origin')
    # test FetchInfo list returned by fetch
    eq_([u'origin/' + clone.get_active_branch(), u'origin/new_branch'],
        [commit.name for commit in fetched])

    ok_clean_git(clone.path)
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
    socket_path = opj(ssh_manager.socket_dir, get_connection_hash('localhost'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # we don't know any branches of the remote:
    eq_([], repo.get_remote_branches())

    fetched = repo.fetch(remote="ssh-remote")
    assert_in('ssh-remote/master', [commit.name for commit in fetched])
    ok_clean_git(repo)

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
    socket_path = opj(ssh_manager.socket_dir, get_connection_hash('localhost'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify remote:
    remote_repo.checkout("ssh-test", ['-b'])
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
    socket_path = opj(ssh_manager.socket_dir, get_connection_hash('localhost'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify local repo:
    repo.checkout("ssh-test", ['-b'])
    with open(opj(repo.path, "ssh_testfile.dat"), "w") as f:
        f.write("whatever")
    repo.add("ssh_testfile.dat")
    repo.commit("ssh_testfile.dat added.")

    # file is not known to the remote yet:
    assert_not_in("ssh_testfile.dat", remote_repo.get_indexed_files())

    # push changes:
    pushed = repo.push(remote="ssh-remote", refspec="ssh-test")
    # test PushInfo object for
    assert_in("ssh-remote/ssh-test", [commit.remote_ref.name for commit in pushed])

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
    clone = GitRepo.clone(orig_path, clone_path)
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
    git2.checkout('branch2', ['-b'])
    with open(opj(path2, 'branch2file'), 'w') as f:
        f.write("git2 in branch2")
    git2.add('branch2file')
    git2.commit("Add something to branch2.")

    # Setting up remote 'git3'
    with open(opj(path3, 'masterfile'), 'w') as f:
        f.write("git3 in master")
    git3.add('masterfile')
    git3.commit("Add something to master.")
    git3.checkout('branch3', ['-b'])
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

    gr = GitRepo.clone(url, path)

    # get the expected files via os for comparison:
    os_files = set()
    for (dirpath, dirnames, filenames) in os.walk(path):
        rel_dir = os.path.relpath(dirpath, start=path)
        if rel_dir.startswith(".git"):
            continue
        for file_ in filenames:
            file_path = os.path.normpath(opj(rel_dir, file_))
            os_files.add(file_path)

    # get the files via GitRepo:
    local_files = set(gr.get_files())
    remote_files = set(gr.get_files(branch="origin/master"))

    eq_(local_files, set(gr.get_indexed_files()))
    eq_(local_files, remote_files)
    eq_(local_files, os_files)

    # create a different branch:
    gr.checkout('new_branch', ['-b'])
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


@with_testrepos('.*git.*', flavors=local_testrepo_flavors)
@with_tempfile(mkdir=True)
@with_tempfile
def test_GitRepo_get_toppath(repo, tempdir, repo2):
    reporeal = realpath(repo)
    eq_(GitRepo.get_toppath(repo, follow_up=False), reporeal)
    eq_(GitRepo.get_toppath(repo), repo)
    # Generate some nested directory
    GitRepo(repo2, create=True)
    repo2real = realpath(repo2)
    nested = opj(repo2, "d1", "d2")
    os.makedirs(nested)
    eq_(GitRepo.get_toppath(nested, follow_up=False), repo2real)
    eq_(GitRepo.get_toppath(nested), repo2)
    # and if not under git, should return None
    eq_(GitRepo.get_toppath(tempdir), None)


@with_tempfile(mkdir=True)
def test_GitRepo_dirty(path):

    repo = GitRepo(path, create=True)
    ok_(not repo.dirty)

    # untracked file
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(repo.dirty)
    # staged file
    repo.add('file1.txt')
    ok_(repo.dirty)
    # clean again
    repo.commit("file1.txt added")
    ok_(not repo.dirty)
    # modify to be the same
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(not repo.dirty)
    # modified file
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('something else')
    ok_(repo.dirty)
    # clean again
    repo.add('file1.txt')
    repo.commit("file1.txt modified")
    ok_(not repo.dirty)

    # TODO: submodules



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
    repo.checkout(branch2, options=["--orphan"])
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
    repo.merge(branch1, allow_unrelated=True)
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

    commits_default = list(repo.get_branch_commits())
    commits = list(repo.get_branch_commits('master'))
    eq_(commits, commits_default)

    eq_(len(commits), 1)
    commits_stop0 = list(repo.get_branch_commits(stop=commits[0].hexsha))
    eq_(commits_stop0, [])
    commits_hexsha = list(repo.get_branch_commits(value='hexsha'))
    commits_hexsha_left = list(repo.get_branch_commits(value='hexsha', limit='left-only'))
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


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_git_custom_calls(path, path2):
    # we need a GitRepo instance
    repo = GitRepo(path, create=True)
    with open(opj(path, "cc_test.dat"), 'w') as f:
        f.write("test_git_custom_calls")

    out, err = repo._gitpy_custom_call('add', 'cc_test.dat')

    # actually executed:
    assert_in("cc_test.dat", repo.get_indexed_files())
    ok_(repo.dirty)

    # call using cmd_options:
    out, err = repo._gitpy_custom_call('commit',
                                       cmd_options={'m': 'added file'})
    ok_clean_git(path, annex=False)
    # check output:
    assert_in("1 file changed", out)
    assert_in("cc_test.dat", out)
    eq_('', err)

    # impossible 'add' call should raise ...
    assert_raises(GitCommandError, repo._gitpy_custom_call,
                  'add', 'not_existing', expect_fail=False)
    # .. except we expect it to fail:
    repo._gitpy_custom_call('add', 'not_existing', expect_fail=True)

    # log outputs:
    with swallow_logs(new_level=logging.DEBUG) as cm:
        out, err = repo._gitpy_custom_call('status',
                                           log_stdout=True,
                                           log_stderr=True)

        assert_in("On branch master", out)
        assert_in("nothing to commit", out)
        eq_("", err)
        for line in out.splitlines():
            assert_in("stdout| " + line, cm.out)

    # don't log outputs:
    with swallow_logs(new_level=logging.DEBUG) as cm:
        out, err = repo._gitpy_custom_call('status',
                                           log_stdout=False,
                                           log_stderr=False)

        assert_in("On branch master", out)
        assert_in("nothing to commit", out)
        eq_("", err)
        eq_("", cm.out)

    # use git_options:
    # Note: 'path2' doesn't contain a git repository
    with assert_raises(GitCommandError) as cm:
        repo._gitpy_custom_call('status', git_options={'C': path2})
    assert_in("-C %s status" % path2, str(cm.exception))
    assert_in("fatal: Not a git repository", str(cm.exception))

    # TODO: How to test 'env'?


@with_testrepos(flavors=['local'])
@with_tempfile(mkdir=True)
def test_get_tracking_branch(o_path, c_path):

    clone = GitRepo.clone(o_path, c_path)
    # Note, that the default branch might differ even if it is always 'master'.
    # For direct mode annex repositories it would then be "annex/direct/master"
    # for example. Therefore use whatever branch is checked out by default:
    master_branch = clone.get_active_branch()
    ok_(master_branch)

    eq_(('origin', 'refs/heads/' + master_branch),
        clone.get_tracking_branch())

    clone.checkout('new_branch', ['-b'])

    eq_((None, None), clone.get_tracking_branch())

    eq_(('origin', 'refs/heads/' + master_branch),
        clone.get_tracking_branch(master_branch))


@with_testrepos('submodule_annex', flavors=['clone'])
def test_submodule_deinit(path):

    top_repo = GitRepo(path, create=False)
    eq_(['subm 1', 'subm 2'], [s.name for s in top_repo.get_submodules()])
    # note: here init=True is ok, since we are using it just for testing
    with swallow_logs(new_level=logging.WARN) as cml:
        top_repo.update_submodule('subm 1', init=True)
        assert_in('Do not use update_submodule with init=True', cml.out)
    top_repo.update_submodule('subm 2', init=True)
    ok_(all([s.module_exists() for s in top_repo.get_submodules()]))

    # modify submodule:
    with open(opj(top_repo.path, 'subm 1', 'file_ut.dat'), "w") as f:
        f.write("some content")

    assert_raises(GitCommandError, top_repo.deinit_submodule, 'sub1')

    # using force should work:
    top_repo.deinit_submodule('subm 1', force=True)

    ok_(not top_repo.repo.submodule('subm 1').module_exists())


@with_testrepos(".*basic_git.*", flavors=['local'])
@with_tempfile(mkdir=True)
def test_GitRepo_add_submodule(source, path):

    top_repo = GitRepo(path, create=True)

    top_repo.add_submodule('sub', name='sub', url=source)
    top_repo.commit('submodule added')
    eq_([s.name for s in top_repo.get_submodules()], ['sub'])
    ok_clean_git(path)
    ok_clean_git(opj(path, 'sub'))


def test_GitRepo_update_submodule():
    raise SkipTest("TODO")


def test_GitRepo_get_submodules():
    raise SkipTest("TODO")


def test_kwargs_to_options():

    class Some(object):

        @kwargs_to_options(split_single_char_options=True)
        def f_decorated_split(self, options=None):
            return options

        @kwargs_to_options(split_single_char_options=False,
                           target_kw='another')
        def f_decorated_no_split(self, another=None):
            return another

    res = Some().f_decorated_split(C="/some/path", m=3, b=True, more_fancy=['one', 'two'])
    ok_(isinstance(res, list))
    eq_(res, ['-C', "/some/path", '-b', '-m', '3',
              '--more-fancy=one', '--more-fancy=two'])

    res = Some().f_decorated_no_split(f='some')
    eq_(res, ['-fsome'])


def test_to_options():

    class Some(object):

        def cmd_func(self, git_options=None, annex_options=None, options=None):

            git_options = git_options[:] if git_options else []
            annex_options = annex_options[:] if annex_options else []
            options = options[:] if options else []

            faked_cmd_call = ['git'] + git_options + ['annex'] + \
                             annex_options + ['my_cmd'] + options

            return faked_cmd_call

    eq_(Some().cmd_func(options=to_options(m="bla", force=True)),
        ['git', 'annex', 'my_cmd', '--force', '-m', 'bla'])

    eq_(Some().cmd_func(git_options=to_options(C="/some/where"),
                        annex_options=to_options(JSON=True),
                        options=to_options(unused=True)),
        ['git', '-C', '/some/where', 'annex', '--JSON', 'my_cmd', '--unused'])

    eq_(Some().cmd_func(git_options=to_options(C="/some/where", split_single_char_options=False),
                        annex_options=to_options(JSON=True),
                        options=to_options(unused=True)),
        ['git', '-C/some/where', 'annex', '--JSON', 'my_cmd', '--unused'])


@with_tempfile
def test_GitRepo_count_objects(repo_path):

    repo = GitRepo(repo_path, create=True)
    # test if dictionary returned
    eq_(isinstance(repo.count_objects, dict), True)
    # test if dictionary contains keys and values we expect
    empty_count = {'count': 0, 'garbage': 0,  'in-pack': 0, 'packs': 0, 'prune-packable': 0,
                   'size': 0, 'size-garbage': 0, 'size-pack': 0}
    eq_(empty_count, repo.count_objects)


@with_tempfile
def test_get_missing(path):
    repo = GitRepo(path, create=True)
    os.makedirs(opj(path, 'deep'))
    with open(opj(path, 'test1'), 'w') as f:
        f.write('some')
    with open(opj(path, 'deep', 'test2'), 'w') as f:
        f.write('some more')
    repo.add('.', commit=True)
    ok_clean_git(path, annex=False)
    os.unlink(opj(path, 'test1'))
    eq_(repo.get_missing_files(), ['test1'])
    rmtree(opj(path, 'deep'))
    eq_(sorted(repo.get_missing_files()), [opj('deep', 'test2'), 'test1'])
    # nothing is actually known to be deleted
    eq_(repo.get_deleted_files(), [])
    # do proper removal
    repo.remove(opj(path, 'test1'))
    # no longer missing
    eq_(repo.get_missing_files(), [opj('deep', 'test2')])
    # but deleted
    eq_(repo.get_deleted_files(), ['test1'])


@with_tempfile
def test_optimized_cloning(path):
    # make test repo with one file and one commit
    originpath = opj(path, 'origin')
    repo = GitRepo(originpath, create=True)
    with open(opj(originpath, 'test'), 'w') as f:
        f.write('some')
    repo.add('test')
    repo.commit('init')
    ok_clean_git(originpath, annex=False)
    from glob import glob

    def _get_inodes(repo):
        return dict(
            [(os.path.join(*o.split(os.sep)[-2:]),
              os.stat(o).st_ino)
             for o in glob(os.path.join(repo.repo.git_dir,
                                        'objects', '*', '*'))])

    origin_inodes = _get_inodes(repo)
    # now clone it in different ways and see what happens to the object storage
    from datalad.support.network import get_local_file_url
    clonepath = opj(path, 'clone')
    for src in (originpath, get_local_file_url(originpath)):
        # deprecated
        assert_raises(DeprecatedError, GitRepo, url=src, path=clonepath)
        clone = GitRepo.clone(url=src, path=clonepath, create=True)
        clone_inodes = _get_inodes(clone)
        eq_(origin_inodes, clone_inodes, msg='with src={}'.format(src))
        rmtree(clonepath)
#        del clone
#        gc.collect()
        # Note: del needed, since otherwise WeakSingletonRepo would just
        # return the original object in second run


@with_tempfile
@with_tempfile
def test_GitRepo_gitpy_injection(path, path2):

    gr = GitRepo(path, create=True)
    gr._GIT_COMMON_OPTIONS.extend(['test-option'])

    with assert_raises(GitCommandError) as cme:
        gr.repo.git.unknown_git_command()
    assert_in('test-option', exc_str(cme.exception))

    # once set, these option should be persistent across git calls:
    with assert_raises(GitCommandError) as cme:
        gr.repo.git.another_unknown_git_command()
    assert_in('test-option', exc_str(cme.exception))

    # but other repos should not be affected:
    gr2 = GitRepo(path2, create=True)
    with assert_raises(GitCommandError) as cme:
        gr2.repo.git.unknown_git_command()
    assert_not_in('test-option', exc_str(cme.exception))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_GitRepo_flyweight(path1, path2):

    repo1 = GitRepo(path1, create=True)
    assert_is_instance(repo1, GitRepo)
    # instantiate again:
    repo2 = GitRepo(path1, create=False)
    assert_is_instance(repo2, GitRepo)
    # the very same object:
    ok_(repo1 is repo2)

    # reference the same in a different way:
    with chpwd(path1):
        repo3 = GitRepo(relpath(path1, start=path2), create=False)
    # it's the same object:
    ok_(repo1 is repo3)

    # and realpath attribute is the same, so they are still equal:
    ok_(repo1 == repo3)


@with_tempfile(mkdir=True)
@with_tempfile()
def test_GitRepo_flyweight_monitoring_inode(path, store):
    # testing for issue #1512
    check_repo_deals_with_inode_change(GitRepo, path, store)


@with_tree(tree={'ignore-sub.me': {'a_file.txt': 'some content'},
                 'ignore.me': 'ignored content',
                 'dontigno.re': 'other content'})
def test_GitRepo_gitignore(path):

    gr = GitRepo(path, create=True)
    sub = GitRepo(opj(path, 'ignore-sub.me'))

    from ..exceptions import GitIgnoreError

    with open(opj(path, '.gitignore'), "w") as f:
        f.write("*.me")

    with assert_raises(GitIgnoreError) as cme:
        gr.add('ignore.me')
    eq_(cme.exception.paths, ['ignore.me'])

    with assert_raises(GitIgnoreError) as cme:
        gr.add_submodule(path='ignore-sub.me')
    eq_(cme.exception.paths, ['ignore-sub.me'])

    with assert_raises(GitIgnoreError) as cme:
        gr.add(['ignore.me', 'dontigno.re', opj('ignore-sub.me', 'a_file.txt')])
    eq_(set(cme.exception.paths), {'ignore.me', 'ignore-sub.me'})


@with_tempfile(mkdir=True)
def test_GitRepo_set_remote_url(path):

    gr = GitRepo(path, create=True)
    gr.add_remote('some', 'http://example.com/.git')
    assert_equal(gr.config['remote.some.url'],
                 'http://example.com/.git')
    # change url:
    gr.set_remote_url('some', 'http://believe.it')
    assert_equal(gr.config['remote.some.url'],
                 'http://believe.it')

    # set push url:
    gr.set_remote_url('some', 'ssh://whatever.ru', push=True)
    assert_equal(gr.config['remote.some.pushurl'],
                 'ssh://whatever.ru')

    # add remote without url
    url2 = 'http://repo2.example.com/.git'
    gr.add_remote('some-without-url', url2)
    assert_equal(gr.config['remote.some-without-url.url'], url2)
    # "remove" it
    gr.config.unset('remote.some-without-url.url', where='local')
    with assert_raises(KeyError):
        gr.config['remote.some-without-url.url']
    eq_(set(gr.get_remotes()), {'some', 'some-without-url'})
    eq_(set(gr.get_remotes(with_urls_only=True)), {'some'})
