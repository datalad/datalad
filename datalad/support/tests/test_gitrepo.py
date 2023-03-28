# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class GitRepo

"""

import logging
import os
import os.path as op
import sys

import pytest

from datalad import get_encoding_info
from datalad.cmd import (
    StdOutCapture,
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.support.exceptions import (
    CommandError,
    FileNotInRepositoryError,
    InvalidGitRepositoryError,
    NoSuchPathError,
    PathKnownToRepositoryError,
)
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import (
    GitRepo,
    _normalize_path,
    normalize_paths,
    to_options,
)
from datalad.support.sshconnector import get_connection_hash
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_cwd_unchanged,
    assert_equal,
    assert_false,
    assert_in,
    assert_in_results,
    assert_is_instance,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_true,
    create_tree,
    eq_,
    get_most_obscure_supported_name,
    integration,
    neq_,
    ok_,
    skip_if_no_network,
    skip_if_on_windows,
    skip_nomultiplex_ssh,
    slow,
    swallow_logs,
    with_tempfile,
    with_tree,
    xfail_buggy_annex_info,
)
from datalad.utils import (
    Path,
    chpwd,
    getpwd,
    on_windows,
    rmtree,
)


@with_tempfile(mkdir=True)
def test_GitRepo_invalid_path(path=None):
    with chpwd(path):
        assert_raises(ValueError, GitRepo, path="git://some/url", create=True)
        ok_(not op.exists(op.join(path, "git:")))
        assert_raises(ValueError, GitRepo, path="file://some_location/path/at/location", create=True)
        ok_(not op.exists(op.join(path, "file:")))


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_GitRepo_instance_from_clone(src=None, dst=None):
    origin = GitRepo(src, create=True)
    gr = GitRepo.clone(src, dst)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(dst, '.git')))

    # do it again should raise ValueError since git will notice there's
    # already a git-repo at that path and therefore can't clone to `dst`
    # Note: Since GitRepo is now a WeakSingletonRepo, this is prevented from
    # happening atm. Disabling for now:
#    raise SkipTest("Disabled for RF: WeakSingletonRepo")
    with swallow_logs() as logs:
        assert_raises(ValueError, GitRepo.clone, src, dst)


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_instance_from_existing(path=None):
    GitRepo(path, create=True)

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_GitRepo_instance_from_not_existing(path=None, path2=None):
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
    assert_repo_status(path2, annex=False)

    # 4. create=True, path exists, but no git repo:
    gr = GitRepo(path, create=True)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path, '.git')))
    assert_repo_status(path, annex=False)


@with_tempfile
def test_GitRepo_init_options(path=None):
    # passing an option, not explicitly defined in GitRepo class:
    gr = GitRepo(path, create=True, bare=True)
    ok_(gr.config.getbool(section="core", option="bare"))


@with_tempfile
@with_tempfile(mkdir=True)
@with_tree(tree={'somefile': 'content', 'config': 'not a git config'})
@with_tree(tree={'afile': 'other',
                 '.git': {}})
@with_tempfile
@with_tempfile
def test_GitRepo_bare(path=None, empty_dir=None, non_empty_dir=None, empty_dot_git=None, non_bare=None,
                      clone_path=None):

    import gc

    # create a bare repo:
    gr = GitRepo(path, create=True, bare=True)
    assert_equal(gr.dot_git, gr.pathobj)
    assert_true(gr.bare)
    assert_true(gr.config.getbool("core", "bare"))
    assert_false((gr.pathobj / '.git').exists())
    assert_false(gr.call_git_success(['status'], expect_stderr=True))

    # kill the object and try to get a new instance on an existing bare repo:
    del gr
    gc.collect()

    gr = GitRepo(path, create=False)
    assert_equal(gr.dot_git, gr.pathobj)
    assert_true(gr.bare)
    assert_true(gr.config.getbool("core", "bare"))
    assert_false((gr.pathobj / '.git').exists())
    assert_false(gr.call_git_success(['status'], expect_stderr=True))

    # an empty dir is not a bare repo:
    assert_raises(InvalidGitRepositoryError, GitRepo, empty_dir,
                  create=False)

    # an arbitrary dir is not a bare repo:
    assert_raises(InvalidGitRepositoryError, GitRepo, non_empty_dir,
                  create=False)

    # nor is a path with an empty .git:
    assert_raises(InvalidGitRepositoryError, GitRepo, empty_dot_git,
                  create=False)

    # a regular repo is not bare
    non_bare_repo = GitRepo(non_bare, create=True)
    assert_false(non_bare_repo.bare)

    # we can have a bare clone
    clone = GitRepo.clone(non_bare, clone_path, clone_options={'bare': True})
    assert_true(clone.bare)

@with_tree(
    tree={
        'subds': {
            'file_name': ''
        }
    }
)
def test_init_fail_under_known_subdir(path=None):
    repo = GitRepo(path, create=True)
    repo.add(op.join('subds', 'file_name'))
    # Should fail even if we do not commit but only add to index:
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds'), create=True)
    assert_in("file_name", str(cme.value))  # we provide a list of offenders
    # and after we commit - the same story
    repo.commit("added file")
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds'), create=True)

    # But it would succeed if we disable the checks
    GitRepo(op.join(path, 'subds'), create=True, create_sanity_checks=False)


@with_tempfile
@with_tempfile
def test_GitRepo_equals(path1=None, path2=None):

    repo1 = GitRepo(path1)
    repo2 = GitRepo(path1)
    ok_(repo1 == repo2)
    eq_(repo1, repo2)
    repo2 = GitRepo(path2)
    neq_(repo1, repo2)
    ok_(repo1 != repo2)


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_GitRepo_add(src=None, path=None):

    gr = GitRepo(path)
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
    assert_repo_status(path)


@assert_cwd_unchanged
@with_tree(tree={
    'd': {'f1': 'content1',
          'f2': 'content2'},
    'file': 'content3',
    'd2': {'f1': 'content1',
          'f2': 'content2'},
    'file2': 'content3'

    })
def test_GitRepo_remove(path=None):

    gr = GitRepo(path, create=True)
    gr.add('*')
    gr.commit("committing all the files")

    eq_(gr.remove('file'), ['file'])
    eq_(set(gr.remove('d', r=True, f=True)), {'d/f1', 'd/f2'})

    eq_(set(gr.remove('*', r=True, f=True)), {'file2', 'd2/f1', 'd2/f2'})


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_commit(path=None):

    gr = GitRepo(path)
    filename = get_most_obscure_supported_name()
    with open(op.join(path, filename), 'w') as f:
        f.write("File to add to git")

    gr.add(filename)
    gr.commit("Testing GitRepo.commit().")
    assert_repo_status(gr)
    eq_("Testing GitRepo.commit().",
        gr.format_commit("%B").strip())

    with open(op.join(path, filename), 'w') as f:
        f.write("changed content")

    gr.add(filename)
    gr.commit("commit with options", options=to_options(dry_run=True))
    # wasn't actually committed:
    ok_(gr.dirty)

    # commit with empty message:
    gr.commit()
    assert_repo_status(gr)
    assert_equal(gr.format_commit("%B").strip(), "[DATALAD] Recorded changes")

    # amend commit:
    assert_equal(len(list(gr.get_branch_commits_())), 2)
    last_sha = gr.get_hexsha()
    with open(op.join(path, filename), 'w') as f:
        f.write("changed again")
    gr.add(filename)
    gr.commit("amend message", options=to_options(amend=True))
    assert_repo_status(gr)
    assert_equal(gr.format_commit("%B").strip(), "amend message")
    assert_not_equal(last_sha, gr.get_hexsha())
    assert_equal(len(list(gr.get_branch_commits_())), 2)
    # amend w/o message maintains previous one:
    gr.commit(options=to_options(amend=True))
    assert_repo_status(gr)
    assert_equal(len(list(gr.get_branch_commits_())), 2)
    assert_equal(gr.format_commit("%B").strip(), "amend message")

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


@with_tempfile
def test_GitRepo_get_indexed_files(path=None):

    gr = GitRepo(path)
    for filename in ('some1.txt', 'some2.dat'):
        with open(op.join(path, filename), 'w') as f:
            f.write(filename)
        gr.add(filename)
    gr.commit('Some files')

    idx_list = gr.get_indexed_files()

    runner = WitlessRunner(cwd=path)
    out = runner.run(['git', 'ls-files'], protocol=StdOutCapture)
    out_list = list(filter(bool, out['stdout'].split('\n')))

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
def test_normalize_path(git_path=None):

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
@with_tempfile
def test_GitRepo_remote_add(path=None):
    gr = GitRepo(path)
    gr.add_remote('github', 'https://github.com/datalad/testrepo--basic--r1')
    out = gr.get_remotes()
    assert_in('github', out)
    eq_(len(out), 1)
    eq_('https://github.com/datalad/testrepo--basic--r1', gr.config['remote.github.url'])


@with_tempfile
def test_GitRepo_remote_remove(path=None):

    gr = GitRepo(path)
    gr.add_remote('github', 'https://github.com/datalad/testrepo--basic--r1')
    out = gr.get_remotes()
    eq_(len(out), 1)
    gr.remove_remote('github')
    out = gr.get_remotes()
    eq_(len(out), 0)


@with_tempfile
def test_GitRepo_get_remote_url(path=None):

    gr = GitRepo(path)
    gr.add_remote('github', 'https://github.com/datalad/testrepo--basic--r1')
    eq_(gr.get_remote_url('github'),
        'https://github.com/datalad/testrepo--basic--r1')


@with_tempfile
@with_tempfile
def test_GitRepo_fetch(orig_path=None, clone_path=None):

    origin = GitRepo(orig_path)
    with open(op.join(orig_path, 'some.txt'), 'w') as f:
        f.write("New text file.")
    origin.add('some.txt')
    origin.commit("new file added.")

    clone = GitRepo.clone(orig_path, clone_path)
    filename = get_most_obscure_supported_name()

    origin.checkout("new_branch", ['-b'])
    with open(op.join(orig_path, filename), 'w') as f:
        f.write("New file.")
    origin.add(filename)
    origin.commit("new file added.")

    fetched = clone.fetch(remote=DEFAULT_REMOTE)
    # test FetchInfo list returned by fetch
    eq_([DEFAULT_REMOTE + '/' + clone.get_active_branch(),
         DEFAULT_REMOTE + '/new_branch'],
        [commit['ref'] for commit in fetched])

    assert_repo_status(clone.path, annex=False)
    assert_in(DEFAULT_REMOTE + "/new_branch", clone.get_remote_branches())
    assert_in(filename, clone.get_files(DEFAULT_REMOTE + "/new_branch"))
    assert_false(op.exists(op.join(clone_path, filename)))  # not checked out

    # create a remote without an URL:
    origin.add_remote('not-available', 'git://example.com/not/existing')
    origin.config.unset('remote.not-available.url', scope='local')

    # fetch without provided URL
    assert_raises(CommandError, origin.fetch, 'not-available')


def _path2localsshurl(path):
    """Helper to build valid localhost SSH urls on Windows too"""
    path = op.abspath(path)
    p = Path(path)
    if p.drive:
        path = '/'.join(('/{}'.format(p.drive[0]),) + p.parts[1:])
    url = "ssh://datalad-test{}".format(path)
    return url


@skip_nomultiplex_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_fetch(remote_path=None, repo_path=None):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path)
    with open(op.join(remote_path, 'some.txt'), 'w') as f:
        f.write("New text file.")
    remote_repo.add('some.txt')
    remote_repo.commit("new file added.")

    url = _path2localsshurl(remote_path)
    socket_path = op.join(str(ssh_manager.socket_dir),
                          get_connection_hash('datalad-test'))
    repo = GitRepo(repo_path, create=True)
    repo.add_remote("ssh-remote", url)

    # we don't know any branches of the remote:
    eq_([], repo.get_remote_branches())

    fetched = repo.fetch(remote="ssh-remote")
    assert_in('ssh-remote/' + DEFAULT_BRANCH,
              [commit['ref'] for commit in fetched])
    assert_repo_status(repo)

    # the connection is known to the SSH manager, since fetch() requested it:
    assert_in(socket_path, list(map(str, ssh_manager._connections)))
    # and socket was created:
    ok_(op.exists(socket_path))

    # we actually fetched it:
    assert_in('ssh-remote/' + DEFAULT_BRANCH,
              repo.get_remote_branches())


@skip_nomultiplex_ssh
@with_tempfile
@with_tempfile
def test_GitRepo_ssh_push(repo_path=None, remote_path=None):
    from datalad import ssh_manager

    remote_repo = GitRepo(remote_path, create=True)
    url = _path2localsshurl(remote_path)
    socket_path = op.join(str(ssh_manager.socket_dir),
                          get_connection_hash('datalad-test'))
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
    pushed = list(repo.push(remote="ssh-remote", refspec="ssh-test"))
    # test PushInfo
    assert_in("refs/heads/ssh-test", [p['from_ref'] for p in pushed])
    assert_in("refs/heads/ssh-test", [p['to_ref'] for p in pushed])

    # the connection is known to the SSH manager, since fetch() requested it:
    assert_in(socket_path, list(map(str, ssh_manager._connections)))
    # and socket was created:
    ok_(op.exists(socket_path))

    # remote now knows the changes:
    assert_in("ssh-test", remote_repo.get_branches())
    assert_in("ssh_testfile.dat", remote_repo.get_files("ssh-test"))

    # amend to make it require "--force":
    repo.commit("amended", options=['--amend'])
    # push without --force should yield an error:
    res = repo.push(remote="ssh-remote", refspec="ssh-test")
    assert_in_results(
        res,
        from_ref='refs/heads/ssh-test',
        to_ref='refs/heads/ssh-test',
        operations=['rejected', 'error'],
        note='[rejected] (non-fast-forward)',
        remote='ssh-remote',
    )
    # now push using force:
    repo.push(remote="ssh-remote", refspec="ssh-test", force=True)
    # correct commit message in remote:
    assert_in("amended",
              remote_repo.format_commit(
                  '%s',
                  list(remote_repo.get_branch_commits_('ssh-test'))[-1]
              ))


@with_tempfile
@with_tempfile
def test_GitRepo_push_n_checkout(orig_path=None, clone_path=None):

    origin = GitRepo(orig_path)
    clone = GitRepo.clone(orig_path, clone_path)
    filename = get_most_obscure_supported_name()

    with open(op.join(clone_path, filename), 'w') as f:
        f.write("New file.")
    clone.add(filename)
    clone.commit("new file added.")
    # TODO: need checkout first:
    clone.push(DEFAULT_REMOTE, '+{}:new-branch'.format(DEFAULT_BRANCH))
    origin.checkout('new-branch')
    ok_(op.exists(op.join(orig_path, filename)))


@with_tempfile
@with_tempfile
@with_tempfile
def test_GitRepo_remote_update(path1=None, path2=None, path3=None):

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


@with_tempfile
@with_tempfile
def test_GitRepo_get_files(src_path=None, path=None):
    src = GitRepo(src_path)
    for filename in ('some1.txt', 'some2.dat'):
        with open(op.join(src_path, filename), 'w') as f:
            f.write(filename)
        src.add(filename)
    src.commit('Some files')

    gr = GitRepo.clone(src.path, path)
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
    remote_files = set(gr.get_files(
        branch=f"{DEFAULT_REMOTE}/{DEFAULT_BRANCH}"))

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
    remote_files = set(gr.get_files(
        branch=f"{DEFAULT_REMOTE}/{DEFAULT_BRANCH}"))
    eq_(remote_files, os_files)
    eq_(set([filename]), local_files.difference(remote_files))

    # switch back and query non-active branch:
    gr.checkout(DEFAULT_BRANCH)
    local_files = set(gr.get_files())
    branch_files = set(gr.get_files(branch="new_branch"))
    eq_(set([filename]), branch_files.difference(local_files))


@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile
def test_GitRepo_get_toppath(repo=None, tempdir=None, repo2=None):
    GitRepo(repo, create=True)
    reporeal = str(Path(repo).resolve())
    eq_(GitRepo.get_toppath(repo, follow_up=False), reporeal)
    eq_(GitRepo.get_toppath(repo), repo)
    # Generate some nested directory
    GitRepo(repo2, create=True)
    repo2real = str(Path(repo2).resolve())
    nested = op.join(repo2, "d1", "d2")
    os.makedirs(nested)
    eq_(GitRepo.get_toppath(nested, follow_up=False), repo2real)
    eq_(GitRepo.get_toppath(nested), repo2)
    # and if not under git, should return None
    eq_(GitRepo.get_toppath(tempdir), None)


@with_tempfile(mkdir=True)
def test_GitRepo_dirty(path=None):

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

    subm = GitRepo(repo.pathobj / "subm", create=True)
    (subm.pathobj / "subfile").write_text(u"")
    subm.save()
    repo.save()
    ok_(not repo.dirty)
    (subm.pathobj / "subfile").write_text(u"changed")
    ok_(repo.dirty)

    # User configuration doesn't affect .dirty's answer.
    repo.config.set("diff.ignoreSubmodules", "all", scope="local")
    ok_(repo.dirty)
    # GitRepo.commit currently can't handle this setting, so remove it for the
    # save() calls below.
    repo.config.unset("diff.ignoreSubmodules", scope="local")
    subm.save()
    repo.save()
    ok_(not repo.dirty)

    repo.config.set("status.showUntrackedFiles", "no", scope="local")
    create_tree(repo.path, {"untracked_dir": {"a": "a"}})
    ok_(repo.dirty)


@with_tempfile(mkdir=True)
def test_GitRepo_get_merge_base(src=None):
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
def test_GitRepo_git_get_branch_commits_(src=None):

    repo = GitRepo(src, create=True)
    with open(op.join(src, 'file.txt'), 'w') as f:
        f.write('load')
    repo.add('*')
    repo.commit('committing')
    # go in a branch with a name that matches the file to require
    # proper disambiguation
    repo.call_git(['checkout', '-b', 'file.txt'])

    commits_default = list(repo.get_branch_commits_())
    commits = list(repo.get_branch_commits_(DEFAULT_BRANCH))
    eq_(commits, commits_default)
    eq_(len(commits), 1)


@with_tempfile
@with_tempfile
def test_get_tracking_branch(o_path=None, c_path=None):
    src = GitRepo(o_path)
    for filename in ('some1.txt', 'some2.dat'):
        with open(op.join(o_path, filename), 'w') as f:
            f.write(filename)
        src.add(filename)
    src.commit('Some files')

    clone = GitRepo.clone(o_path, c_path)
    # Note, that the default branch might differ even if it is always 'master'.
    # For direct mode annex repositories it would then be "annex/direct/master"
    # for example. Therefore use whatever branch is checked out by default:
    master_branch = clone.get_active_branch()
    ok_(master_branch)

    eq_((DEFAULT_REMOTE, 'refs/heads/' + master_branch),
        clone.get_tracking_branch())

    clone.checkout('new_branch', ['-b'])

    eq_((None, None), clone.get_tracking_branch())

    eq_((DEFAULT_REMOTE, 'refs/heads/' + master_branch),
        clone.get_tracking_branch(master_branch))

    clone.checkout(master_branch, options=["--track", "-btopic"])
    eq_(('.', 'refs/heads/' + master_branch),
        clone.get_tracking_branch())
    eq_((None, None),
        clone.get_tracking_branch(remote_only=True))


@with_tempfile
def test_GitRepo_get_submodules(path=None):
    repo = GitRepo(path, create=True)

    s_abc = GitRepo(op.join(path, "s_abc"), create=True)
    s_abc.commit(msg="c s_abc", options=["--allow-empty"])
    repo.save(path="s_abc")

    s_xyz = GitRepo(op.join(path, "s_xyz"), create=True)
    s_xyz.commit(msg="c s_xyz", options=["--allow-empty"])
    repo.save(path="s_xyz")

    eq_([s["gitmodule_name"]
         for s in repo.get_submodules(sorted_=True)],
        ["s_abc", "s_xyz"])

    # Limit by path
    eq_([s["gitmodule_name"]
         for s in repo.get_submodules(paths=["s_abc"])],
        ["s_abc"])

    # Pointing to a path within submodule should include it too
    eq_([s["gitmodule_name"]
         for s in repo.get_submodules(paths=["s_abc/unrelated"])],
        ["s_abc"])

    # top level should list all submodules
    eq_([s["gitmodule_name"]
         for s in repo.get_submodules(paths=[repo.path])],
        ["s_abc", "s_xyz"])

    # Limit by non-existing/non-matching path
    eq_([s["gitmodule_name"]
         for s in repo.get_submodules(paths=["s_unknown"])],
        [])


@with_tempfile
def test_get_submodules_parent_on_unborn_branch(path=None):
    repo = GitRepo(path, create=True)
    subrepo = GitRepo(op.join(path, "sub"), create=True)
    subrepo.commit(msg="s", options=["--allow-empty"])
    repo.save(path="sub")
    eq_([s["gitmodule_name"] for s in repo.get_submodules_()],
        ["sub"])


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


def test_to_options_from_gitpython():
    """Imported from GitPython and modified.

    Original copyright:
        Copyright (C) 2008, 2009 Michael Trier and contributors
    Original license:
        BSD 3-Clause "New" or "Revised" License
    """
    eq_(["-s"], to_options(**{'s': True}))
    eq_(["-s", "5"], to_options(**{'s': 5}))
    eq_([], to_options(**{'s': None}))

    eq_(["--max-count"], to_options(**{'max_count': True}))
    eq_(["--max-count=5"], to_options(**{'max_count': 5}))
    eq_(["--max-count=0"], to_options(**{'max_count': 0}))
    eq_([], to_options(**{'max_count': None}))

    # Multiple args are supported by using lists/tuples
    eq_(["-L", "1-3", "-L", "12-18"], to_options(**{'L': ('1-3', '12-18')}))
    eq_(["-C", "-C"], to_options(**{'C': [True, True, None, False]}))

    # order is undefined
    res = to_options(**{'s': True, 't': True})
    eq_({'-s', '-t'}, set(res))


@with_tempfile
def test_GitRepo_count_objects(repo_path=None):

    repo = GitRepo(repo_path, create=True)
    # test if dictionary returned
    eq_(isinstance(repo.count_objects, dict), True)
    # test if dictionary contains keys and values we expect
    empty_count = {'count': 0, 'garbage': 0,  'in-pack': 0, 'packs': 0, 'prune-packable': 0,
                   'size': 0, 'size-garbage': 0, 'size-pack': 0}
    eq_(empty_count, repo.count_objects)


# this is simply broken on win, but less important
# https://github.com/datalad/datalad/issues/3639
@skip_if_on_windows
@with_tempfile
def test_optimized_cloning(path=None):
    # make test repo with one file and one commit
    originpath = op.join(path, 'origin')
    repo = GitRepo(originpath, create=True)
    with open(op.join(originpath, 'test'), 'w') as f:
        f.write('some')
    repo.add('test')
    repo.commit('init')
    assert_repo_status(originpath, annex=False)
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
    for src in (originpath, get_local_file_url(originpath, compatibility='git')):
        clone = GitRepo.clone(url=src, path=clonepath, create=True)
        clone_inodes = _get_inodes(clone)
        eq_(origin_inodes, clone_inodes, msg='with src={}'.format(src))
        rmtree(clonepath)
#        del clone
#        gc.collect()
        # Note: del needed, since otherwise WeakSingletonRepo would just
        # return the original object in second run


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_GitRepo_flyweight(path1=None, path2=None):

    import gc

    repo1 = GitRepo(path1, create=True)
    assert_is_instance(repo1, GitRepo)

    # Due to issue 4862, we currently still require gc.collect() under unclear
    # circumstances to get rid of an exception traceback when creating in an
    # existing directory. That traceback references the respective function
    # frames which in turn reference the repo instance (they are methods).
    # Doesn't happen on all systems, though. Eventually we need to figure that
    # out.
    # However, still test for the refcount after gc.collect() to ensure we don't
    # introduce new circular references and make the issue worse!
    gc.collect()

    # As long as we don't reintroduce any circular references or produce
    # garbage during instantiation that isn't picked up immediately, `repo1`
    # should be the only counted reference to this instance.
    # Note, that sys.getrefcount reports its own argument and therefore one
    # reference too much.
    assert_equal(1, sys.getrefcount(repo1) - 1)

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

    orig_id = id(repo1)

    # Be sure we have exactly one object in memory:
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.path == path1]))

    # deleting one reference doesn't change anything - we still get the same
    # thing:
    gc.collect()  #  TODO: see first comment above
    del repo1
    ok_(repo2 is not None)
    ok_(repo2 is repo3)
    ok_(repo2 == repo3)

    # re-requesting still delivers the same thing:
    repo1 = GitRepo(path1)
    assert_equal(orig_id, id(repo1))

    # killing all references should result in the instance being gc'd and
    # re-request yields a new object:
    del repo1
    del repo2

    # Killing last reference will lead to garbage collection which will call
    # GitRepo's finalizer:
    with swallow_logs(new_level=1) as cml:
        del repo3
        gc.collect()  # TODO: see first comment above
        cml.assert_logged(msg="Finalizer called on: GitRepo(%s)" % path1,
                          level="Level 1",
                          regex=False)

    # Flyweight is gone:
    assert_not_in(path1, GitRepo._unique_instances.keys())
    # gc doesn't know any instance anymore:
    assert_equal([], [o for o in gc.get_objects()
                      if isinstance(o, GitRepo) and o.path == path1])

    # new object is created on re-request:
    repo1 = GitRepo(path1)
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.path == path1]))


@with_tree(tree={'ignore-sub.me': {'a_file.txt': 'some content'},
                 'ignore.me': 'ignored content',
                 'dontigno.re': 'other content'})
def test_GitRepo_gitignore(path=None):

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
    eq_(cme.value.paths, ['ignore.me'])

    with assert_raises(GitIgnoreError) as cme:
        gr.add(['ignore.me', 'dontigno.re', op.join('ignore-sub.me', 'a_file.txt')])
    eq_(set(cme.value.paths), {'ignore.me', 'ignore-sub.me'})

    eq_(gr.get_gitattributes('.')['.'], {})  # nothing is recorded within .gitattributes


@with_tempfile(mkdir=True)
def test_GitRepo_set_remote_url(path=None):

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
    gr.config.unset('remote.some-without-url.url', scope='local')
    with assert_raises(KeyError):
        gr.config['remote.some-without-url.url']
    eq_(set(gr.get_remotes()), {'some', 'some-without-url'})
    eq_(set(gr.get_remotes(with_urls_only=True)), {'some'})


@with_tempfile(mkdir=True)
def test_gitattributes(path=None):
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
    # attributes file is not added or committed, we can ignore such
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
    if get_encoding_info()['default'] != 'ascii' and not on_windows:
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
    # mode='a' appends additional key/value
    gr.set_gitattributes([('*', {'king': 'kong'})], mode='a')
    eq_(gr.get_gitattributes('.')['.'], {'some': 'nonsense', 'king': 'kong'})
    # handle files without trailing newline
    with open(op.join(gr.path, '.gitattributes'), 'r+') as f:
        s = f.read()
        f.seek(0)
        f.write(s.rstrip())
        f.truncate()
    gr.set_gitattributes([('*', {'ding': 'dong'})], mode='a')
    eq_(gr.get_gitattributes('.')['.'],
        {'some': 'nonsense', 'king': 'kong', 'ding': 'dong'})


@with_tempfile(mkdir=True)
def test_get_hexsha_tag(path=None):
    gr = GitRepo(path, create=True)
    gr.commit(msg="msg", options=["--allow-empty"])
    gr.tag("atag", message="atag msg")
    # get_hexsha() dereferences a tag to a commit.
    eq_(gr.get_hexsha("atag"), gr.get_hexsha())


@with_tempfile(mkdir=True)
def test_get_tags(path=None):
    from unittest.mock import patch

    gr = GitRepo(path, create=True)
    eq_(gr.get_tags(), [])
    eq_(gr.describe(), None)

    # Explicitly override the committer date because tests may set it to a
    # fixed value, but we want to check that the returned tags are sorted by
    # the date the tag (for annotaged tags) or commit (for lightweight tags)
    # was created.
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

    with patch.dict("os.environ", {"GIT_COMMITTER_DATE":
                                   "Fri, 09 Apr 2005 22:13:13 +0200"}):
        gr.tag("annotated", message="annotation")
    # The annotated tag happened later, so it comes last.
    tags2 = tags1 + [{'name': 'annotated', 'hexsha': gr.get_hexsha()}]
    eq_(gr.get_tags(), tags2)
    eq_(gr.describe(), tags2[1]['name'])

    # compare prev commit
    eq_(gr.describe(commitish=first_commit), None)
    eq_(gr.describe(commitish=first_commit, tags=True), tags1[0]['name'])

    gr.tag('specific', commit='HEAD~1')
    eq_(gr.get_hexsha('specific'), gr.get_hexsha('HEAD~1'))
    assert_in('specific', gr.get_tags(output='name'))

    # retag a different commit
    assert_raises(CommandError, gr.tag, 'specific', commit='HEAD')
    # force it
    gr.tag('specific', commit='HEAD', options=['-f'])
    eq_(gr.get_hexsha('specific'), gr.get_hexsha('HEAD'))

    # delete
    gr.call_git(['tag', '-d', 'specific'])
    eq_(gr.get_tags(), tags2)
    # more than one
    gr.tag('one')
    gr.tag('two')
    gr.call_git(['tag', '-d', 'one', 'two'])
    eq_(gr.get_tags(), tags2)


@with_tree(tree={'1': ""})
def test_get_commit_date(path=None):
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

    eq_(date, gr.get_commit_date(DEFAULT_BRANCH))
    # and even if we get into a detached head
    gr.checkout(gr.get_hexsha())
    eq_(gr.get_active_branch(), None)
    eq_(date, gr.get_commit_date(DEFAULT_BRANCH))


@with_tree(tree={"foo": "foo content",
                 "bar": "bar content"})
def test_fake_dates(path=None):
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


@slow   # 15sec on Yarik's laptop and tripped Travis CI
@with_tempfile(mkdir=True)
def test_duecredit(path=None):
    # Just to check that no obvious side-effects
    run = WitlessRunner(cwd=path).run
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

    out = run(cmd, env=env, protocol=StdOutErrCapture)
    outs = ''.join(out.values()) # Let's not depend on where duecredit decides to spit out
    # All quiet
    test_string = 'Data management and distribution platform'
    assert_not_in(test_string, outs)

    # and now enable DUECREDIT - output could come to stderr
    env['DUECREDIT_ENABLE'] = '1'
    out = run(cmd, env=env, protocol=StdOutErrCapture)
    outs = ''.join(out.values())

    if external_versions['duecredit']:
        assert_in(test_string, outs)
    else:
        assert_not_in(test_string, outs)


@with_tempfile(mkdir=True)
def test_GitRepo_get_revisions(path=None):
    gr = GitRepo(path, create=True)

    def commit(msg):
        gr.commit(msg=msg, options=["--allow-empty"])

    # We catch the error and return empty if the current branch doesn't have a
    # commit checked out.
    eq_(gr.get_revisions(), [])

    # But will raise if on a bad ref name, including an unborn branch.
    with assert_raises(CommandError):
        gr.get_revisions(DEFAULT_BRANCH)

    # By default, we query HEAD.
    commit("1")
    eq_(len(gr.get_revisions()), 1)

    gr.checkout("other", options=["-b"])
    commit("2")

    # We can also query branch by name.
    eq_(len(gr.get_revisions(DEFAULT_BRANCH)), 1)
    eq_(len(gr.get_revisions("other")), 2)

    # "name" is sugar for ["name"].
    eq_(gr.get_revisions(DEFAULT_BRANCH),
        gr.get_revisions([DEFAULT_BRANCH]))

    gr.checkout(DEFAULT_BRANCH)
    commit("3")
    eq_(len(gr.get_revisions(DEFAULT_BRANCH)), 2)
    # We can pass multiple revisions...
    eq_(len(gr.get_revisions([DEFAULT_BRANCH, "other"])), 3)
    # ... or options like --all and --branches
    eq_(gr.get_revisions([DEFAULT_BRANCH, "other"]),
        gr.get_revisions(options=["--all"]))

    # Ranges are supported.
    eq_(gr.get_revisions(DEFAULT_BRANCH + ".."), [])


@xfail_buggy_annex_info
@with_tree({"foo": "foo",
            ".gitattributes": "* annex.largefiles=anything"})
def test_gitrepo_add_to_git_with_annex_v7(path=None):
    from datalad.support.annexrepo import AnnexRepo
    ar = AnnexRepo(path, create=True, version=7)
    gr = GitRepo(path)
    gr.add("foo")
    gr.commit(msg="c1")
    assert_false(ar.is_under_annex("foo"))


@with_tree({"foo": "foo", "bar": "bar"})
def test_gitrepo_call_git_methods(path=None):
    gr = GitRepo(path)
    gr.add(["foo", "bar"])
    gr.commit(msg="foobar")
    gr.call_git(["mv"], files=["foo", "foo.txt"])
    ok_(op.exists(op.join(gr.path, 'foo.txt')))

    for expect_fail, check in [(False, assert_in),
                               (True, assert_not_in)]:
        with swallow_logs(new_level=logging.DEBUG) as cml:
            with assert_raises(CommandError):
                gr.call_git(["mv"], files=["notthere", "dest"],
                            expect_fail=expect_fail)
            check("fatal: bad source", cml.out)

    eq_(list(gr.call_git_items_(["ls-files"], read_only=True)),
        ["bar", "foo.txt"])
    eq_(list(gr.call_git_items_(["ls-files", "-z"], sep="\0", read_only=True)),
        ["bar", "foo.txt"])

    with assert_raises(AssertionError):
        gr.call_git_oneline(["ls-files"], read_only=True)

    eq_(gr.call_git_oneline(["ls-files"], files=["bar"], read_only=True),
        "bar")

    ok_(gr.call_git_success(["rev-parse", "HEAD^{commit}"], read_only=True))
    with swallow_logs(new_level=logging.DEBUG) as cml:
        assert_false(gr.call_git_success(["rev-parse", "HEAD^{blob}"],
                                         read_only=True))
        assert_not_in("expected blob type", cml.out)


@integration
    # http is well tested already
    # 'git' is not longer supported
@pytest.mark.parametrize("proto", ["https"])
@skip_if_no_network
@with_tempfile
def test_protocols(destdir=None, *, proto):
    # git-annex-standalone build can get git bundle which would fail to
    # download via https, resulting in messages such as
    #  fatal: unable to find remote helper for 'https'
    # which happened with git-annex-standalone 7.20191017+git2-g7b13db551-1~ndall+1
    GitRepo.clone('%s://github.com/datalad-tester/testtt' % proto, destdir)

@with_tempfile
def test_gitrepo_push_default_first_kludge(path=None):
    path = Path(path)
    repo_a = GitRepo(path / "a", bare=True)
    repo_b = GitRepo.clone(repo_a.path, str(path / "b"))

    (repo_b.pathobj / "foo").write_text("foo")
    repo_b.save()

    # push() usually pushes all refspecs in one go.
    with swallow_logs(new_level=logging.DEBUG) as cml:
        res_oneshot = repo_b.push(remote=DEFAULT_REMOTE,
                                  refspec=[DEFAULT_BRANCH + ":b-oneshot",
                                           DEFAULT_BRANCH + ":a-oneshot",
                                           DEFAULT_BRANCH + ":c-oneshot"])
    cmds_oneshot = [ln for ln in cml.out.splitlines()
                    if "Run" in ln and "push" in ln and DEFAULT_BRANCH in ln]
    eq_(len(cmds_oneshot), 1)
    assert_in(":a-oneshot", cmds_oneshot[0])
    assert_in(":b-oneshot", cmds_oneshot[0])
    assert_in(":c-oneshot", cmds_oneshot[0])
    eq_(len(res_oneshot), 3)

    # But if datalad-push-default-first is set...
    cfg_var = f"remote.{DEFAULT_REMOTE}.datalad-push-default-first"
    repo_b.config.set(cfg_var, "true", scope="local")
    with swallow_logs(new_level=logging.DEBUG) as cml:
        res_twoshot = repo_b.push(remote=DEFAULT_REMOTE,
                                  refspec=[DEFAULT_BRANCH + ":b-twoshot",
                                           DEFAULT_BRANCH + ":a-twoshot",
                                           DEFAULT_BRANCH + ":c-twoshot"])
    cmds_twoshot = [ln for ln in cml.out.splitlines()
                    if "Run" in ln and "push" in ln and DEFAULT_BRANCH in ln]
    # ... there are instead two git-push calls.
    eq_(len(cmds_twoshot), 2)
    # The first is for the first item of the refspec.
    assert_in(":b-twoshot", cmds_twoshot[0])
    assert_not_in(":b-twoshot", cmds_twoshot[1])
    # The remaining items are in the second call.
    assert_in(":a-twoshot", cmds_twoshot[1])
    assert_in(":c-twoshot", cmds_twoshot[1])
    assert_not_in(":c-twoshot", cmds_twoshot[0])
    assert_not_in(":a-twoshot", cmds_twoshot[0])
    # The result returned by push() has the same number of records, though.
    eq_(len(res_twoshot), 3)
    # The configuration variable is removed afterward.
    assert_false(repo_b.config.get(cfg_var))
