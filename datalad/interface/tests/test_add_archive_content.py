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

from os.path import exists, join as opj, pardir, basename
from glob import glob

from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_tempfile, assert_in
from ...tests.utils import assert_equal
from ...tests.utils import assert_false
from ...tests.utils import ok_archives_caches

from ...support.annexrepo import AnnexRepo
from ...support.exceptions import FileNotInRepositoryError
from ...tests.utils import with_tree, serve_path_via_http, ok_file_under_git, swallow_outputs
from ...utils import chpwd, getpwd

from ...api import add_archive_content


# within top directory
# archive is in subdirectory -- adding in the same (or different) directory

tree1args = dict(
    tree=(
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), )),
        ('d1', (('1.tar.gz', (
                    ('2 f.txt', '2 f load'),
                    ('d2', (
                        ('2d', ''),)
                     )),),),),
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
        repo.annex_addurls([opj(url, '1.tar.gz')], options=["--pathdepth", "-1"])
    repo.git_commit("added 1.tar.gz")

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

    # If ran again, should fail due to override=False
    with assert_raises(RuntimeError) as cme:
        add_archive_content('1.tar.gz')
    # TODO: somewhat not precise since we have two possible "already exists"
    # -- in caching and overwrite check
    assert_in("already exists", str(cme.exception))
    # but should do fine if overrides are allowed
    add_archive_content('1.tar.gz', existing='overwrite')
    d1_basic_checks()
    add_archive_content('1.tar.gz', existing='archive-suffix')
    add_archive_content('1.tar.gz', existing='archive-suffix')
    # rudimentary test
    assert_equal(sorted(map(basename, glob(opj(repo_path, '1', '1*')))),
                 ['1 f.txt', '1 f.txt-1', '1 f.txt-1.1'])
    whereis = repo.annex_whereis(glob(opj(repo_path, '1', '1*')))
    # they all must be the same
    assert(all([x==whereis[0] for x in whereis[1:]]))

    # and we should be able to reference it while under subdirectory
    subdir = opj(repo_path, 'subdir')
    with chpwd(subdir, mkdir=True):
        add_archive_content(opj(pardir, '1.tar.gz'))
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
            repo.annex_addurls([opj(url, 'd1', '1.tar.gz')], options=["--pathdepth", "-1"],
                               cwd=getpwd())  # invoke under current subdir
        repo.git_commit("added 1.tar.gz in d1")

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
    repo.annex_drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.annex_get(opj('1', '1 f.txt'))
    ok_archives_caches(repo.path, 1, persistent=True)
    ok_archives_caches(repo.path, 0, persistent=False)

    repo.annex_drop(opj('1', '1 f.txt'))  # should be all kosher
    repo.annex_drop(key_1tar, options=['--key'])  # is available from the URL -- should be kosher
    repo.annex_get(opj('1', '1 f.txt'))  # that what managed to not work

    # TODO: check if persistent archive is there for the 1.tar.gz

    chpwd(orig_pwd)  # just to avoid warnings ;)


# looking for the future tagging of lengthy tests
test_add_archive_content.tags = ['integration']
