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

import logging

import os
from os import linesep
import os.path as op

import sys


from datalad import get_encoding_info
from datalad.cmd import Runner

from datalad.utils import unlink
from datalad.tests.utils import ok_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import eq_
from datalad.tests.utils import neq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import skip_if_no_network
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_re_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import local_testrepo_flavors
from datalad.tests.utils import get_most_obscure_supported_name
from datalad.tests.utils import SkipTest
from datalad.utils import rmtree
from datalad.tests.utils_testrepos import BasicAnnexTestRepo
from datalad.utils import getpwd, chpwd

from datalad.dochelpers import exc_str

from datalad.support.sshconnector import get_connection_hash

from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.gitrepo import NoSuchPathError
from datalad.support.gitrepo import InvalidGitRepositoryError
from datalad.support.gitrepo import to_options
from datalad.support.gitrepo import kwargs_to_options
from datalad.support.gitrepo import _normalize_path
from datalad.support.gitrepo import normalize_paths
from datalad.support.gitrepo import split_remote_branch
from datalad.support.gitrepo import gitpy
from datalad.support.gitrepo import guard_BadName
from datalad.support.exceptions import DeprecatedError
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import PathKnownToRepositoryError
from datalad.support.external_versions import external_versions
from datalad.support.protocol import ExecutionTimeProtocol
from .utils import check_repo_deals_with_inode_change


@with_tempfile(mkdir=True)
def test_GitRepo_invalid_path(path):
    with chpwd(path):
        assert_raises(ValueError, GitRepo, path="git://some/url", create=True)
        ok_(not op.exists(op.join(path, "git:")))
        assert_raises(ValueError, GitRepo, path="file://some/relative/path", create=True)
        ok_(not op.exists(op.join(path, "file:")))


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_instance_from_clone(src, dst):

    gr = GitRepo.clone(src, dst)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    assert_is_instance(gr.repo, gitpy.Repo,
                       "Failed to instantiate GitPython Repo object.")
    ok_(op.exists(op.join(dst, '.git')))

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
    ok_(op.exists(op.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_GitRepo_instance_from_not_existing(path, path2):
    # 1. create=False and path doesn't exist:
    assert_raises(NoSuchPathError, GitRepo, path, create=False)
    assert_false(op.exists(path))

    # 2. create=False, path exists, but no git repo:
    os.mkdir(path)
    ok_(op.exists(path))
    assert_raises(InvalidGitRepositoryError, GitRepo, path, create=False)
    assert_false(op.exists(op.join(path, '.git')))

    # 3. create=True, path doesn't exist:
    gr = GitRepo(path2, create=True)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path2, '.git')))
    ok_clean_git(path2, annex=False)

    # 4. create=True, path exists, but no git repo:
    gr = GitRepo(path, create=True)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path, '.git')))
    ok_clean_git(path, annex=False)


@with_tempfile
def test_GitRepo_init_options(path):
    # passing an option, not explicitly defined in GitRepo class:
    gr = GitRepo(path, create=True, bare=True)

    cfg = gr.repo.config_reader()
    ok_(cfg.get_value(section="core", option="bare"))


@with_tree(
    tree={
        'subds': {
            'file_name': ''
        }
    }
)
def test_init_fail_under_known_subdir(path):
    repo = GitRepo(path, create=True)
    repo.add(op.join('subds', 'file_name'))
    # Should fail even if we do not commit but only add to index:
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds'), create=True)
    assert_in("file_name", str(cme.exception))  # we provide a list of offenders
    # and after we commit - the same story
    repo.commit("added file")
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds'), create=True)


@with_tempfile
@with_tempfile
def test_GitRepo_equals(path1, path2):

    repo1 = GitRepo(path1)
    repo2 = GitRepo(path1)
    ok_(repo1 == repo2)
    eq_(repo1, repo2)
    repo2 = GitRepo(path2)
    neq_(repo1, repo2)
    ok_(repo1 != repo2)


@assert_cwd_unchanged
@with_testrepos('.*git.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_add(src, path):

    gr = GitRepo.clone(src, path)
    filename = get_most_obscure_supported_name()
    with open(op.join(path, filename), 'w') as f:
        f.write("File to add to git")
    added = gr.add(filename)

    eq_(added, {'success': True, 'file': filename})
    assert_in(filename, gr.get_indexed_files(),
              "%s not successfully added to %s" % (filename, path))
    # uncommitted:
    ok_(gr.dirty)

    filename = "another.txt"
    with open(op.join(path, filename), 'w') as f:
        f.write("Another file to add to git")

    # include committing:
    added2 = gr.add(filename)
    gr.commit(msg="Add two files.")
    eq_(added2, {'success': True, 'file': filename})

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
    with open(op.join(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.add(filename)
    gr.commit("Testing GitRepo.commit().")
    ok_clean_git(gr)
    eq_("Testing GitRepo.commit().{}".format(linesep),
        gr.repo.head.commit.message)

    with open(op.join(path, filename), 'w') as f:
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
    with open(op.join(path, "untracked"), "w") as f:
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

    # result = _normalize_path(gr.path, op.join('.', 'testfile'))
    # eq_(result, "testfile", "_normalize_path() returned %s" % result)
    #
    # result = _normalize_path(gr.path, op.join('testdir', '..', 'testfile'))
    # eq_(result, "testfile", "_normalize_path() returned %s" % result)
    # Note: By now, normpath within normalize_paths() is disabled, therefore
    # disable these tests.

    result = _normalize_path(gr.path, op.join('testdir', 'testfile'))
    eq_(result, op.join("testdir", "testfile"), "_normalize_path() returned %s" % result)

    result = _normalize_path(gr.path, op.join(git_path, "testfile"))
    eq_(result, "testfile", "_normalize_path() returned %s" % result)

    # now we are inside, so
    # OLD PHILOSOPHY: relative paths are relative to cwd and have
    # to be converted to be relative to annex_path
    # NEW PHILOSOPHY: still relative to repo! unless starts with . (curdir) or .. (pardir)
    with chpwd(op.join(git_path, 'd1', 'd2')):

        result = _normalize_path(gr.path, "testfile")
        eq_(result, 'testfile', "_normalize_path() returned %s" % result)

        # if not joined as directory name but just a prefix to the filename, should
        # behave correctly
        for d in (op.curdir, op.pardir):
            result = _normalize_path(gr.path, d + "testfile")
            eq_(result, d + 'testfile', "_normalize_path() returned %s" % result)

        result = _normalize_path(gr.path, op.join(op.curdir, "testfile"))
        eq_(result, op.join('d1', 'd2', 'testfile'), "_normalize_path() returned %s" % result)

        result = _normalize_path(gr.path, op.join(op.pardir, 'testfile'))
        eq_(result, op.join('d1', 'testfile'), "_normalize_path() returned %s" % result)

        assert_raises(FileNotInRepositoryError, _normalize_path, gr.path, op.join(git_path, '..', 'outside'))

        result = _normalize_path(gr.path, op.join(git_path, 'd1', 'testfile'))
        eq_(result, op.join('d1', 'testfile'), "_normalize_path() returned %s" % result)


def test_GitRepo_files_decorator():

    class testclass(object):
        def __init__(self):
            self.path = op.join('some', 'where')

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
    file_to_test = op.join(test_instance.path, 'deep', obscure_filename)
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


    file_to_test = op.join(obscure_filename, 'beyond', 'obscure')
    eq_(test_instance.decorated_many(file_to_test),
                 _normalize_path(test_instance.path, file_to_test))

    file_to_test = op.join(getpwd(), 'somewhere', 'else', obscure_filename)
    assert_raises(FileNotInRepositoryError, test_instance.decorated_many,
                  file_to_test)

    # If a list passed -- list returned
    files_to_test = ['now', op.join('a list', 'of'), 'paths']
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
    out = gr.get_remotes()
    assert_in('origin', out)
    eq_(len(out), 1)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    out = gr.get_remotes()
    assert_in('origin', out)
    assert_in('github', out)
    eq_(len(out), 2)
    eq_('git://github.com/datalad/testrepo--basic--r1', gr.config['remote.github.url'])


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_GitRepo_remote_remove(orig_path, path):

    gr = GitRepo.clone(orig_path, path)
    gr.add_remote('github', 'git://github.com/datalad/testrepo--basic--r1')
    gr.remove_remote('github')
    out = gr.get_remotes()
    eq_(len(out), 1)
    assert_in('origin', out)


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

    with open(op.join(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.add(filename)
    origin.commit("new file added.")
    clone.pull()
    ok_(op.exists(op.join(clone_path, filename)))

    # While at it, let's test _get_remotes_having_commit a bit
    clone.add_remote("very_origin", test_path)
    clone.fetch("very_origin")
    eq_(
        clone._get_remotes_having_commit(clone.get_hexsha()),
        ['origin']
    )
    prev_commit = clone.get_hexsha('HEAD^')
    eq_(
        set(clone._get_remotes_having_commit(prev_commit)),
        {'origin', 'very_origin'}
    )


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
@with_tempfile
def test_GitRepo_fetch(test_path, orig_path, clone_path):

    origin = GitRepo.clone(test_path, orig_path)
    clone = GitRepo.clone(orig_path, clone_path)
    filename = get_most_obscure_supported_name()

    origin.checkout("new_branch", ['-b'])
    with open(op.join(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.add(filename)
    origin.commit("new file added.")

    fetched = clone.fetch(remote='origin')
    # test FetchInfo list returned by fetch
    eq_([u'origin/' + clone.get_active_branch(), u'origin/new_branch'],
        [commit.name for commit in fetched])

    ok_clean_git(clone.path, annex=False)
    assert_in("origin/new_branch", clone.get_remote_branches())
    assert_in(filename, clone.get_files("origin/new_branch"))
    assert_false(op.exists(op.join(clone_path, filename)))  # not checked out

    # create a remote without an URL:
    origin.add_remote('not-available', 'git://example.com/not/existing')
    origin.config.unset('remote.not-available.url', where='local')

    # fetch without provided URL
    fetched = origin.fetch('not-available')
    # nothing was done, nothing returned:
    eq_([], fetched)


@skip_ssh
@with_testrepos('.*basic.*', flavors=['local'])
@with_tempfile
def test_GitRepo_ssh_fetch(remote_path, repo_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=False)
    url = "ssh://localhost" + op.abspath(remote_path)
    socket_path = op.join(ssh_manager.socket_dir, get_connection_hash('localhost'))
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
    ok_(op.exists(socket_path))

    # we actually fetched it:
    assert_in('ssh-remote/master', repo.get_remote_branches())


@skip_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_pull(remote_path, repo_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=True)
    url = "ssh://localhost" + op.abspath(remote_path)
    socket_path = op.join(ssh_manager.socket_dir, get_connection_hash('localhost'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify remote:
    remote_repo.checkout("ssh-test", ['-b'])
    with open(op.join(remote_repo.path, "ssh_testfile.dat"), "w") as f:
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
    ok_(op.exists(socket_path))

    # we actually pulled the changes
    assert_in("ssh_testfile.dat", repo.get_indexed_files())


@skip_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_push(repo_path, remote_path):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=True)
    url = "ssh://localhost" + op.abspath(remote_path)
    socket_path = op.join(ssh_manager.socket_dir, get_connection_hash('localhost'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # modify local repo:
    repo.checkout("ssh-test", ['-b'])
    with open(op.join(repo.path, "ssh_testfile.dat"), "w") as f:
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
    ok_(op.exists(socket_path))

    # remote now knows the changes:
    assert_in("ssh-test", remote_repo.get_branches())
    assert_in("ssh_testfile.dat", remote_repo.get_files("ssh-test"))

    # amend to make it require "--force":
    repo.commit("amended", options=['--amend'])
    # push without --force should yield an error:
    pushed = repo.push(remote="ssh-remote", refspec="ssh-test")
    assert_in("[rejected] (non-fast-forward)", pushed[0].summary)
    # now push using force:
    repo.push(remote="ssh-remote", refspec="ssh-test", force=True)
    # correct commit message in remote:
    assert_in("amended",
              list(remote_repo.get_branch_commits('ssh-test'))[-1].summary)


@with_tempfile
@with_tempfile
def test_GitRepo_push_n_checkout(orig_path, clone_path):

    origin = GitRepo(orig_path)
    clone = GitRepo.clone(orig_path, clone_path)
    filename = get_most_obscure_supported_name()

    with open(op.join(clone_path, filename), 'w') as f:
        f.write("New file.")
    clone.add(filename)
    clone.commit("new file added.")
    # TODO: need checkout first:
    clone.push('origin', '+master:new-branch')
    origin.checkout('new-branch')
    ok_(op.exists(op.join(orig_path, filename)))


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
    with open(op.join(path2, 'masterfile'), 'w') as f:
        f.write("git2 in master")
    git2.add('masterfile')
    git2.commit("Add something to master.")
    git2.checkout('branch2', ['-b'])
    with open(op.join(path2, 'branch2file'), 'w') as f:
        f.write("git2 in branch2")
    git2.add('branch2file')
    git2.commit("Add something to branch2.")

    # Setting up remote 'git3'
    with open(op.join(path3, 'masterfile'), 'w') as f:
        f.write("git3 in master")
    git3.add('masterfile')
    git3.commit("Add something to master.")
    git3.checkout('branch3', ['-b'])
    with open(op.join(path3, 'branch3file'), 'w') as f:
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
            file_path = os.path.normpath(op.join(rel_dir, file_))
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
    with open(op.join(path, filename), 'w') as f:
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


@with_tree(tree={
    'd1': {'f1': 'content1',
           'f2': 'content2'},
    'file': 'content3',
    'd2': {'f1': 'content1',
           'f2': 'content2'},
    'file2': 'content3'

    })
def test_GitRepo__get_files_history(path):

    gr = GitRepo(path, create=True)
    gr.add('d1')
    gr.commit("commit d1")
    #import pdb; pdb.set_trace()

    gr.add(['d2', 'file'])
    gr.commit("commit d2")

    # commit containing files of d1
    d1_commit = next(gr._get_files_history([op.join(path, 'd1', 'f1'), op.join(path, 'd1', 'f1')]))
    eq_(str(d1_commit.message), 'commit d1\n')

    # commit containing files of d2
    d2_commit_gen = gr._get_files_history([op.join(path, 'd2', 'f1'), op.join(path, 'd2', 'f1')])
    eq_(str(next(d2_commit_gen).message), 'commit d2\n')
    assert_raises(StopIteration, next, d2_commit_gen)  # no more commits with files of d2

    # union of commits containing passed objects
    commits_union = gr._get_files_history([op.join(path, 'd1', 'f1'), op.join(path, 'd2', 'f1'), op.join(path, 'file')])
    eq_(str(next(commits_union).message), 'commit d2\n')
    eq_(str(next(commits_union).message), 'commit d1\n')
    assert_raises(StopIteration, next, commits_union)

    # file2 not commited, so shouldn't exist in commit history
    no_such_commits = gr._get_files_history([op.join(path, 'file2')])
    assert_raises(StopIteration, next, no_such_commits)


@with_testrepos('.*git.*', flavors=local_testrepo_flavors)
@with_tempfile(mkdir=True)
@with_tempfile
def test_GitRepo_get_toppath(repo, tempdir, repo2):
    reporeal = op.realpath(repo)
    eq_(GitRepo.get_toppath(repo, follow_up=False), reporeal)
    eq_(GitRepo.get_toppath(repo), repo)
    # Generate some nested directory
    GitRepo(repo2, create=True)
    repo2real = op.realpath(repo2)
    nested = op.join(repo2, "d1", "d2")
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
    with open(op.join(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(repo.dirty)
    # staged file
    repo.add('file1.txt')
    ok_(repo.dirty)
    # clean again
    repo.commit("file1.txt added")
    ok_(not repo.dirty)
    # modify to be the same
    with open(op.join(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(not repo.dirty)
    # modified file
    with open(op.join(path, 'file1.txt'), 'w') as f:
        f.write('something else')
    ok_(repo.dirty)
    # clean again
    repo.add('file1.txt')
    repo.commit("file1.txt modified")
    ok_(not repo.dirty)

    # An empty directory doesn't count as dirty.
    os.mkdir(op.join(path, "empty"))
    ok_(not repo.dirty)
    # Neither does an empty directory with an otherwise empty directory.
    os.mkdir(op.join(path, "empty", "empty-again"))
    ok_(not repo.dirty)

    # TODO: submodules


@with_tempfile(mkdir=True)
def test_GitRepo_get_merge_base(src):
    repo = GitRepo(src, create=True)
    with open(op.join(src, 'file.txt'), 'w') as f:
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
    with open(op.join(src, 'file.txt'), 'w') as f:
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
    repo.precommit()  # to stop all the batched processes for swallow_outputs
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
    from datalad.support.annexrepo import AnnexRepo

    top_repo = AnnexRepo(path, create=False)
    eq_({'subm 1', '2'}, {s.name for s in top_repo.get_submodules()})
    # note: here init=True is ok, since we are using it just for testing
    with swallow_logs(new_level=logging.WARN) as cml:
        top_repo.update_submodule('subm 1', init=True)
        assert_in('Do not use update_submodule with init=True', cml.out)
    top_repo.update_submodule('2', init=True)

    # ok_(all([s.module_exists() for s in top_repo.get_submodules()]))
    # TODO: old assertion above if non-bare? (can't use "direct mode" in test_gitrepo)
    # Alternatively: New testrepo (plain git submodules) and have a dedicated
    # test for annexes in addition
    ok_(all([GitRepo.is_valid_repo(op.join(top_repo.path, s.path))
             for s in top_repo.get_submodules()]))

    # modify submodule:
    with open(op.join(top_repo.path, 'subm 1', 'file_ut.dat'), "w") as f:
        f.write("some content")

    assert_raises(CommandError, top_repo.deinit_submodule, 'sub1')

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
    ok_clean_git(op.join(path, 'sub'))


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
    os.makedirs(op.join(path, 'deep'))
    with open(op.join(path, 'test1'), 'w') as f:
        f.write('some')
    with open(op.join(path, 'deep', 'test2'), 'w') as f:
        f.write('some more')
    # no files tracked yet, so nothing changed
    eq_(repo.get_changed_files(), [])
    repo.add('.')
    # still no differences between worktree and staged
    eq_(repo.get_changed_files(), [])
    eq_(set(repo.get_changed_files(staged=True)),
        {'test1', op.join('deep', 'test2')})
    eq_(set(repo.get_changed_files(staged=True, diff_filter='AD')),
        {'test1', op.join('deep', 'test2')})
    eq_(repo.get_changed_files(staged=True, diff_filter='D'), [])
    repo.commit()
    eq_(repo.get_changed_files(), [])
    eq_(repo.get_changed_files(staged=True), [])
    ok_clean_git(path, annex=False)
    unlink(op.join(path, 'test1'))
    eq_(repo.get_missing_files(), ['test1'])
    rmtree(op.join(path, 'deep'))
    eq_(sorted(repo.get_missing_files()), [op.join('deep', 'test2'), 'test1'])
    # nothing is actually known to be deleted
    eq_(repo.get_deleted_files(), [])
    # do proper removal
    repo.remove(op.join(path, 'test1'))
    # no longer missing
    eq_(repo.get_missing_files(), [op.join('deep', 'test2')])
    # but deleted
    eq_(repo.get_deleted_files(), ['test1'])


@with_tempfile
def test_optimized_cloning(path):
    # make test repo with one file and one commit
    originpath = op.join(path, 'origin')
    repo = GitRepo(originpath, create=True)
    with open(op.join(originpath, 'test'), 'w') as f:
        f.write('some')
    repo.add('test')
    repo.commit('init')
    ok_clean_git(originpath, annex=False)
    from glob import glob

    def _get_inodes(repo):
        return dict(
            [(os.path.join(*o.split(os.sep)[-2:]),
              os.stat(o).st_ino)
             for o in glob(os.path.join(repo.path,
                                        repo.get_git_dir(repo),
                                        'objects', '*', '*'))])

    origin_inodes = _get_inodes(repo)
    # now clone it in different ways and see what happens to the object storage
    from datalad.support.network import get_local_file_url
    clonepath = op.join(path, 'clone')
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
        repo3 = GitRepo(op.relpath(path1, start=path2), create=False)
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
    sub = GitRepo(op.join(path, 'ignore-sub.me'))
    # we need to commit something, otherwise add_submodule
    # will already refuse the submodule for having no commit
    sub.add('a_file.txt')
    sub.commit()

    from ..exceptions import GitIgnoreError

    with open(op.join(path, '.gitignore'), "w") as f:
        f.write("*.me")

    with assert_raises(GitIgnoreError) as cme:
        gr.add('ignore.me')
    eq_(cme.exception.paths, ['ignore.me'])

    with assert_raises(GitIgnoreError) as cme:
        gr.add_submodule(path='ignore-sub.me')
    eq_(cme.exception.paths, ['ignore-sub.me'])

    with assert_raises(GitIgnoreError) as cme:
        gr.add(['ignore.me', 'dontigno.re', op.join('ignore-sub.me', 'a_file.txt')])
    eq_(set(cme.exception.paths), {'ignore.me', 'ignore-sub.me'})

    eq_(gr.get_gitattributes('.')['.'], {})  # nothing is recorded within .gitattributes


@with_tempfile(mkdir=True)
def test_GitRepo_set_remote_url(path):

    gr = GitRepo(path, create=True)
    gr.add_remote('some', 'http://example.com/.git')
    eq_(gr.config['remote.some.url'],
                 'http://example.com/.git')
    # change url:
    gr.set_remote_url('some', 'http://believe.it')
    eq_(gr.config['remote.some.url'],
                 'http://believe.it')

    # set push url:
    gr.set_remote_url('some', 'ssh://whatever.ru', push=True)
    eq_(gr.config['remote.some.pushurl'],
                 'ssh://whatever.ru')

    # add remote without url
    url2 = 'http://repo2.example.com/.git'
    gr.add_remote('some-without-url', url2)
    eq_(gr.config['remote.some-without-url.url'], url2)
    # "remove" it
    gr.config.unset('remote.some-without-url.url', where='local')
    with assert_raises(KeyError):
        gr.config['remote.some-without-url.url']
    eq_(set(gr.get_remotes()), {'some', 'some-without-url'})
    eq_(set(gr.get_remotes(with_urls_only=True)), {'some'})


@with_tempfile(mkdir=True)
def test_gitattributes(path):
    gr = GitRepo(path, create=True)
    # starts without any attributes file
    ok_(not op.exists(op.join(gr.path, '.gitattributes')))
    eq_(gr.get_gitattributes('.')['.'], {})
    # bool is a tag or unsets, anything else is key/value
    gr.set_gitattributes([('*', {'tag': True}), ('*', {'sec.key': 'val'})])
    ok_(op.exists(op.join(gr.path, '.gitattributes')))
    eq_(gr.get_gitattributes('.')['.'], {'tag': True, 'sec.key': 'val'})
    # unset by amending the record, but does not remove notion of the
    # tag entirely
    gr.set_gitattributes([('*', {'tag': False})])
    eq_(gr.get_gitattributes('.')['.'], {'tag': False, 'sec.key': 'val'})
    # attributes file is not added or commited, we can ignore such
    # attributes
    eq_(gr.get_gitattributes('.', index_only=True)['.'], {})

    # we can send absolute path patterns and write to any file, and
    # the patterns will be translated relative to the target file
    gr.set_gitattributes([
        (op.join(gr.path, 'relative', 'ikethemike/**'), {'bang': True})],
        attrfile=op.join('relative', '.gitattributes'))
    # directory and file get created
    ok_(op.exists(op.join(gr.path, 'relative', '.gitattributes')))
    eq_(gr.get_gitattributes(
        op.join(gr.path, 'relative', 'ikethemike', 'probe')),
        # always comes out relative to the repo root, even if abs goes in
        {op.join('relative', 'ikethemike', 'probe'):
            {'tag': False, 'sec.key': 'val', 'bang': True}})
    if get_encoding_info()['default'] != 'ascii':
        # do not perform this on obscure systems without anything like UTF
        # it is not relevant whether a path actually exists, and paths
        # with spaces and other funky stuff are just fine
        funky = u'{} {}'.format(
            get_most_obscure_supported_name(),
            get_most_obscure_supported_name())
        gr.set_gitattributes([(funky, {'this': 'that'})])
        eq_(gr.get_gitattributes(funky)[funky], {
            'this': 'that',
            'tag': False,
            'sec.key': 'val',
        })

    # mode='w' should replace the entire file:
    gr.set_gitattributes([('**', {'some': 'nonsense'})], mode='w')
    eq_(gr.get_gitattributes('.')['.'], {'some': 'nonsense'})


@with_tempfile(mkdir=True)
def test_get_hexsha_tag(path):
    gr = GitRepo(path, create=True)
    gr.commit(msg="msg", options=["--allow-empty"])
    gr.tag("atag", message="atag msg")
    # get_hexsha() dereferences a tag to a commit.
    eq_(gr.get_hexsha("atag"), gr.get_hexsha())


@with_tempfile(mkdir=True)
def test_get_tags(path):
    from mock import patch

    gr = GitRepo(path, create=True)
    eq_(gr.get_tags(), [])
    eq_(gr.describe(), None)

    # Explicitly override the committer date because tests may set it to a
    # fixed value, but we want to check that the returned tags are sorted by
    # the committer date.
    with patch.dict("os.environ", {"GIT_COMMITTER_DATE":
                                   "Thu, 07 Apr 2005 22:13:13 +0200"}):
        create_tree(gr.path, {'file': ""})
        gr.add('file')
        gr.commit(msg="msg")
        eq_(gr.get_tags(), [])
        eq_(gr.describe(), None)

        gr.tag("nonannotated")
        tags1 = [{'name': 'nonannotated', 'hexsha': gr.get_hexsha()}]
        eq_(gr.get_tags(), tags1)
        eq_(gr.describe(), None)
        eq_(gr.describe(tags=True), tags1[0]['name'])

    first_commit = gr.get_hexsha()

    with patch.dict("os.environ", {"GIT_COMMITTER_DATE":
                                   "Fri, 08 Apr 2005 22:13:13 +0200"}):

        create_tree(gr.path, {'file': "123"})
        gr.add('file')
        gr.commit(msg="changed")

    gr.tag("annotated", message="annotation")
    tags2 = tags1 + [{'name': 'annotated', 'hexsha': gr.get_hexsha()}]
    eq_(gr.get_tags(), tags2)
    eq_(gr.describe(), tags2[1]['name'])

    # compare prev commit
    eq_(gr.describe(commitish=first_commit), None)
    eq_(gr.describe(commitish=first_commit, tags=True), tags1[0]['name'])


@with_tree(tree={'1': ""})
def test_get_commit_date(path):
    gr = GitRepo(path, create=True)
    eq_(gr.get_commit_date(), None)

    # Let's make a commit with a custom date
    DATE = "Wed Mar 14 03:47:30 2018 -0000"
    DATE_EPOCH = 1520999250
    gr.add('1')
    gr.commit("committed", date=DATE)
    gr = GitRepo(path, create=True)
    date = gr.get_commit_date()
    neq_(date, None)
    eq_(date, DATE_EPOCH)

    eq_(date, gr.get_commit_date('master'))
    # and even if we get into a detached head
    gr.checkout(gr.get_hexsha())
    eq_(gr.get_active_branch(), None)
    eq_(date, gr.get_commit_date('master'))


@with_tree(tree={"foo": "foo content",
                 "bar": "bar content"})
def test_fake_dates(path):
    gr = GitRepo(path, create=True, fake_dates=True)

    gr.add("foo")
    gr.commit("commit foo")

    seconds_initial = gr.config.obtain("datalad.fake-dates-start")

    # First commit is incremented by 1 second.
    eq_(seconds_initial + 1, gr.get_commit_date())

    # The second commit by 2.
    gr.add("bar")
    gr.commit("commit bar")
    eq_(seconds_initial + 2, gr.get_commit_date())

    # If we checkout another branch, its time is still based on the latest
    # timestamp in any local branch.
    gr.checkout("other", options=["--orphan"])
    with open(op.join(path, "baz"), "w") as ofh:
        ofh.write("baz content")
    gr.add("baz")
    gr.commit("commit baz")
    eq_(gr.get_active_branch(), "other")
    eq_(seconds_initial + 3, gr.get_commit_date())


def test_guard_BadName():
    from gitdb.exc import BadName

    calls = []

    class Vulnerable(object):
        def precommit(self):
            calls.append('precommit')

        @guard_BadName
        def __call__(self, x, y=2):
            if not calls:
                calls.append(1)
                raise BadName
            return x+y
    v = Vulnerable()
    eq_(v(1, y=3), 4)
    eq_(calls, [1, 'precommit'])


@with_tree(tree={"foo": "foo content"})
def test_custom_runner_protocol(path):
    # Check that a runner with a non-default protocol gets wired up correctly.
    prot = ExecutionTimeProtocol()
    gr = GitRepo(path, runner=Runner(cwd=path, protocol=prot), create=True)
    # now we run two commands
    #  1. to check if no known to possible git upstairs files in current path
    #  2. actually call git init
    eq_(len(prot), 2)
    gr.add("foo")
    eq_(len(prot), 3)
    assert_in("add", prot[2]["command"])
    gr.commit("commit foo")
    eq_(len(prot), 4)
    assert_in("commit", prot[3]["command"])
    ok_(all(p['duration'] >= 0 for p in prot))


@with_tempfile(mkdir=True)
def test_duecredit(path):
    # Just to check that no obvious side-effects
    run = Runner(cwd=path).run
    cmd = [
        sys.executable, "-c",
        "from datalad.support.gitrepo import GitRepo; GitRepo(%r, create=True)" % path
    ]

    env = os.environ.copy()

    # Test with duecredit not enabled for sure
    env.pop('DUECREDIT_ENABLE', None)
    # Alternative workaround for what to be fixed by
    # https://github.com/datalad/datalad/pull/3215
    # where underlying datalad process might issue a warning since our temp
    # cwd is not matching possibly present PWD env variable
    env.pop('PWD', None)

    out, err = run(cmd, env=env, expect_stderr=True)
    outs = out + err  # Let's not depend on where duecredit decides to spit out
    # All quiet
    eq_(outs, '')

    # and now enable DUECREDIT - output could come to stderr
    env['DUECREDIT_ENABLE'] = '1'
    out, err = run(cmd, env=env, expect_stderr=True)
    outs = out + err

    if external_versions['duecredit']:
        assert_in('Data management and distribution platform', outs)
    else:
        eq_(outs, '')