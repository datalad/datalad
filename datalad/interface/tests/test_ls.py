# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Primarily a smoke test for ls

"""

__docformat__ = 'restructuredtext'

from glob import glob

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.distribution.dataset import Dataset
from ...api import ls
from ...utils import swallow_outputs, swallow_logs, chpwd
from ...tests.utils import assert_equal, assert_in
from ...tests.utils import use_cassette
from ...tests.utils import with_tempfile
from ...tests.utils import with_tree
from datalad.interface.ls import ignored, fs_traverse, _ls_json, AnnexModel
from os.path import exists, lexists, join as opj, abspath, isabs

from datalad.downloaders.tests.utils import get_test_providers

@use_cassette('test_ls_s3')
def test_ls_s3():
    url = 's3://datalad-test0-versioned/'
    with swallow_outputs():
        # just to skip if no credentials
        get_test_providers(url)

    with swallow_outputs() as cmo:
        assert_equal(ls(url), None)  # not output ATM
        assert_in('Bucket info:', cmo.out)
test_ls_s3.tags = ['network']


@with_tempfile
def test_ls_repos(toppath):
    # smoke test pretty much
    GitRepo(toppath + '1', create=True)
    AnnexRepo(toppath + '2', create=True)
    repos = glob(toppath + '*')

    for args in (repos, repos + ["/some/bogus/file"]):
        for recursive in [False, True]:
            # in both cases shouldn't fail
            with swallow_outputs() as cmo:
                ls(args, recursive=recursive)
                assert_equal(len(cmo.out.rstrip().split('\n')), len(args))
                assert_in('[annex]', cmo.out)
                assert_in('[git]', cmo.out)
                assert_in('master', cmo.out)
                if "bogus" in args:
                    assert_in('unknown', cmo.out)


@with_tree(
    tree={'dir': {'file1.txt': '123', 'file2.txt': '456'},
          '.hidden': {'.hidden_file': '121'}})
def test_ignored(topdir):
    # create annex, git repos
    AnnexRepo(opj(topdir, 'annexdir'), create=True)
    GitRepo(opj(topdir, 'gitdir'), create=True)

    # non-git or annex should not be ignored
    assert_equal(ignored(topdir), False)
    # git, annex and hidden nodes should be ignored
    for subdir in ["annexdir", "gitdir", ".hidden"]:
        assert_equal(ignored(opj(topdir, subdir)), True)
    # ignore only hidden nodes(not git or annex repos) flag should work
    assert_equal(ignored(opj(topdir, "annexdir"), only_hidden=True), False)


@with_tree(
    tree={'dir': {'.fgit': {'ab.txt': '123'},
                  'subdir': {'file1.txt': '123', 'file2.txt': '456'},
                  'subgit': {'fgit.txt': '987'}},
          '.hidden': {'.hidden_file': '121'}})
def test_fs_traverse(topdir):
    AnnexRepo(topdir)
    AnnexRepo(opj(topdir, 'annexdir'), create=True)
    GitRepo(opj(topdir, 'gitdir'), create=True)
    GitRepo(opj(topdir, 'dir', 'subgit'), create=True)

    with swallow_logs() as log, swallow_outputs() as cmo:
        fs = fs_traverse(topdir, AnnexRepo(topdir), recursive=True, json='display')
        # fs_traverse logs should contain all not ignored subdirectories
        for subdir in [opj(topdir, "dir"), opj(topdir, 'dir', 'subdir')]:
            assert_in("Directory: " + subdir, log.out)

        # fs_traverse should return a dictionary
        assert_equal(isinstance(fs, dict), True)
        # containing all the toplevel directories including git and annex folders
        assert_equal(([True for item in fs["nodes"] if ('gitdir' and 'annexdir') == item['name']]), [True])
        # fs_traverse stdout contains subdirectory
        assert_in(('file2.txt' and 'dir'), cmo.out)


@with_tree(
    tree={'dir': {'.fgit': {'ab.txt': '123'},
                  'subdir': {'file1.txt': '123', 'file2.txt': '456'},
                  'subgit': {'fgit.txt': '987'}},
          '.hidden': {'.hidden_file': '121'}})
def test_ls_json(topdir):
    annex = AnnexRepo(topdir, create=True)
    ds = Dataset(topdir)
    ds.create_subdataset(opj(topdir, 'annexdir'))
    git = GitRepo(opj(topdir, 'dir', 'subgit'), create=True)
    git.add(opj(topdir, 'dir', 'subgit', 'fgit.txt'), commit=True)
    annex.add(opj(topdir, 'dir', 'subgit'), commit=True)
    annex.add(opj(topdir, 'dir'), commit=True)
    annex.drop(opj(topdir, 'dir', 'subdir', 'file2.txt'), options=['--force'])

    with swallow_logs(), swallow_outputs():
        for all in [True, False]:
            for state in ['file', 'delete']:
                _ls_json(topdir, json=state, all=all, recursive=True)

                # subdataset should have json created and deleted when all=True else not
                assert_equal(exists(opj(topdir, 'annexdir', '.dir.json')), (state == 'file' and all))

                # directories that should have json files created and deleted
                for subdir in ['dir', opj('dir', 'subdir')]:
                    assert_equal(exists(opj(topdir, subdir, '.dir.json')), state == 'file')

                # directories that should not have json files created
                for subdir in ['.hidden', opj('dir', 'subgit')]:
                    assert_equal(exists(opj(topdir, subdir, '.dir.json')), False)


@with_tempfile
def test_ls_noarg(toppath):
    # smoke test pretty much
    AnnexRepo(toppath, create=True)

    # this test is pointless for now and until ls() actually returns
    # something
    with swallow_outputs():
        ls_out = ls(toppath)
        with chpwd(toppath):
            assert_equal(ls_out, ls([]))
            assert_equal(ls_out, ls('.'))

