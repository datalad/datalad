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

import gc
from git.exc import GitCommandError
from six import PY3

from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_in, assert_not_in
from nose import SkipTest

from ..support.annexrepo import AnnexRepo, kwargs_to_options, GitRepo
from ..support.exceptions import CommandNotAvailableError, \
    FileInGitError, FileNotInAnnexError, CommandError
from ..cmd import Runner
from .utils import *


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
@with_testrepos(flavors=local_testrepo_flavors)
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    GitRepo(path)
    assert_raises(RuntimeError, AnnexRepo, path, create=False)

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
    ok_annex_get(ar, testfile)

    f = open(testfile_abs, 'r')
    assert_equal(f.readlines(), ['123\n'],
                 "test-annex.dat's content doesn't match.")


@assert_cwd_unchanged
@with_testrepos
@with_tempfile
def test_AnnexRepo_crippled_filesystem(src, dst):

    ar = AnnexRepo(dst, src)

    # fake git-annex entries in .git/config:
    writer = ar.repo.config_writer()
    writer.set_value("annex", "crippledfilesystem", True)
    writer.release()
    assert_true(ar.is_crippled_fs())
    writer.set_value("annex", "crippledfilesystem", False)
    writer.release()
    assert_false(ar.is_crippled_fs())
    # since we can't remove the entry, just rename it to fake its absence:
    writer.rename_section("annex", "removed")
    writer.set_value("annex", "something", "value")
    writer.release()
    assert_false(ar.is_crippled_fs())


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
def test_AnnexRepo_is_direct_mode(path):

    ar = AnnexRepo(path)
    dm = ar.is_direct_mode()

    # by default annex should be in direct mode on crippled filesystem and
    # on windows:
    if ar.is_crippled_fs() or on_windows:
        assert_true(dm)
    else:
        assert_false(dm)


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
@with_testrepos(flavors=local_testrepo_flavors)
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
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):
    ar = AnnexRepo(annex_path, src)
    ar.set_direct_mode(True)
    ok_clean_git_annex_proxy(path=annex_path)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
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

    ok_annex_get(ar, "test-annex.dat")
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

    # Order is not guaranteed so use sets
    assert_equal(set(decorated(1, 2, someoption='first', someotheroption='second')),
                 {' --someoption=first', ' --someotheroption=second'})


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
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


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_web_remote(src, dst):
    if os.environ.get('DATALAD_TESTS_NONETWORK'):
        raise SkipTest

    ar = AnnexRepo(dst, src)

    testurl = 'http://datalad.org/pages/about.html'
    testfile = 'datalad.org_pages_about.html'

    # get the file from remote
    with swallow_outputs() as cmo:
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
        with swallow_logs() as cml:
            ar.annex_drop(testfile)
            assert_in('ERROR', cml.out)
            assert_in('drop: 1 failed', cml.out)
    except CommandError as e:
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

@with_testrepos(flavors='network')
@with_tempfile
def test_AnnexRepo_migrating_backends(src, dst):
    ar = AnnexRepo(dst, src, backend='MD5')
    # GitPython has a bug which causes .git/config being wiped out
    # under Python3, triggered by collecting its config instance I guess
    gc.collect()
    ok_git_config_not_empty(ar)  # Must not blow, see https://github.com/gitpython-developers/GitPython/issues/333

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    f = open(filename_abs, 'w')
    f.write("What to write?")
    f.close()

    ar.annex_add(filename, backend='MD5')
    assert_equal(ar.get_file_backend(filename), 'MD5')
    assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')

    # migrating will only do, if file is present
    ok_annex_get(ar, 'test-annex.dat')

    if ar.is_direct_mode():
        # No migration in direct mode
        assert_raises(CommandNotAvailableError, ar.migrate_backend,
                      'test-annex.dat')
    else:
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')
        ar.migrate_backend('test-annex.dat')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'MD5')

        ar.migrate_backend('', backend='SHA1')
        assert_equal(ar.get_file_backend(filename), 'SHA1')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA1')


tree1args = dict(
    tree=(
        ('firstfile', 'whatever'),
        ('secondfile', 'something else'),
        ('remotefile', 'pretends to be remote'),
        ('faraway', 'incredibly remote')),
)


@with_tree(**tree1args)
@serve_path_via_http()
def test_AnnexRepo_backend_option(path, url):
    ar = AnnexRepo(path, backend='MD5')

    ar.annex_add('firstfile', backend='SHA1')
    ar.annex_add('secondfile')
    assert_equal(ar.get_file_backend('firstfile'), 'SHA1')
    assert_equal(ar.get_file_backend('secondfile'), 'MD5')

    with swallow_outputs() as cmo:
        ar.annex_addurl_to_file('remotefile', url + 'remotefile', backend='SHA1')
    assert_equal(ar.get_file_backend('remotefile'), 'SHA1')

    with swallow_outputs() as cmo:
        ar.annex_addurls([url +'faraway'], backend='SHA1')
    # TODO: what's the annex-generated name of this?
    # For now, workaround:
    assert_true(ar.get_file_backend(f) == 'SHA1'
                for f in ar.get_indexed_files() if 'faraway' in f)

@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_get_file_backend(src, dst):
    #init local test-annex before cloning:
    AnnexRepo(src)

    ar = AnnexRepo(dst, src)

    assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')
    if not ar.is_direct_mode():
        # no migration in direct mode
        ok_annex_get(ar, 'test-annex.dat', network=False)
        ar.migrate_backend('test-annex.dat', backend='SHA1')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA1')
    else:
        assert_raises(CommandNotAvailableError, ar.migrate_backend,
                      'test-annex.dat', backend='SHA1')


@with_tempfile
def test_AnnexRepo_always_commit(path):

    repo = AnnexRepo(path)
    runner = Runner(cwd=path)
    file1 = get_most_obscure_supported_name() + "_1"
    file2 = get_most_obscure_supported_name() + "_2"
    with open(opj(path, file1), 'w') as f:
        f.write("First file.")
    with open(opj(path, file2), 'w') as f:
        f.write("Second file.")

    # always_commit == True is expected to be default
    repo.annex_add(file1)

    # Now git-annex log should show the addition:
    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    assert_equal(len(out_list), 1)
    assert_in(file1, out_list[0])
    # check git log of git-annex branch:
    # expected: initial creation, update (by annex add) and another
    # update (by annex log)
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 3)

    repo.always_commit = False
    repo.annex_add(file2)

    # No additional git commit:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 3)

    repo.always_commit = True

    # Still one commit only in git-annex log,
    # but 'git annex log' was called when always_commit was true again,
    # so it should commit the addition at the end. Calling it again should then
    # show two commits.
    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    assert_equal(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in("recording state in git", out_list[1])

    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    assert_equal(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in(file2, out_list[1])

    # Now git knows as well:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 4)


# TODO:
#def annex_initremote(self, name, options):
#def annex_enableremote(self, name):


