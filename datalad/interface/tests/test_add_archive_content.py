# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for add-archive-content command

"""

__docformat__ = 'restructuredtext'

import logging
import os
from os import unlink
from os.path import exists, join as opj, pardir, basename, lexists
from glob import glob

from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_tempfile, assert_in
from ...tests.utils import assert_equal, assert_not_equal
from ...tests.utils import assert_false
from ...tests.utils import assert_true
from ...tests.utils import ok_archives_caches
from ...tests.utils import SkipTest

from ...support.annexrepo import AnnexRepo
from ...support.exceptions import FileNotInRepositoryError
from ...support.exceptions import CommandError
from ...tests.utils import with_tree, serve_path_via_http, ok_file_under_git, swallow_outputs
from ...tests.utils import swallow_logs
from ...utils import chpwd, getpwd, rmtemp
from ...utils import find_files
from ...utils import rmtree
from datalad.log import lgr
from ...api import add_archive_content, clean
from datalad.support.external_versions import external_versions
from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
from datalad.consts import ARCHIVES_SPECIAL_REMOTE

from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_clean_git

treeargs = dict(
    tree=(
        ('1.tar.gz', (
            ('crcns_pfc-1_data', (('CR24A', (
                                    ('behaving1', {'1 f.txt': '1 f load'}),)),)),
            ('crcns_pfc-1_data', (('CR24C', (
                                    ('behaving3', {'3 f.txt': '3 f load'}),)),)),
            ('crcns_pfc-1_data', (('CR24D', (
                                    ('behaving2', {'2 f.txt': '2 f load'}),)),)),
            ('__MACOSX', (('crcns_pfc-2_data', (
                                    ('CR24B', (
                                        ('behaving2', {'2 f.txt': '2 f load'}),)),)
                           ),)),
            ('crcns_pfc-2_data', (('__MACOSX', (
                                    ('CR24E', (
                                        ('behaving2', {'2 f.txt': '2 f load'}),)),)
                                   ),)),

        )),
    )
)


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**treeargs)
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_add_archive_dirs(path_orig, url, repo_path):
    # change to repo_path
    chpwd(repo_path)

    # create annex repo
    repo = AnnexRepo(repo_path, create=True, direct=False)

    # add archive to the repo so we could test
    with swallow_outputs():
        repo.add_urls([opj(url, '1.tar.gz')], options=["--pathdepth", "-1"])
    repo.commit("added 1.tar.gz")

    # test with excludes and annex options
    add_archive_content('1.tar.gz',
                        existing='archive-suffix',
                        # Since inconsistent and seems in many cases no leading dirs to strip, keep them as provided
                        strip_leading_dirs=True,
                        delete=True,
                        leading_dirs_consider=['crcns.*', '1'],
                        leading_dirs_depth=2,
                        use_current_dir=False,
                        exclude='.*__MACOSX.*')  # some junk penetrates

    if external_versions['cmd:annex'] >= '6.20170208':
        # should have fixed remotes
        eq_(repo.get_description(uuid=DATALAD_SPECIAL_REMOTES_UUIDS[ARCHIVES_SPECIAL_REMOTE]),
            '[%s]' % ARCHIVES_SPECIAL_REMOTE)

    all_files = sorted(find_files('.'))
    target_files = {
        './CR24A/behaving1/1 f.txt',
        './CR24C/behaving3/3 f.txt',
        './CR24D/behaving2/2 f.txt',
    }
    eq_(set(all_files), target_files)

    # regression test: the subdir in MACOSX wasn't excluded and its name was getting stripped by leading_dir_len
    assert_false(exists('__MACOSX'))  # if stripping and exclude didn't work this fails
    assert_false(exists('c-1_data'))  # if exclude doesn't work then name of subdir gets stripped by leading_dir_len
    assert_false(exists('CR24B'))     # if exclude doesn't work but everything else works this fails


# within top directory
# archive is in subdirectory -- adding in the same (or different) directory

tree1args = dict(
    tree=(
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), )),
        ('1u', {
          '1.tar.gz': { # updated file content
             '1 f.txt': '1 f load1'
          }}),
        ('2u', {  # updated file content
          '1.tar.gz': {
             '1 f.txt': '1 f load2'
          }}),
        ('3u', {  # updated file content
          '1.tar.gz': {
             '1 f.txt': '1 f load3'
          }}),
        ('4u', {  # updated file content
          '1.tar.gz': {
             '1 f.txt': '1 f load4'
          }}),
        ('d1', (('1.tar.gz', (
                    ('2 f.txt', '2 f load'),
                    ('d2', (
                        ('2d', ''),)
                     )),),),),
    )
)

tree4uargs = dict(
    tree=(
        ('4u', {  # updated file content
          '1.tar.gz': {
             '1 f.txt': '1 f load4',
              'sub.tar.gz': {
                  '2 f.txt': '2 f'
              }
        }}),
    )
)


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree1args)
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_add_archive_content(path_orig, url, repo_path):
    direct = False  # TODO: test on undirect, but too long ATM
    orig_pwd = getpwd()
    chpwd(repo_path)
    # TODO we need to be able to pass path into add_archive_content
    # We could mock but I mean for the API
    assert_raises(RuntimeError, add_archive_content, "nonexisting.tar.gz") # no repo yet

    repo = AnnexRepo(repo_path, create=True, direct=direct)
    assert_raises(ValueError, add_archive_content, "nonexisting.tar.gz")
    # we can't add a file from outside the repo ATM
    assert_raises(FileNotInRepositoryError, add_archive_content, opj(path_orig, '1.tar.gz'))

    # Let's add first archive to the repo so we could test
    with swallow_outputs():
        repo.add_urls([opj(url, '1.tar.gz')], options=["--pathdepth", "-1"])
        for s in range(1, 5):
            repo.add_urls([opj(url, '%du/1.tar.gz' % s)], options=["--pathdepth", "-2"])
    repo.commit("added 1.tar.gz")

    key_1tar = repo.get_file_key('1.tar.gz')  # will be used in the test later

    def d1_basic_checks():
        ok_(exists('1'))
        ok_file_under_git('1', '1 f.txt', annexed=True)
        ok_file_under_git(opj('1', 'd', '1d'), annexed=True)
        ok_archives_caches(repo_path, 0)

    # and by default it just does it, everything goes to annex
    repo_ = add_archive_content('1.tar.gz')
    eq_(repo.path, repo_.path)
    d1_basic_checks()

    # If ran again, should proceed just fine since the content is the same so no changes would be made really
    add_archive_content('1.tar.gz')

    # But that other one carries updated file, so should fail due to overwrite
    with assert_raises(RuntimeError) as cme:
        add_archive_content(opj('1u', '1.tar.gz'), use_current_dir=True)

    # TODO: somewhat not precise since we have two possible "already exists"
    # -- in caching and overwrite check
    assert_in("already exists", str(cme.exception))
    # but should do fine if overrides are allowed
    add_archive_content(opj('1u', '1.tar.gz'), existing='overwrite', use_current_dir=True)
    add_archive_content(opj('2u', '1.tar.gz'), existing='archive-suffix', use_current_dir=True)
    add_archive_content(opj('3u', '1.tar.gz'), existing='archive-suffix', use_current_dir=True)
    add_archive_content(opj('4u', '1.tar.gz'), existing='archive-suffix', use_current_dir=True)

    # rudimentary test
    assert_equal(sorted(map(basename, glob(opj(repo_path, '1', '1*')))),
                 ['1 f-1.1.txt', '1 f-1.2.txt', '1 f-1.txt', '1 f.txt'])
    whereis = repo.whereis(glob(opj(repo_path, '1', '1*')))
    # they all must be the same
    assert(all([x == whereis[0] for x in whereis[1:]]))

    # and we should be able to reference it while under subdirectory
    subdir = opj(repo_path, 'subdir')
    with chpwd(subdir, mkdir=True):
        add_archive_content(opj(pardir, '1.tar.gz'), use_current_dir=True)
        d1_basic_checks()
        # or we could keep relative path and also demand to keep the archive prefix
        # while extracting under original (annex root) dir
        add_archive_content(opj(pardir, '1.tar.gz'), add_archive_leading_dir=True)
    with chpwd('1'):
        d1_basic_checks()

    # test with excludes and renames and annex options
    add_archive_content(
        '1.tar.gz', exclude=['d'], rename=['/ /_', '/^1/2'],
        annex_options="-c annex.largefiles=exclude=*.txt",
        delete=True)
    # no conflicts since new name
    ok_file_under_git('2', '1_f.txt', annexed=False)
    assert_false(exists(opj('2', 'd')))
    assert_false(exists('1.tar.gz'))  # delete was in effect

    # now test ability to extract within subdir
    with chpwd('d1', mkdir=True):
        # Let's add first archive to the repo so we could test
        # named the same way but different content
        with swallow_outputs():
            repo.add_urls([opj(url, 'd1', '1.tar.gz')], options=["--pathdepth", "-1"],
                          cwd=getpwd())  # invoke under current subdir
        repo.commit("added 1.tar.gz in d1")

        def d2_basic_checks():
            ok_(exists('1'))
            ok_file_under_git('1', '2 f.txt', annexed=True)
            ok_file_under_git(opj('1', 'd2', '2d'), annexed=True)
            ok_archives_caches(repo.path, 0)

        add_archive_content('1.tar.gz')
        d2_basic_checks()

    # in manual tests ran into the situation of inability to obtain on a single run
    # a file from an archive which was coming from a dropped key.  I thought it was
    # tested in custom remote tests, but I guess not sufficiently well enough
    repo.drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.get(opj('1', '1 f.txt'))
    ok_archives_caches(repo.path, 1, persistent=True)
    ok_archives_caches(repo.path, 0, persistent=False)

    repo.drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.drop(key_1tar, options=['--key'])  # is available from the URL -- should be kosher
    repo.get(opj('1', '1 f.txt'))  # that what managed to not work

    # TODO: check if persistent archive is there for the 1.tar.gz

    # We should be able to drop everything since available online
    with swallow_outputs():
        clean(dataset=repo.path)
    repo.drop(key_1tar, options=['--key'])  # is available from the URL -- should be kosher
    chpwd(orig_pwd)  # just to avoid warnings ;)  move below whenever SkipTest removed

    repo.drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.get(opj('1', '1 f.txt'))  # and should be able to get it again

    # bug was that dropping didn't work since archive was dropped first
    repo._annex_custom_command([], ["git", "annex", "drop", "--all"])

    # verify that we can't drop a file if archive key was dropped and online archive was removed or changed size! ;)
    repo.get(key_1tar, options=['--key'])
    unlink(opj(path_orig, '1.tar.gz'))
    res = repo.drop(key_1tar, options=['--key'])
    assert_equal(res['success'], False)
    assert_equal(res['note'], '(Use --force to override this check, or adjust numcopies.)')
    assert exists(opj(repo.path, repo.get_contentlocation(key_1tar)))


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree1args)
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_add_archive_content_strip_leading(path_orig, url, repo_path):
    direct = False  # TODO: test on undirect, but too long ATM
    orig_pwd = getpwd()
    chpwd(repo_path)

    repo = AnnexRepo(repo_path, create=True, direct=direct)

    # Let's add first archive to the repo so we could test
    with swallow_outputs():
        repo.add_urls([opj(url, '1.tar.gz')], options=["--pathdepth", "-1"])
    repo.commit("added 1.tar.gz")

    add_archive_content('1.tar.gz', strip_leading_dirs=True)
    ok_(not exists('1'))
    ok_file_under_git(repo.path, '1 f.txt', annexed=True)
    ok_file_under_git('d', '1d', annexed=True)
    ok_archives_caches(repo.path, 0)

    chpwd(orig_pwd)  # just to avoid warnings ;)

# looking for the future tagging of lengthy tests
test_add_archive_content.tags = ['integration']


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree4uargs)
def test_add_archive_use_archive_dir(repo_path):
    direct = False  # TODO: test on undirect, but too long ATM
    repo = AnnexRepo(repo_path, create=True, direct=direct)
    with chpwd(repo_path):
        # Let's add first archive to the repo with default setting
        archive_path = opj('4u', '1.tar.gz')
        with swallow_outputs():
            repo.add(archive_path)
        repo.commit("added 1.tar.gz")

        ok_archives_caches(repo.path, 0)
        add_archive_content(archive_path, strip_leading_dirs=True, use_current_dir=True)
        ok_(not exists(opj('4u', '1 f.txt')))
        ok_file_under_git(repo.path, '1 f.txt', annexed=True)
        ok_archives_caches(repo.path, 0)

        # and now let's extract under archive dir
        add_archive_content(archive_path, strip_leading_dirs=True)
        ok_file_under_git(repo.path, opj('4u', '1 f.txt'), annexed=True)
        ok_archives_caches(repo.path, 0)

        add_archive_content(opj('4u', 'sub.tar.gz'))
        ok_file_under_git(repo.path, opj('4u', 'sub', '2 f.txt'), annexed=True)
        ok_archives_caches(repo.path, 0)


class TestAddArchiveOptions():

    # few tests bundled with a common setup/teardown to minimize boiler plate
    @with_tree(tree={'1.tar': {'file.txt': 'load',
                               '1.dat': 'load2'}},
               delete=False)
    def setup(self, repo_path):
        self.pwd = getpwd()
        direct = False  # TODO: test on undirect, but too long ATM
        self.annex = annex = AnnexRepo(repo_path, create=True, direct=direct)
        # Let's add first archive to the annex so we could test
        annex.add('1.tar')
        annex.commit(msg="added 1.tar")

    def teardown(self):
        assert_equal(self.pwd, getpwd())
        rmtemp(self.annex.path)

    def test_add_delete(self):
        # To test that .tar gets removed
        add_archive_content('1.tar', annex=self.annex, strip_leading_dirs=True, delete=True)
        assert_false(lexists(opj(self.annex.path, '1.tar')))

    def test_add_archive_leading_dir(self):
        import os
        os.mkdir(opj(self.annex.path, 'sub'))
        f123 = opj('sub', '123.tar')
        os.rename(opj(self.annex.path, '1.tar'), opj(self.annex.path, f123))
        self.annex.remove('1.tar', force=True)
        self.annex.add(f123)
        self.annex.commit(msg="renamed")
        add_archive_content(
            f123,
            annex=self.annex,
            add_archive_leading_dir=True,
            strip_leading_dirs=True
        )
        ok_file_under_git(self.annex.path, opj('sub', '123', 'file.txt'), annexed=True)

    def test_add_delete_after_and_drop(self):
        # To test that .tar gets removed
        # but that new stuff was added to annex repo.  We know the key since default
        # backend and content remain the same
        key1 = 'SHA256E-s5--16d3ad1974655987dd7801d70659990b89bfe7e931a0a358964e64e901761cc0.dat'

        # previous state of things:
        prev_files = list(find_files('.*', self.annex.path))
        with assert_raises(Exception), \
                swallow_logs():
            self.annex.whereis(key1, key=True, output='full')
        commits_prior = list(self.annex.get_branch_commits('git-annex'))
        add_archive_content('1.tar', annex=self.annex, strip_leading_dirs=True, delete_after=True)
        commits_after = list(self.annex.get_branch_commits('git-annex'))
        # There should be a single commit for all additions +1 to initiate datalad-archives gh-1258
        assert_equal(len(commits_after), len(commits_prior) + 2)
        assert_equal(prev_files, list(find_files('.*', self.annex.path)))
        w = self.annex.whereis(key1, key=True, output='full')
        assert_equal(len(w), 2)  # in archive, and locally since we didn't drop

        # Let's now do the same but also drop content
        add_archive_content('1.tar', annex=self.annex, strip_leading_dirs=True, delete_after=True,
                            drop_after=True)
        assert_equal(prev_files, list(find_files('.*', self.annex.path)))
        w = self.annex.whereis(key1, key=True, output='full')
        assert_equal(len(w), 1)  # in archive

        # there should be no .datalad temporary files hanging around
        self.assert_no_trash_left_behind()

    def test_add_delete_after_and_drop_subdir(self):
        os.mkdir(opj(self.annex.path, 'subdir'))
        mv_out = self.annex._git_custom_command(
            [],
            ['git', 'mv', '1.tar', 'subdir']
        )
        self.annex.commit("moved into subdir")
        with chpwd(self.annex.path):
            # was failing since deleting without considering if tarball
            # was extracted in that tarball directory
            commits_prior_master = list(self.annex.get_branch_commits())
            commits_prior = list(self.annex.get_branch_commits('git-annex'))
            add_out = add_archive_content(
                opj('subdir', '1.tar'),
                delete_after=True,
                drop_after=True)
            ok_clean_git(self.annex.path)
            commits_after_master = list(self.annex.get_branch_commits())
            commits_after = list(self.annex.get_branch_commits('git-annex'))
            # There should be a single commit for all additions +1 to
            # initiate datalad-archives gh-1258
            assert_equal(len(commits_after), len(commits_prior) + 2)
            assert_equal(len(commits_after_master), len(commits_prior_master))
            assert(add_out is self.annex)
            # there should be no .datalad temporary files hanging around
            self.assert_no_trash_left_behind()

            # and if we add some untracked file, redo, there should be no changes
            # to master and file should remain not committed
            create_tree(self.annex.path, {'dummy.txt': '123'})
            assert_true(self.annex.dirty)  # untracked file
            add_out = add_archive_content(
                opj('subdir', '1.tar'),
                delete_after=True,
                drop_after=True,
                allow_dirty=True)
            ok_clean_git(self.annex.path, untracked=['dummy.txt'])
            assert_equal(len(list(self.annex.get_branch_commits())),
                         len(commits_prior_master))

            # there should be no .datalad temporary files hanging around
            self.assert_no_trash_left_behind()

    def assert_no_trash_left_behind(self):
        assert_equal(
            list(find_files('\.datalad..*', self.annex.path, dirs=True)),
            []
        )

    def test_override_existing_under_git(self):
        create_tree(self.annex.path, {'1.dat': 'load2'})
        self.annex.add('1.dat', git=True)
        self.annex.commit('added to git')
        add_archive_content(
            '1.tar', annex=self.annex, strip_leading_dirs=True,
        )
        # and we did not bother adding it to annex (for now) -- just skipped
        # since we have it and it is the same
        ok_file_under_git(self.annex.path, '1.dat', annexed=False)

        # but if we say 'overwrite' -- we would remove and replace
        add_archive_content(
            '1.tar', annex=self.annex, strip_leading_dirs=True, delete=True
            , existing='overwrite'
        )
        ok_file_under_git(self.annex.path, '1.dat', annexed=True)
