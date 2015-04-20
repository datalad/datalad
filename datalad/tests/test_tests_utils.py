# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os, platform, sys

from os.path import exists, join as opj, basename
from glob import glob
from mock import patch

from nose.tools import assert_in, assert_not_in
from nose import SkipTest

from .utils import eq_, ok_, assert_false, ok_startswith, nok_startswith, \
    with_tempfile, with_testrepos, with_tree, \
    rmtemp, OBSCURE_FILENAMES, get_most_obscure_supported_name, \
    swallow_outputs, swallow_logs, \
    on_windows, assert_raises, assert_equal, assert_cwd_unchanged


##
# Test with_tempfile, especially nested invocations
#

@with_tempfile
def _with_tempfile_decorated_dummy(path):
    return path


def test_with_tempfile_dir_via_env_variable():
    target = os.path.join(os.path.expanduser("~"), "dataladtesttmpdir")
    assert_false(os.path.exists(target), "directory %s already exists." % target)
    with patch.dict('os.environ', {'DATALAD_TESTS_TEMPDIR': target}):
        filename = _with_tempfile_decorated_dummy()
        ok_startswith(filename, target)

@with_tempfile
@with_tempfile
def test_nested_with_tempfile_basic(f1, f2):
    ok_(f1 != f2)
    ok_(not os.path.exists(f1))
    ok_(not os.path.exists(f2))

# And the most obscure case to test.  Generator for the test is
# used as well to verify that every one of those functions adds new argument
# to the end of incoming arguments.
@with_tempfile(prefix="TEST", suffix='big')
@with_tree((('f1.txt', 'load'),))
@with_tempfile(suffix='.cfg')
@with_tempfile(suffix='.cfg.old')
@with_testrepos(flavors=['local'])
def check_nested_with_tempfile_parametrized_surrounded(param, f0, tree, f1, f2, repo):
    eq_(param, "param1")
    ok_(f0.endswith('big'), msg="got %s" % f0)
    ok_(os.path.basename(f0).startswith('TEST'), msg="got %s" % f0)
    ok_(os.path.exists(os.path.join(tree, 'f1.txt')))
    ok_(f1 != f2)
    ok_(f1.endswith('.cfg'), msg="got %s" % f1)
    ok_(f2.endswith('.cfg.old'), msg="got %s" % f2)
    ok_('testrepos' in repo)

def test_nested_with_tempfile_parametrized_surrounded():
    yield check_nested_with_tempfile_parametrized_surrounded, "param1"

def test_with_testrepos():
    repos = []

    @with_testrepos
    def check_with_testrepos(repo):
        repos.append(repo)

    check_with_testrepos()

    eq_(len(repos), 4)
    for repo in repos:
        if not (repo.startswith('git://') or repo.startswith('http')):
            print repo
            # either it is a "local" or a removed clone
            ok_(exists(opj(repo, '.git'))
                or
                not exists(opj(repo, '.git', 'remove-me')))

def test_with_tempfile_mkdir():
    dnames = [] # just to store the name within the decorated function

    @with_tempfile(mkdir=True)
    def check_mkdir(d1):
        ok_(os.path.exists(d1))
        ok_(os.path.isdir(d1))
        dnames.append(d1)
        eq_(glob(os.path.join(d1, '*')), [])
        # Create a file to assure we can remove later the temporary load
        with open(os.path.join(d1, "test.dat"), "w") as f:
            f.write("TEST LOAD")

    check_mkdir()
    if not os.environ.get('DATALAD_TESTS_KEEPTEMP'):
        ok_(not os.path.exists(dnames[0])) # got removed


@with_tempfile()
def test_with_tempfile_default_prefix(d1):
    d = basename(d1)
    short = 'datalad_temp_'
    full = short + \
           'test_with_tempfile_default_prefix'
    if on_windows:
        ok_startswith(d, short)
        nok_startswith(d, full)
    else:
        ok_startswith(d, full)


@with_tempfile(prefix="nodatalad_")
def test_with_tempfile_specified_prefix(d1):
    ok_startswith(basename(d1), 'nodatalad_')
    ok_('test_with_tempfile_specified_prefix' not in d1)


def test_get_most_obscure_supported_name():
    n = get_most_obscure_supported_name()
    if platform.system() in ('Linux', 'Darwin'):
        eq_(n, OBSCURE_FILENAMES[1])
    else:
        # ATM noone else is as good
        ok_(n in OBSCURE_FILENAMES[2:])


def test_keeptemp_via_env_variable():

    if os.environ.get('DATALAD_TESTS_KEEPTEMP'):
        raise SkipTest("We have env variable set to preserve tempfiles")

    files = []

    @with_tempfile()
    def check(f):
        open(f, 'w').write("LOAD")
        files.append(f)

    with patch.dict('os.environ', {}):
        check()

    with patch.dict('os.environ', {'DATALAD_TESTS_KEEPTEMP': '1'}):
        check()

    eq_(len(files), 2)
    ok_(not exists(files[0]), msg="File %s still exists" % files[0])
    ok_(    exists(files[1]), msg="File %s not exists" % files[1])

    rmtemp(files[-1])

def test_swallow_outputs():
    with swallow_outputs() as cm:
        eq_(cm.out, '')
        sys.stdout.write("out normal")
        sys.stderr.write("out error")
        eq_(cm.out, 'out normal')
        sys.stdout.write(" and more")
        eq_(cm.out, 'out normal and more') # incremental
        eq_(cm.err, 'out error')
        eq_(cm.err, 'out error') # the same value if multiple times

import logging
def test_swallow_logs():
    lgr = logging.getLogger('datalad')
    with swallow_logs(new_level=9) as cm:
        eq_(cm.out, '')
        lgr.log(8, "very heavy debug")
        eq_(cm.out, '') # not even visible at level 9
        lgr.log(9, "debug1")
        eq_(cm.out, 'debug1\n') # not even visible at level 9
        lgr.info("info")
        eq_(cm.out, 'debug1\ninfo\n') # not even visible at level 9

def test_ok_startswith():
    ok_startswith('abc', 'abc')
    ok_startswith('abc', 'a')
    ok_startswith('abc', '')
    ok_startswith(' abc', ' ')
    ok_startswith('abc\r\n', 'a') # no effect from \r\n etc
    assert_raises(AssertionError, ok_startswith, 'abc', 'b')
    assert_raises(AssertionError, ok_startswith, 'abc', 'abcd')

def test_nok_startswith():
    nok_startswith('abc', 'bc')
    nok_startswith('abc', 'c')
    assert_raises(AssertionError, nok_startswith, 'abc', 'a')
    assert_raises(AssertionError, nok_startswith, 'abc', 'abc')


def test_assert_cwd_unchanged():

    orig_dir = os.getcwd()

    @assert_cwd_unchanged
    def do_chdir():
        os.chdir(os.pardir)

    assert_raises(AssertionError, do_chdir)
    eq_(orig_dir, os.getcwd(),
        "assert_cwd_unchanged didn't return us back to %s" % orig_dir)


def test_assert_cwd_unchanged_ok_chdir():
    # Test that we are not masking out other "more important" exceptions

    orig_dir = os.getcwd()

    @assert_cwd_unchanged(ok_to_chdir=True)
    def do_chdir_value_error():
        os.chdir(os.pardir)

    with swallow_logs() as cml:
        do_chdir_value_error()
        eq_(orig_dir, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to %s" % orig_dir)
        assert_not_in("Mitigating and changing back", cml.out)


def test_assert_cwd_unchanged_not_masking_exceptions():
    # Test that we are not masking out other "more important" exceptions

    orig_dir = os.getcwd()

    @assert_cwd_unchanged
    def do_chdir_value_error():
        os.chdir(os.pardir)
        raise ValueError("error exception")

    with swallow_logs() as cml:
        assert_raises(ValueError, do_chdir_value_error)
        eq_(orig_dir, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to %s" % orig_dir)
        assert_in("Mitigating and changing back", cml.out)


    # and again but allowing to chdir
    @assert_cwd_unchanged(ok_to_chdir=True)
    def do_chdir_value_error():
        os.chdir(os.pardir)
        raise ValueError("error exception")

    with swallow_logs() as cml:
        assert_raises(ValueError, do_chdir_value_error)
        eq_(orig_dir, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to %s" % orig_dir)
        assert_not_in("Mitigating and changing back", cml.out)

