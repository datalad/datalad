# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for add-archive-content command

"""

__docformat__ = 'restructuredtext'

import os
import tempfile
from glob import glob
from os import unlink
from os.path import (
    basename,
    exists,
)
from os.path import join as opj
from os.path import (
    lexists,
    pardir,
)
from pathlib import Path

from datalad.api import (
    Dataset,
    add_archive_content,
    clean,
)
from datalad.consts import (
    ARCHIVES_SPECIAL_REMOTE,
    DATALAD_SPECIAL_REMOTES_UUIDS,
)
from datalad.support.exceptions import (
    CommandError,
    NoDatasetFound,
)
from datalad.support.external_versions import external_versions
from datalad.tests.utils_pytest import (
    assert_cwd_unchanged,
    assert_equal,
    assert_false,
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_values_cond,
    assert_true,
    create_tree,
    eq_,
    integration,
    known_failure_windows,
    ok_,
    ok_archives_caches,
    ok_file_has_content,
    ok_file_under_git,
    serve_path_via_http,
    skip_if,
    skip_if_adjusted_branch,
    swallow_outputs,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    chpwd,
    find_files,
    get_tempfile_kwargs,
    getpwd,
    on_windows,
    rmtemp,
)

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
def test_add_archive_dirs(path_orig=None, url=None, repo_path=None):
    # change to repo_path
    with chpwd(repo_path):
        # create annex repo
        ds = Dataset(repo_path).create(force=True)
        repo = ds.repo
        # add archive to the repo so we could test
        with swallow_outputs():
            repo.add_url_to_file('1.tar.gz', opj(url, '1.tar.gz'))
        repo.commit("added 1.tar.gz")

        # test with excludes and annex options
        add_archive_content('1.tar.gz',
                            existing='archive-suffix',
                            # Since inconsistent and seems in many cases no
                            # leading dirs to strip, keep them as provided
                            strip_leading_dirs=True,
                            delete=True,
                            leading_dirs_consider=['crcns.*', '1'],
                            leading_dirs_depth=2,
                            use_current_dir=False,
                            exclude='.*__MACOSX.*')  # some junk penetrates

        eq_(repo.get_description(
            uuid=DATALAD_SPECIAL_REMOTES_UUIDS[ARCHIVES_SPECIAL_REMOTE]),
            '[%s]' % ARCHIVES_SPECIAL_REMOTE)

        all_files = sorted(find_files('.'))
        # posixify paths to make it work on Windows as well
        all_files = [Path(file).as_posix() for file in all_files]
        target_files = {
            'CR24A/behaving1/1 f.txt',
            'CR24C/behaving3/3 f.txt',
            'CR24D/behaving2/2 f.txt',
            '.datalad/config',
        }
        eq_(set(all_files), target_files)

        # regression test: the subdir in MACOSX wasn't excluded and its name was
        # getting stripped by leading_dir_len
        # if stripping and exclude didn't work this fails
        assert_false(exists('__MACOSX'))
        # if exclude doesn't work then name of subdir gets stripped by
        # leading_dir_len
        assert_false(exists('c-1_data'))
        # if exclude doesn't work but everything else works this fails
        assert_false(exists('CR24B'))

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


@known_failure_windows
#  apparently fails only sometimes in PY3, but in a way that's common in V6
@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree1args)
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_add_archive_content(path_orig=None, url=None, repo_path=None):
    with chpwd(repo_path):
        # TODO we need to be able to pass path into add_archive_content
        # We could mock but I mean for the API

        # no repo yet
        assert_raises(NoDatasetFound, add_archive_content, "nonexisting.tar.gz")
        ds = Dataset(repo_path).create()
        res = ds.add_archive_content("nonexisting.tar.gz", on_failure='ignore')
        assert_in_results(res, action='add-archive-content',
                          status='impossible')
        repo = ds.repo

        # we can't add a file from outside the repo ATM
        res = ds.add_archive_content(Path(path_orig) / '1.tar.gz',
                                     on_failure='ignore')
        assert_in_results(
            res,
            action='add-archive-content',
            status='impossible',
            type="dataset",
            message="Can not add archive outside of the dataset"
        )

        # Let's add first archive to the repo so we could test
        with swallow_outputs():
            repo.add_url_to_file('1.tar.gz', opj(url, '1.tar.gz'))
            for s in range(1, 5):
                repo.add_url_to_file('%du/1.tar.gz' % s,
                                     opj(url, '%du/1.tar.gz' % s))
            repo.commit("added 1.tar.gz")

        key_1tar = repo.get_file_annexinfo('1.tar.gz')['key']  # will be used in the test later

        def d1_basic_checks():
            ok_(exists('1'))
            ok_file_under_git('1', '1 f.txt', annexed=True)
            ok_file_under_git(opj('1', 'd', '1d'), annexed=True)
            ok_archives_caches(repo_path, 0)

        # and by default it just does it, everything goes to annex
        res = add_archive_content('1.tar.gz')
        assert_in_results(
            res,
            action='add-archive-content',
            status='ok'
        )
        d1_basic_checks()

        # If ran again, should proceed just fine since the content is the same
        # so no changes would be made really
        res = add_archive_content('1.tar.gz')
        assert_in_results(
            res,
            action='add-archive-content',
            status='ok'
        )

        # But that other one carries updated file, so should fail due to
        # overwrite
        res = add_archive_content(Path('1u') / '1.tar.gz',
                                  use_current_dir=True, on_failure='ignore')
        assert_in_results(
            res,
            action='add-archive-content',
            status='error',
        )
        assert_in('exists, but would be overwritten by new file',
                  res[0]['message'])
        # but should do fine if overrides are allowed
        add_archive_content(Path('1u') / '1.tar.gz', existing='overwrite',
                            use_current_dir=True)
        add_archive_content(Path('2u') / '1.tar.gz',
                            existing='archive-suffix', use_current_dir=True)
        add_archive_content(Path('3u') / '1.tar.gz',
                            existing='archive-suffix', use_current_dir=True)
        add_archive_content(Path('4u') / '1.tar.gz',
                            existing='archive-suffix', use_current_dir=True)

        # rudimentary test
        assert_equal(sorted(map(basename, glob(opj(repo_path, '1', '1*')))),
                     ['1 f-1.1.txt', '1 f-1.2.txt', '1 f-1.txt', '1 f.txt'])
        whereis = repo.whereis(glob(opj(repo_path, '1', '1*')))
        # they all must be the same
        assert(all([x == whereis[0] for x in whereis[1:]]))

    # and we should be able to reference it while under subdirectory
    subdir = opj(repo_path, 'subdir')
    with chpwd(subdir, mkdir=True):
        add_archive_content(opj(pardir, '1.tar.gz'), dataset=ds.path,
                            use_current_dir=True)
        d1_basic_checks()
        # or we could keep relative path and also demand to keep the archive prefix
        # while extracting under original (annex root) dir
        add_archive_content(opj(pardir, '1.tar.gz'),
                            dataset=ds.path,
                            add_archive_leading_dir=True)

    with chpwd(opj(repo_path, '1')):
        d1_basic_checks()

    with chpwd(repo_path):
        # test with excludes and renames and annex options
        ds.add_archive_content(
            '1.tar.gz', exclude=['d'], rename=['/ /_', '/^1/2'],
            annex_options="-c annex.largefiles=exclude=*.txt",
            delete=True)
        # no conflicts since new name
        ok_file_under_git('2', '1_f.txt', annexed=False)
        assert_false(exists(opj('2', 'd')))
        assert_false(exists('1.tar.gz'))  # delete was in effect

    # now test ability to extract within subdir
    with chpwd(opj(repo_path, 'd1'), mkdir=True):
        # Let's add first archive to the repo so we could test
        # named the same way but different content
        with swallow_outputs():
            repo.add_url_to_file('d1/1.tar.gz', opj(url, 'd1', '1.tar.gz'))
        repo.commit("added 1.tar.gz in d1")

        def d2_basic_checks():
            ok_(exists('1'))
            ok_file_under_git('1', '2 f.txt', annexed=True)
            ok_file_under_git(opj('1', 'd2', '2d'), annexed=True)
            ok_archives_caches(repo.path, 0)
        add_archive_content('1.tar.gz', dataset=ds.path)
        d2_basic_checks()

    # in manual tests ran into the situation of inability to obtain on a single run
    # a file from an archive which was coming from a dropped key.  I thought it was
    # tested in custom remote tests, but I guess not sufficiently well enough
    repo.drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.get(opj('1', '1 f.txt'))
    ok_archives_caches(repo.path, 1, persistent=True)
    ok_archives_caches(repo.path, 0, persistent=False)

    repo.drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.drop(key_1tar, key=True)  # is available from the URL -- should be kosher
    repo.get(opj('1', '1 f.txt'))  # that what managed to not work

    # TODO: check if persistent archive is there for the 1.tar.gz

    # We should be able to drop everything since available online
    with swallow_outputs():
        clean(dataset=ds)
    repo.drop(key_1tar, key=True)  # is available from the URL -- should be kosher

    ds.drop(opj('1', '1 f.txt'))  # should be all kosher
    ds.get(opj('1', '1 f.txt'))  # and should be able to get it again

    # bug was that dropping didn't work since archive was dropped first
    repo.call_annex(["drop", "--all"])

    # verify that we can't drop a file if archive key was dropped and online archive was removed or changed size! ;)
    repo.get(key_1tar, key=True)
    unlink(opj(path_orig, '1.tar.gz'))
    with assert_raises(CommandError) as e:
        repo.drop(key_1tar, key=True)
        assert_equal(e.kwargs['stdout_json'][0]['success'], False)
        assert_result_values_cond(
            e.kwargs['stdout_json'], 'note',
            lambda x: '(Use --force to override this check, or adjust numcopies.)' in x
        )
    assert exists(opj(repo.path, repo.get_contentlocation(key_1tar)))


@integration
@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree1args)
@serve_path_via_http()
@with_tempfile(mkdir=True)
def test_add_archive_content_strip_leading(path_orig=None, url=None, repo_path=None):
    with chpwd(repo_path):
        ds = Dataset(repo_path).create(force=True)
        repo = ds.repo
        # Let's add first archive to the repo so we could test
        with swallow_outputs():
            repo.add_url_to_file('1.tar.gz', opj(url, '1.tar.gz'))
        repo.commit("added 1.tar.gz")

        add_archive_content('1.tar.gz', strip_leading_dirs=True)
        ok_(not exists('1'))
        ok_file_under_git(ds.path, '1 f.txt', annexed=True)
        ok_file_under_git('d', '1d', annexed=True)
        ok_archives_caches(ds.path, 0)


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(tree={"1.zip": {"dir": {"bar": "blah"}, "foo": "blahhhhh"}})
def test_add_archive_content_zip(repo_path=None):
    ds = Dataset(repo_path).create(force=True)
    with chpwd(repo_path):
        with swallow_outputs():
            ds.save("1.zip", message="add 1.zip")
        add_archive_content("1.zip")
        ok_file_under_git(ds.pathobj / "1" / "foo", annexed=True)
        ok_file_under_git(ds.pathobj / "1" / "dir" / "bar", annexed=True)
        ok_archives_caches(ds.path, 0)


@with_tree(tree={"ds": {"1.tar.gz": {"foo": "abc"}},
                 "notds": {"2.tar.gz": {"bar": "def"}}})
def test_add_archive_content_absolute_path(path=None):
    ds = Dataset(opj(path, "ds")).create(force=True)
    repo = ds.repo
    ds.save("1.tar.gz", message="1.tar.gz")
    abs_tar_gz = opj(path, "ds", "1.tar.gz")
    add_archive_content(abs_tar_gz, dataset=ds)
    ok_file_under_git(opj(path, "ds", "1", "foo"), annexed=True)
    commit_msg = repo.format_commit("%B")
    # The commit message uses relative paths.
    assert_not_in(abs_tar_gz, commit_msg)
    assert_in("1.tar.gz", commit_msg)
    res = add_archive_content(opj(path, "notds", "2.tar.gz"),
                              dataset=ds, on_failure='ignore')

    assert_in_results(
        res,
        action='add-archive-content',
        status='impossible',
        message='Can not add archive outside of the dataset',
    )


@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree4uargs)
def test_add_archive_use_archive_dir(repo_path=None):
    ds = Dataset(repo_path).create(force=True)
    with chpwd(repo_path):
        # Let's add first archive to the repo with default setting
        archive_path = opj('4u', '1.tar.gz')
        # check it gives informative error if archive is not already added
        res = add_archive_content(archive_path, on_failure='ignore')
        message = \
            "Can not add an untracked archive. Run 'datalad save 4u\\1.tar.gz'"\
        if on_windows else \
            "Can not add an untracked archive. Run 'datalad save 4u/1.tar.gz'"
        assert_in_results(
            res,
            action='add-archive-content',
            message=message,
            status='impossible')

        with swallow_outputs():
            ds.save(archive_path)

        ok_archives_caches(ds.path, 0)
        add_archive_content(archive_path, strip_leading_dirs=True,
                            use_current_dir=True)
        ok_(not exists(opj('4u', '1 f.txt')))
        ok_file_under_git(ds.path, '1 f.txt', annexed=True)
        ok_archives_caches(ds.path, 0)

        # and now let's extract under archive dir
        add_archive_content(archive_path, strip_leading_dirs=True)
        ok_file_under_git(ds.path, opj('4u', '1 f.txt'), annexed=True)
        ok_archives_caches(ds.path, 0)

        add_archive_content(opj('4u', 'sub.tar.gz'))
        ok_file_under_git(ds.path, opj('4u', 'sub', '2 f.txt'), annexed=True)
        ok_archives_caches(ds.path, 0)


@with_tree(
    tree={
        'archives': {
            '1.gz': '1',
            '2.xz': '2',
            '3.lzma': '3',
            # TODO: add any other stream compression we might be supporting via 7zip or patool?
        },
    }
)
def test_add_archive_single_file(repo_path=None):
    ds = Dataset(repo_path).create(force=True)
    with chpwd(repo_path):
        archives = glob('archives/*')
        ds.save(archives, message='Added archives')

        for archive in archives:
            archive_name = os.path.splitext(archive)[0]
            archive_content = os.path.basename(archive_name)
            ds.add_archive_content(archive)
            ok_file_has_content(archive_name, archive_content)


class TestAddArchiveOptions():
    # few tests bundled with a common setup/teardown to minimize boiler plate
    # nothing here works on windows, no even teardown(), prevent failure at the
    # origin
    def setup(self):
        repo_path = tempfile.mkdtemp(**get_tempfile_kwargs(prefix="tree"))
        create_tree(
            repo_path,
            {'1.tar': {'file.txt': 'load',
                       '1.dat': 'load2'}})
        self.ds = ds = Dataset(repo_path)
        ds.create(force=True)
        self.annex = ds.repo
        # Let's add first archive to the annex so we could test
        ds.save('1.tar', message="added 1.tar")

    def teardown(self):
        # so we close any outstanding batch process etc
        self.annex.precommit()
        rmtemp(self.ds.path)

    def test_add_delete(self):
        # To test that .tar gets removed
        self.ds.add_archive_content('1.tar', strip_leading_dirs=True,
                                    delete=True)
        assert_false(lexists(self.ds.pathobj / '1.tar'))

    # git-annex regression
    # https://git-annex.branchable.com/bugs/regression__58___annex_add_of_moved_file_errors_out/
    @skip_if(
        '10.20220525' <= external_versions['cmd:annex'] < '10.20220706',  # approx when was fixed
        msg="buggy git-annex release"
    )
    def test_add_archive_leading_dir(self):
        import os
        os.mkdir(self.ds.pathobj / 'sub')
        f123 = Path('sub') / '123.tar'
        Path(self.ds.pathobj / '1.tar').rename(self.ds.pathobj / Path(f123))
        self.annex.remove('1.tar', force=True)
        self.ds.save(message="renamed")

        self.ds.add_archive_content(
            f123,
            add_archive_leading_dir=True,
            strip_leading_dirs=True
        )

        ok_file_under_git(self.ds.path,
                          str(Path('sub') / '123' / 'file.txt'),
                          annexed=True)

    # https://github.com/datalad/datalad/issues/6187
    @skip_if_adjusted_branch
    def test_add_delete_after_and_drop(self):
        # To test that .tar gets removed
        # but that new stuff was added to annex repo.  We know the key since
        # default backend and content remain the same
        key1 = 'MD5E-s5--db87ebcba59a8c9f34b68e713c08a718.dat'
        repo = self.ds.repo
        # previous state of things:
        prev_files = list(find_files('.*', self.ds.path))
        assert_equal(repo.whereis(key1, key=True, output='full'), {})

        commits_prior = list(repo.get_branch_commits_('git-annex'))
        self.ds.add_archive_content('1.tar',
                                    strip_leading_dirs=True, delete_after=True)
        commits_after = list(repo.get_branch_commits_('git-annex'))
        # There should be a single commit for all additions +1 to initiate
        # datalad-archives gh-1258
        # If faking dates, there should be another +1 because
        # annex.alwayscommit isn't set to false.
        assert_equal(len(commits_after),
                     # We expect one more when faking dates because
                     # annex.alwayscommit isn't set to false.
                     len(commits_prior) + 2 + repo.fake_dates_enabled)
        assert_equal(prev_files, list(find_files('.*', self.ds.path)))
        w = repo.whereis(key1, key=True, output='full')
        assert_equal(len(w), 2)  # in archive, and locally since we didn't drop

        # Let's now do the same but also drop content
        self.ds.add_archive_content('1.tar',
                                    strip_leading_dirs=True, delete_after=True,
                                    drop_after=True)
        assert_equal(prev_files, list(find_files('.*', self.ds.path)))
        w = repo.whereis(key1, key=True, output='full')
        assert_equal(len(w), 1)  # in archive

        # there should be no .datalad temporary files hanging around
        self.assert_no_trash_left_behind()

    def test_add_delete_after_and_drop_subdir(self=None):
        os.mkdir(opj(self.annex.path, 'subdir'))
        mv_out = self.annex.call_git(
            ['mv', '1.tar', 'subdir']
        )
        self.annex.commit("moved into subdir")
        with chpwd(self.annex.path):
            # was failing since deleting without considering if tarball
            # was extracted in that tarball directory
            commits_prior_master = list(self.annex.get_branch_commits_())
            commits_prior = list(self.annex.get_branch_commits_('git-annex'))
            add_out = self.ds.add_archive_content(
                opj('subdir', '1.tar'),
                delete_after=True,
                drop_after=True)
            assert_repo_status(self.annex.path)
            if not self.annex.is_managed_branch():
                # whole counting logic here is ignorant of adjusted branches
                commits_after_master = list(self.annex.get_branch_commits_())
                commits_after = list(self.annex.get_branch_commits_('git-annex'))
                # There should be a single commit for all additions +1 to
                # initiate datalad-archives gh-1258.  If faking dates,
                # there should be another +1 because annex.alwayscommit
                # isn't set to false.
                assert_equal(len(commits_after),
                             len(commits_prior) + 2 + self.annex.fake_dates_enabled)
                assert_equal(len(commits_after_master), len(commits_prior_master))
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
            assert_repo_status(self.annex.path, untracked=['dummy.txt'])
            assert_equal(len(list(self.annex.get_branch_commits_())),
                         len(commits_prior_master))

            # there should be no .datalad temporary files hanging around
            self.assert_no_trash_left_behind()

    def assert_no_trash_left_behind(self):
        assert_equal(
            list(find_files(r'\.datalad..*', self.annex.path, exclude="config",
                            dirs=True)),
            []
        )

    def test_override_existing_under_git(self):
        create_tree(self.ds.path, {'1.dat': 'load2'})
        self.ds.save('1.dat', to_git=True, message='added to git')
        self.ds.add_archive_content(
            '1.tar', strip_leading_dirs=True,
        )
        # and we did not bother adding it to annex (for now) -- just skipped
        # since we have it and it is the same
        ok_file_under_git(self.ds.path, '1.dat', annexed=False)

        # but if we say 'overwrite' -- we would remove and replace
        self.ds.add_archive_content(
            '1.tar', strip_leading_dirs=True, delete=True
            , existing='overwrite'
        )
        ok_file_under_git(self.ds.path, '1.dat', annexed=True)
