# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class AnnexRepo

"""

import os

from git.exc import GitCommandError
from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_in, assert_not_in

from datalad.support.annexrepo import AnnexRepo, kwargs_to_options
from datalad.tests.utils import with_tempfile, with_testrepos, \
    assert_cwd_unchanged, ignore_nose_capturing_stdout, on_windows,\
    ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, with_tree,\
    get_most_obscure_supported_name, ok_clean_git
from datalad.support.exceptions import CommandNotAvailableError,\
    FileInGitError, FileNotInAnnexError, CommandError

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_instance_from_clone(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise GitCommandError since git will notice
    # there's already a git-repo at that path and therefore can't clone to `dst`
    with swallow_logs() as cm:
        assert_raises(GitCommandError, AnnexRepo, dst, src)
        assert("already exists" in cm.out)


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=['network'])
@with_tempfile
def test_AnnexRepo_get(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = os.path.join(dst, testfile)
    assert_false(ar.file_has_content("test-annex.dat"))
    ar.annex_get(testfile)
    assert_true(ar.file_has_content("test-annex.dat"))

    f = open(testfile_abs, 'r')
    assert_equal(f.readlines(), ['123\n'],
                 "test-annex.dat's content doesn't match.")


@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_crippled_filesystem(src, dst):
    # TODO: This test is rudimentary, since platform does not really determine
    # the filesystem. For now this should work for the buildbots.
    # Nevertheless: Find a better way to test it.

    ar = AnnexRepo(dst, src)
    if on_windows:
        assert_true(ar.is_crippled_fs(),
                    "Detected non-crippled filesystem on windows.")
    else:
        assert_false(ar.is_crippled_fs(),
                     "Detected crippled filesystem on non-windows.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
def test_AnnexRepo_is_direct_mode(path):

    ar = AnnexRepo(path)
    dm = ar.is_direct_mode()
    if on_windows:
        assert_true(dm,
                    "AnnexRepo.is_direct_mode() returned false on windows.")
    else:
        assert_false(dm,
                     "AnnexRepo.is_direct_mode() returned true on non-windows")
    # Note: In fact this test isn't totally correct, since you always can
    # switch to direct mode. So not being on windows doesn't necessarily mean
    # we are in indirect mode. But how to obtain a "ground truth" to test
    # against, without making test of is_direct_mode() dependent on
    # set_direct_mode() and vice versa?


@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_set_direct_mode(src, dst):

    ar = AnnexRepo(dst, src)
    ar.set_direct_mode(True)
    assert_true(ar.is_direct_mode(), "Switching to direct mode failed.")
    if ar.is_crippled_fs():
        assert_raises(CommandNotAvailableError, ar.set_direct_mode, False)
        assert_true(ar.is_direct_mode(),
            "Indirect mode on crippled fs detected. Shouldn't be possible.")
    else:
        ar.set_direct_mode(False)
        assert_false(ar.is_direct_mode(), "Switching to indirect mode failed.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_annex_add(src, annex_path):

    ar = AnnexRepo(annex_path, src)

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(annex_path, filename)
    f = open(filename_abs, 'w')
    f.write("What to write?")
    f.close()
    ar.annex_add(filename)
    if not ar.is_direct_mode():
        assert_true(os.path.islink(filename_abs),
                    "Annexed file is not a link.")
    else:
        assert_false(os.path.islink(filename_abs),
                     "Annexed file is link in direct mode.")
    key = ar.get_file_key(filename)
    assert_false(key == '')
    # could test for the actual key, but if there's something
    # and no exception raised, it's fine anyway.


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):

    ar = AnnexRepo(annex_path, src)
    ar.set_direct_mode(True)
    ok_clean_git_annex_proxy(path=annex_path)


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_get_file_key(src, annex_path):

    ar = AnnexRepo(annex_path, src)

    # test-annex.dat should return the correct key:
    assert_equal(
        ar.get_file_key("test-annex.dat"),
        'SHA256E-s4--181210f8f9c779c26da1d9b2075bde0127302ee0e3fca38c9a83f5b1dd8e5d3b.dat')

    # test.dat is actually in git
    # should raise Exception; also test for polymorphism
    assert_raises(IOError, ar.get_file_key, "test.dat")
    assert_raises(FileNotInAnnexError, ar.get_file_key, "test.dat")
    assert_raises(FileInGitError, ar.get_file_key, "test.dat")

    # filenotpresent.wtf doesn't even exist
    assert_raises(IOError, ar.get_file_key, "filenotpresent.wtf")


@with_testrepos(flavors=['network'])
@with_tempfile
def test_AnnexRepo_file_has_content(src, annex_path):

    ar = AnnexRepo(annex_path, src)
    testfiles = ["test-annex.dat", "test.dat"]
    assert_equal(ar.file_has_content(testfiles), [False, False])

    ar.annex_get("test-annex.dat")
    assert_equal(ar.file_has_content(testfiles), [True, False])
    assert_equal(ar.file_has_content(testfiles[:1]), [True])

    assert_equal(ar.file_has_content(testfiles + ["bogus.txt"]),
                 [True, False, False])

    assert_false(ar.file_has_content("bogus.txt"))
    assert_true(ar.file_has_content("test-annex.dat"))


def test_AnnexRepo_options_decorator():

    @kwargs_to_options
    def decorated(self, whatever, options=[]):
        return options

    assert_equal(decorated(1, 2, someoption='first', someotheroption='second'),
                 [' --someoption=first', ' --someotheroption=second'])


@assert_cwd_unchanged
@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_annex_add_to_git(src, dst):

    ar = AnnexRepo(dst, src)

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")

    assert_raises(IOError, ar.get_file_key, filename)
    ar.annex_add_to_git(filename)
    assert_in(filename, ar.get_indexed_files())


@with_testrepos(flavors=local_flavors)
@with_tempfile
def test_AnnexRepo_web_remote(src, dst):

    ar = AnnexRepo(dst, src)

    testurl = 'http://datalad.org/pages/about.html'
    testfile = 'datalad.org_pages_about.html'

    # get the file from remote
    ar.annex_addurls([testurl])
    l = ar.annex_whereis(testfile)
    assert_in('web', l)
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # remove the remote
    ar.annex_rmurl(testfile, testurl)
    l = ar.annex_whereis(testfile)
    assert_not_in('web', l)
    assert_equal(len(l), 1)

    # now only 1 copy; drop should fail
    try:
        ar.annex_drop(testfile)
    except CommandError, e:
        assert_equal(e.code, 1)
        assert_in('Could only verify the '
                  'existence of 0 out of 1 necessary copies', e.stdout)
        failed = True

    assert_true(failed)

    # read the url using different method
    ar.annex_addurl_to_file(testfile, testurl)
    l = ar.annex_whereis(testfile)
    assert_in('web', l)
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # 2 known copies now; drop should succeed
    ar.annex_drop(testfile)
    l = ar.annex_whereis(testfile)
    assert_in('web', l)
    assert_equal(len(l), 1)
    assert_false(ar.file_has_content(testfile))

# TODO:
#def annex_initremote(self, name, options):
#def annex_enableremote(self, name):


