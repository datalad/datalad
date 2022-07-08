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

from datalad.dataset.gitrepo import (
    GitRepo,
    _get_dot_git,
)
from datalad.support.exceptions import (
    CommandError,
    PathKnownToRepositoryError,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_cwd_unchanged,
    assert_equal,
    assert_false,
    assert_in,
    assert_is_instance,
    assert_not_in,
    assert_raises,
    eq_,
    neq_,
    ok_,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
)


@with_tempfile(mkdir=True)
def test_GitRepo_invalid_path(path=None):
    with chpwd(path):
        assert_raises(ValueError, GitRepo, path="git://some/url")
        ok_(not op.exists(op.join(path, "git:")))
        assert_raises(ValueError, GitRepo, path="file://some/relative/path")
        ok_(not op.exists(op.join(path, "file:")))


@assert_cwd_unchanged
@with_tempfile
def test_GitRepo_instance_from_existing(path=None):
    GitRepo(path).init()

    gr = GitRepo(path)
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_GitRepo_instance_from_not_existing(path=None, path2=None):
    # 1. create=False and path doesn't exist:
    repo = GitRepo(path)
    assert_false(op.exists(path))

    # 2. create=False, path exists, but no git repo:
    os.mkdir(path)
    ok_(op.exists(path))
    repo = GitRepo(path)
    assert_false(op.exists(op.join(path, '.git')))

    # 3. create=True, path doesn't exist:
    gr = GitRepo(path2).init()
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path2, '.git')))
    # re-enable from core GitRepo has a status() method
    #assert_repo_status(path2, annex=False)

    # 4. create=True, path exists, but no git repo:
    gr = GitRepo(path).init()
    assert_is_instance(gr, GitRepo, "GitRepo was not created.")
    ok_(op.exists(op.join(path, '.git')))
    # re-enable from core GitRepo has a status() method
    #assert_repo_status(path, annex=False)


@with_tempfile
def test_GitRepo_init_options(path=None):
    # passing an option, not explicitly defined in GitRepo class:
    gr = GitRepo(path).init(init_options=['--bare'])
    ok_(gr.cfg.getbool(section="core", option="bare"))


@with_tree(
    tree={
        'subds': {
            'file_name': ''
        }
    }
)
def test_init_fail_under_known_subdir(path=None):
    repo = GitRepo(path).init()
    repo.call_git(['add', op.join('subds', 'file_name')])
    # Should fail even if we do not commit but only add to index:
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds')).init()
    assert_in("file_name", str(cme.value))  # we provide a list of offenders
    # and after we commit - the same story
    repo.call_git(['commit', '-m', "added file"])
    with assert_raises(PathKnownToRepositoryError) as cme:
        GitRepo(op.join(path, 'subds')).init()

    # But it would succeed if we disable the checks
    GitRepo(op.join(path, 'subds')).init(sanity_checks=False)


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


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_GitRepo_flyweight(path1=None, path2=None):

    import gc

    repo1 = GitRepo(path1).init()
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
    repo2 = GitRepo(path1).init()
    assert_is_instance(repo2, GitRepo)

    # the very same object:
    ok_(repo1 is repo2)

    # reference the same in a different way:
    with chpwd(path1):
        repo3 = GitRepo(op.relpath(path1, start=path2))

    # it's the same object:
    ok_(repo1 is repo3)

    # and realpath attribute is the same, so they are still equal:
    ok_(repo1 == repo3)

    orig_id = id(repo1)

    # Be sure we have exactly one object in memory:
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.pathobj == Path(path1)]))

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
                      if isinstance(o, GitRepo) and o.pathobj == Path(path1)])

    # new object is created on re-request:
    repo1 = GitRepo(path1)
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.pathobj == Path(path1)]))


@with_tree({"foo": "foo", "bar": "bar"})
def test_gitrepo_call_git_methods(path=None):
    gr = GitRepo(path).init()
    gr.call_git(['add', "foo", "bar"])
    gr.call_git(['commit', '-m', "foobar"])
    gr.call_git(["mv"], files=["foo", "foo.txt"])
    ok_((gr.pathobj / 'foo.txt').exists())

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
        # Note: The custom separator has trailing empty item, but this is an
        # arbitrary command with unknown output it isn't safe to trim it.
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


@with_tree(tree={"foo": "foo content",
                 "bar": "bar content"})
def test_fake_dates(path=None):
    raise SkipTest("Core GitRepo class does not have format_commit() yet")

    gr = GitRepo(path).init()
    gr.cfg.set('datalad.fake-dates', 'true')

    gr.call_git(['add', "foo"])
    gr.call_git(['commit', '-m', 'some', "foo"])

    seconds_initial = gr.cfg.obtain("datalad.fake-dates-start")

    # First commit is incremented by 1 second.
    eq_(seconds_initial + 1,
        int(gr.format_commit('%at')))

    # The second commit by 2.
    gr.call_git(['add', "bar"])
    gr.call_git(['commit', '-m', 'some', "bar"])
    eq_(seconds_initial + 2,
        int(gr.format_commit('%at')))

    # If we checkout another branch, its time is still based on the latest
    # timestamp in any local branch.
    gr.call_git(['checkout', "--orphan", 'other'])
    with open(op.join(path, "baz"), "w") as ofh:
        ofh.write("baz content")
    gr.call_git(['add', "baz"])
    gr.call_git(['commit', '-m', 'some', "baz"])
    eq_(gr.get_active_branch(), "other")
    eq_(seconds_initial + 3,
        int(gr.format_commit('%at')))


@with_tempfile(mkdir=True)
@with_tree(tree={".git": {}})
@with_tree(tree={"HEAD": "",
                 "config": ""})
@with_tree(tree={".git": "gitdir: subdir"})
def test_get_dot_git(emptycase=None, gitdircase=None, barecase=None, gitfilecase=None):
    emptycase = Path(emptycase)
    gitdircase = Path(gitdircase)
    barecase = Path(barecase)
    gitfilecase = Path(gitfilecase)

    # the test is not actually testing resolving (we can trust that)
    # but it is exercising the internal code paths involved in it
    for r in (True, False):
        assert_raises(RuntimeError, _get_dot_git, emptycase, resolved=r)
        eq_(_get_dot_git(emptycase, ok_missing=True, resolved=r),
            emptycase / '.git')

        eq_(_get_dot_git(gitdircase, resolved=r),
            (gitdircase.resolve() if r else gitdircase) / '.git')

        eq_(_get_dot_git(barecase, resolved=r),
            barecase.resolve() if r else barecase)

        eq_(_get_dot_git(gitfilecase, resolved=r),
            (gitfilecase.resolve() if r else gitfilecase) / 'subdir')


file1_content = "file1 content\n"
file2_content = "file2 content\0"
example_tree = {
    "file1": file1_content,
    "file2": file2_content
}


def _create_test_gitrepo(temp_dir):
    repo = GitRepo(temp_dir)
    repo.init()
    repo.call_git(["add", "."])
    repo.call_git(["commit", "-m", "test commit"])

    hash_keys = tuple(
        repo.call_git(["hash-object", file_name]).strip()
        for file_name in ("file1", "file2")
    )
    return repo, hash_keys


@with_tree(tree=example_tree)
def test_call_git_items(temp_dir=None):
    # check proper handling of separator in call_git_items_
    repo, (hash1, hash2) = _create_test_gitrepo(temp_dir)

    expected_tree_lines = (
        f'100644 blob {hash1}\tfile1',
        f'100644 blob {hash2}\tfile2'
    )

    assert_equal(
        expected_tree_lines,
        tuple(repo.call_git_items_(["ls-tree", "HEAD"]))
    )

    assert_equal(
        expected_tree_lines,
        tuple(repo.call_git_items_(["ls-tree", "-z", "HEAD"], sep="\0"))
    )


@with_tree(tree=example_tree)
def test_call_git_call_git_items_identity(temp_dir=None):
    # Ensure that git_call() and "".join(call_git_items_(..., keep_ends=True))
    # yield the same result and that the result is identical to the file content

    repo, hash_keys = _create_test_gitrepo(temp_dir)
    args = ["cat-file", "-p"]
    for hash_key, content in zip(hash_keys, (file1_content, file2_content)):
        r_item = "".join(repo.call_git_items_(args + [hash_key], keep_ends=True))
        r_no_item = repo.call_git(args, [hash_key])
        assert_equal(r_item, r_no_item)
        assert_equal(r_item, content)
