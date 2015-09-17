# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import platform
import sys
import os
import random

from bs4 import BeautifulSoup
from glob import glob
from os.path import exists, join as opj, basename

from six import text_type
from six.moves.urllib.request import urlopen

from mock import patch
from nose.tools import assert_in, assert_not_in, assert_true
from nose import SkipTest

from .utils import eq_, ok_, assert_false, ok_startswith, nok_startswith, \
    with_tempfile, with_testrepos, with_tree, \
    rmtemp, OBSCURE_FILENAMES, get_most_obscure_supported_name, \
    swallow_outputs, swallow_logs, \
    on_windows, assert_raises, assert_cwd_unchanged, serve_path_via_http, \
    ok_symlink, assert_true, ok_good_symlink, ok_broken_symlink

from .utils import assert_re_in
from .utils import local_testrepo_flavors
from .utils import skip_if_no_network

#
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
@with_testrepos(flavors=local_testrepo_flavors)
def check_nested_with_tempfile_parametrized_surrounded(
        param, f0, tree, f1, f2, repo):
    eq_(param, "param1")
    ok_(f0.endswith('big'), msg="got %s" % f0)
    ok_(os.path.basename(f0).startswith('TEST'), msg="got %s" % f0)
    ok_(os.path.exists(os.path.join(tree, 'f1.txt')))
    ok_(f1 != f2)
    ok_(f1.endswith('.cfg'), msg="got %s" % f1)
    ok_(f2.endswith('.cfg.old'), msg="got %s" % f2)
    ok_(repo) # got some repo -- local or url


def test_nested_with_tempfile_parametrized_surrounded():
    yield check_nested_with_tempfile_parametrized_surrounded, "param1"


def test_with_testrepos():
    repos = []

    @with_testrepos
    def check_with_testrepos(repo):
        repos.append(repo)

    check_with_testrepos()

    eq_(len(repos),
        2 if on_windows # TODO -- would fail now in DTGALAD_TESTS_NONETWORK mode
          else (3 if os.environ.get('DATALAD_TESTS_NONETWORK') else 4))  # local, local-url, clone, network

    for repo in repos:
        if not (repo.startswith('git://') or repo.startswith('http')):
            # either it is a "local" or a removed clone
            ok_(exists(opj(repo, '.git'))
                or
                not exists(opj(repo, '.git', 'remove-me')))


def test_with_tempfile_mkdir():
    dnames = []  # just to store the name within the decorated function

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
        ok_(not os.path.exists(dnames[0]))  # got removed


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
        # ATM no one else is as good
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


@with_tempfile
def test_ok_symlink_helpers(tmpfile):

    if on_windows:
        raise SkipTest("no sylmlinks on windows")

    assert_raises(AssertionError, ok_symlink, tmpfile)
    assert_raises(AssertionError, ok_good_symlink, tmpfile)
    assert_raises(AssertionError, ok_broken_symlink, tmpfile)

    tmpfile_symlink = tmpfile + '_symlink'
    os.symlink(tmpfile, tmpfile_symlink)  

    # broken symlink
    ok_symlink(tmpfile_symlink)
    ok_broken_symlink(tmpfile_symlink)
    assert_raises(AssertionError, ok_good_symlink, tmpfile_symlink)

    with open(tmpfile, 'w') as tf:
        tf.write('test text')
    
    # tmpfile is still not a symlink here
    assert_raises(AssertionError, ok_symlink, tmpfile)
    assert_raises(AssertionError, ok_good_symlink, tmpfile)
    assert_raises(AssertionError, ok_broken_symlink, tmpfile)

    ok_symlink(tmpfile_symlink)
    ok_good_symlink(tmpfile_symlink)
    assert_raises(AssertionError, ok_broken_symlink, tmpfile_symlink)


def test_ok_startswith():
    ok_startswith('abc', 'abc')
    ok_startswith('abc', 'a')
    ok_startswith('abc', '')
    ok_startswith(' abc', ' ')
    ok_startswith('abc\r\n', 'a')  # no effect from \r\n etc
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


@with_tempfile(mkdir=True)
def _test_serve_path_via_http(test_fpath, tmp_dir): # pragma: no cover

    # First verify that filesystem layer can encode this filename
    # verify first that we could encode file name in this environment
    try:
        filesysencoding = sys.getfilesystemencoding()
        test_fpath_encoded = test_fpath.encode(filesysencoding)
    except UnicodeEncodeError:
        raise SkipTest("Environment doesn't support unicode filenames")
    if test_fpath_encoded.decode(filesysencoding) != test_fpath:
        raise SkipTest("Can't convert back/forth using %s encoding"
                       % filesysencoding)

    test_fpath_full = text_type(os.path.join(tmp_dir, test_fpath))
    test_fpath_dir = text_type(os.path.dirname(test_fpath_full))

    if not os.path.exists(test_fpath_dir):
        os.makedirs(test_fpath_dir)

    with open(test_fpath_full, 'w') as f:
        test_txt = 'some txt and a randint {}'.format(random.randint(1, 10)) 
        f.write(test_txt)


    @serve_path_via_http(tmp_dir)
    def test_path_and_url(path, url):

        url = url + os.path.dirname(test_fpath)
        assert_true(urlopen(url))
        u = urlopen(url)
        assert_true(u.getcode() == 200)
        html = u.read()
        soup = BeautifulSoup(html, "html.parser")
        href_links = [txt.get('href') for txt in soup.find_all('a')]
        assert_true(len(href_links) == 1)

        url = "{}/{}".format(url, href_links[0])
        u = urlopen(url)
        html = u.read().decode()
        assert(test_txt == html)

    test_path_and_url()


def test_serve_path_via_http():
    for test_fpath in ['test1.txt',
                       'test_dir/test2.txt',
                       'test_dir/d2/d3/test3.txt',
                       'file with space test4',
                       u'Джэйсон',
                       get_most_obscure_supported_name(),
                      ]:

        yield _test_serve_path_via_http, test_fpath


def test_assert_re_in():
    assert_re_in(".*", "")
    assert_re_in(".*", ["any"])

    # should do match not search
    assert_re_in("ab", "abc")
    assert_raises(AssertionError, assert_re_in, "ab", "cab")
    assert_raises(AssertionError, assert_re_in, "ab$", "abc")

    # Sufficient to have one entry matching
    assert_re_in("ab", ["", "abc", "laskdjf"])
    assert_raises(AssertionError, assert_re_in, "ab$", ["ddd", ""])

    # Tuples should be ok too
    assert_re_in("ab", ("", "abc", "laskdjf"))
    assert_raises(AssertionError, assert_re_in, "ab$", ("ddd", ""))

    # shouldn't "match" the emty list
    assert_raises(AssertionError, assert_re_in, "", [])


def test_skip_if_no_network():
    cleaned_env = os.environ.copy()
    cleaned_env.pop('DATALAD_TESTS_NONETWORK', None)
    # we need to run under cleaned env to make sure we actually test in both conditions
    with patch('os.environ', cleaned_env):
        @skip_if_no_network
        def somefunc(a1):
            return a1
        with patch.dict('os.environ', {'DATALAD_TESTS_NONETWORK': '1'}):
            assert_raises(SkipTest, somefunc, 1)
        with patch.dict('os.environ', {}):
            eq_(somefunc(1), 1)