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
import traceback
import logging

try:
    # optional direct dependency we might want to kick out
    import bs4
except ImportError:  # pragma: no cover
    bs4 = None

from glob import glob
from os.path import exists, join as opj, basename

from six import PY2, PY3
from six import text_type
from six.moves.urllib.request import urlopen

from mock import patch
from nose.tools import assert_in, assert_not_in, assert_true
from nose import SkipTest

from ..utils import getpwd, chpwd

from .utils import eq_, ok_, assert_false, ok_startswith, nok_startswith, \
    with_tempfile, with_testrepos, with_tree, \
    rmtemp, OBSCURE_FILENAMES, get_most_obscure_supported_name, \
    swallow_outputs, swallow_logs, \
    on_windows, assert_raises, assert_cwd_unchanged, serve_path_via_http, \
    ok_symlink, assert_true, ok_good_symlink, ok_broken_symlink

from .utils import ok_generator
from .utils import assert_dict_equal
from .utils import assert_re_in
from .utils import local_testrepo_flavors
from .utils import skip_if_no_network
from .utils import skip_if_no_module
from .utils import run_under_dir
from .utils import skip_if
from .utils import ok_file_has_content
from .utils import without_http_proxy
from .utils import with_testsui

#
# Test with_tempfile, especially nested invocations
#

@with_tempfile
def _with_tempfile_decorated_dummy(path):
    return path


def test_with_tempfile_dir_via_env_variable():
    target = os.path.join(os.path.expanduser("~"), "dataladtesttmpdir")
    assert_false(os.path.exists(target), "directory %s already exists." % target)
    with patch.dict('os.environ', {'DATALAD_TESTS_TEMP_DIR': target}):
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
@with_testrepos(flavors=local_testrepo_flavors, count=1)
def check_nested_with_tempfile_parametrized_surrounded(
        param, f0, tree, f1, f2, repo):
    eq_(param, "param1")
    ok_(f0.endswith('big'), msg="got %s" % f0)
    ok_(os.path.basename(f0).startswith('TEST'), msg="got %s" % f0)
    ok_(os.path.exists(os.path.join(tree, 'f1.txt')))
    ok_(f1 != f2)
    ok_(f1.endswith('.cfg'), msg="got %s" % f1)
    ok_(f2.endswith('.cfg.old'), msg="got %s" % f2)
    ok_(repo)  # got some repo -- local or url


def test_nested_with_tempfile_parametrized_surrounded():
    yield check_nested_with_tempfile_parametrized_surrounded, "param1"


@with_tempfile(content="testtest")
def test_with_tempfile_content(f):
    ok_file_has_content(f, "testtest")
    ok_file_has_content(f, "test*", re_=True)


def test_with_tempfile_content_raises_on_mkdir():

    @with_tempfile(content="test", mkdir=True)
    def t():  # pragma: no cover
        raise AssertionError("must not be run")

    with assert_raises(ValueError):
        # after this commit, it will check when invoking, not when decorating
        t()


def test_with_testrepos():
    repos = []

    @with_testrepos
    def check_with_testrepos(repo):
        repos.append(repo)

    check_with_testrepos()

    eq_(len(repos),
        2 if on_windows  # TODO -- would fail now in DATALAD_TESTS_NONETWORK mode
          else (15 if os.environ.get('DATALAD_TESTS_NONETWORK') else 16))  # local, local-url, clone, network

    for repo in repos:
        if not (repo.startswith('git://') or repo.startswith('http')):
            # either it is a "local" or a removed clone
            ok_(exists(opj(repo, '.git'))
                or
                not exists(opj(repo, '.git', 'remove-me')))


def test_get_resolved_values():
    from datalad.tests.utils import _get_resolved_flavors
    flavors = ['networkish', 'local']
    eq_(([] if os.environ.get('DATALAD_TESTS_NONETWORK') else ['networkish'])
        + ['local'],
        _get_resolved_flavors(flavors))

    with patch.dict('os.environ', {'DATALAD_TESTS_NONETWORK': '1'}):
        eq_(_get_resolved_flavors(flavors), ['local'])

        # and one more to see the exception being raised if nothing to teston
        @with_testrepos(flavors=['network'])
        def magical():
            raise AssertionError("Must not be ran")
        assert_raises(SkipTest, magical)

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
    if not os.environ.get('DATALAD_TESTS_TEMP_KEEP'):
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

    if os.environ.get('DATALAD_TESTS_TEMP_KEEP'):  # pragma: no cover
        raise SkipTest("We have env variable set to preserve tempfiles")

    files = []

    @with_tempfile()
    def check(f):
        open(f, 'w').write("LOAD")
        files.append(f)

    with patch.dict('os.environ', {}):
        check()

    with patch.dict('os.environ', {'DATALAD_TESTS_TEMP_KEEP': '1'}):
        check()

    eq_(len(files), 2)
    ok_(not exists(files[0]), msg="File %s still exists" % files[0])
    ok_(    exists(files[1]), msg="File %s not exists" % files[1])

    rmtemp(files[-1])


@with_tempfile
def test_ok_symlink_helpers(tmpfile):

    if on_windows:  # pragma: no cover
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

def test_ok_generator():
    def func(a, b=1):
        return a+b
    def gen(a, b=1):  # pragma: no cover
        yield a+b
    # not sure how to determine if xrange is a generator
    if PY2:
        assert_raises(AssertionError, ok_generator, xrange(2))
    assert_raises(AssertionError, ok_generator, range(2))
    assert_raises(AssertionError, ok_generator, gen)
    ok_generator(gen(1))
    assert_raises(AssertionError, ok_generator, func)
    assert_raises(AssertionError, ok_generator, func(1))


def _test_assert_Xwd_unchanged(func):
    orig_cwd = os.getcwd()
    orig_pwd = getpwd()

    @assert_cwd_unchanged
    def do_chdir():
        func(os.pardir)

    with assert_raises(AssertionError) as cm:
        do_chdir()

    eq_(orig_cwd, os.getcwd(),
        "assert_cwd_unchanged didn't return us back to cwd %s" % orig_cwd)
    eq_(orig_pwd, getpwd(),
        "assert_cwd_unchanged didn't return us back to pwd %s" % orig_pwd)

def test_assert_Xwd_unchanged():
    yield _test_assert_Xwd_unchanged, os.chdir
    yield _test_assert_Xwd_unchanged, chpwd


def _test_assert_Xwd_unchanged_ok_chdir(func):
    # Test that we are not masking out other "more important" exceptions

    orig_cwd = os.getcwd()
    orig_pwd = getpwd()

    @assert_cwd_unchanged(ok_to_chdir=True)
    def do_chdir_value_error():
        func(os.pardir)

    with swallow_logs() as cml:
        do_chdir_value_error()
        eq_(orig_cwd, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to cwd %s" % orig_cwd)
        eq_(orig_pwd, getpwd(),
            "assert_cwd_unchanged didn't return us back to cwd %s" % orig_pwd)
        assert_not_in("Mitigating and changing back", cml.out)

def test_assert_Xwd_unchanged_ok_chdir():
    yield _test_assert_Xwd_unchanged_ok_chdir, os.chdir
    yield _test_assert_Xwd_unchanged_ok_chdir, chpwd

def test_assert_cwd_unchanged_not_masking_exceptions():
    # Test that we are not masking out other "more important" exceptions

    orig_cwd = os.getcwd()

    @assert_cwd_unchanged
    def do_chdir_value_error():
        os.chdir(os.pardir)
        raise ValueError("error exception")

    with swallow_logs(new_level=logging.WARN) as cml:
        with assert_raises(ValueError) as cm:
            do_chdir_value_error()
        # retrospect exception
        if PY2:
            # could not figure out how to make it legit for PY3
            # but on manual try -- works, and exception traceback is not masked out
            exc_info = sys.exc_info()
            assert_in('raise ValueError("error exception")', traceback.format_exception(*exc_info)[-2])

        eq_(orig_cwd, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to %s" % orig_cwd)
        assert_in("Mitigating and changing back", cml.out)

    # and again but allowing to chdir
    @assert_cwd_unchanged(ok_to_chdir=True)
    def do_chdir_value_error():
        os.chdir(os.pardir)
        raise ValueError("error exception")

    with swallow_logs(new_level=logging.WARN) as cml:
        assert_raises(ValueError, do_chdir_value_error)
        eq_(orig_cwd, os.getcwd(),
            "assert_cwd_unchanged didn't return us back to %s" % orig_cwd)
        assert_not_in("Mitigating and changing back", cml.out)


@with_tempfile(mkdir=True)
def _test_serve_path_via_http(test_fpath, tmp_dir):  # pragma: no cover

    # First verify that filesystem layer can encode this filename
    # verify first that we could encode file name in this environment
    try:
        filesysencoding = sys.getfilesystemencoding()
        test_fpath_encoded = test_fpath.encode(filesysencoding)
    except UnicodeEncodeError:  # pragma: no cover
        raise SkipTest("Environment doesn't support unicode filenames")
    if test_fpath_encoded.decode(filesysencoding) != test_fpath:  # pragma: no cover
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

        # @serve_ should remove http_proxy from the os.environ if was present
        assert_false('http_proxy' in os.environ)
        url = url + os.path.dirname(test_fpath)
        assert_true(urlopen(url))
        u = urlopen(url)
        assert_true(u.getcode() == 200)
        html = u.read()
        soup = bs4.BeautifulSoup(html, "html.parser")
        href_links = [txt.get('href') for txt in soup.find_all('a')]
        assert_true(len(href_links) == 1)

        url = "{}/{}".format(url, href_links[0])
        u = urlopen(url)
        html = u.read().decode()
        assert(test_txt == html)

    if bs4 is None:  # pragma: no cover
        raise SkipTest("bs4 is absent")
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

    # just with the last one check that we did remove proxy setting
    with patch.dict('os.environ', {'http_proxy': 'http://127.0.0.1:9/'}):
        yield _test_serve_path_via_http, test_fpath


def test_without_http_proxy():

    @without_http_proxy
    def check(a, kw=False):
        assert_false('http_proxy' in os.environ)
        assert_false('https_proxy' in os.environ)
        assert_in(kw, [False, 'custom'])

    check(1)

    with patch.dict('os.environ', {'http_proxy': 'http://127.0.0.1:9/'}):
        check(1)
        check(1, "custom")
        with assert_raises(AssertionError):
            check(1, "wrong")

    with patch.dict('os.environ', {'https_proxy': 'http://127.0.0.1:9/'}):
        check(1)
    with patch.dict('os.environ', {'http_proxy': 'http://127.0.0.1:9/',
                                   'https_proxy': 'http://127.0.0.1:9/'}):
        check(1)


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

    # shouldn't "match" the empty list
    assert_raises(AssertionError, assert_re_in, "", [])


def test_skip_if_no_network():
    cleaned_env = os.environ.copy()
    cleaned_env.pop('DATALAD_TESTS_NONETWORK', None)
    # we need to run under cleaned env to make sure we actually test in both conditions
    with patch('os.environ', cleaned_env):
        @skip_if_no_network
        def somefunc(a1):
            return a1
        eq_(somefunc.tags, ['network'])
        with patch.dict('os.environ', {'DATALAD_TESTS_NONETWORK': '1'}):
            assert_raises(SkipTest, somefunc, 1)
        with patch.dict('os.environ', {}):
            eq_(somefunc(1), 1)
        # and now if used as a function, not a decorator
        with patch.dict('os.environ', {'DATALAD_TESTS_NONETWORK': '1'}):
            assert_raises(SkipTest, skip_if_no_network)
        with patch.dict('os.environ', {}):
            eq_(skip_if_no_network(), None)


def test_skip_if_no_module():

    def testish():
        skip_if_no_module("nonexistingforsuremodule")
        raise ValueError
    assert_raises(SkipTest, testish)

    def testish2():
        skip_if_no_module("datalad")
        return "magic"
    eq_(testish2(), "magic")


def test_skip_if():

    with assert_raises(SkipTest):
        @skip_if(True)
        def f():  # pragma: no cover
            raise AssertionError("must have not been ran")
        f()

    @skip_if(False)
    def f():
        return "magical"
    eq_(f(), 'magical')


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_run_under_dir(d):
    orig_pwd = getpwd()
    orig_cwd = os.getcwd()

    @run_under_dir(d)
    def f(arg, kwarg=None):
        eq_(arg, 1)
        eq_(kwarg, 2)
        eq_(getpwd(), d)

    f(1, 2)
    eq_(getpwd(), orig_pwd)
    eq_(os.getcwd(), orig_cwd)

    # and if fails
    assert_raises(AssertionError, f, 1, 3)
    eq_(getpwd(), orig_pwd)
    eq_(os.getcwd(), orig_cwd)


def test_assert_dict_equal():
    assert_dict_equal({}, {})
    assert_dict_equal({"a": 3}, {"a": 3})
    assert_raises(AssertionError, assert_dict_equal, {1: 3}, {1: 4})
    assert_raises(AssertionError, assert_dict_equal, {1: 3}, {2: 4})
    assert_raises(AssertionError, assert_dict_equal, {1: 3}, {2: 4, 1: 3})
    assert_raises(AssertionError, assert_dict_equal, {1: 3}, {2: 4, 1: 'a'})
    try:
        import numpy as np
    except:  # pragma: no cover
        raise SkipTest("need numpy for this tiny one")
    # one is scalar another one array
    assert_raises(AssertionError, assert_dict_equal, {1: 0}, {1: np.arange(1)})
    assert_raises(AssertionError, assert_dict_equal, {1: 0}, {1: np.arange(3)})


def test_testsui():
    # just one for now to test conflicting arguments
    with assert_raises(ValueError):
        @with_testsui(responses='some', interactive=False)
        def some_func():   # pragma: no cover
            pass

    from datalad.ui import ui

    @with_testsui(responses=['yes', "maybe so"])
    def func2(x):
        assert x == 1
        eq_(ui.yesno("title"), True)
        eq_(ui.question("title2"), "maybe so")
        assert_raises(AssertionError, ui.question, "asking more than we know")
        return x*2
    eq_(func2(1), 2)

    @with_testsui(interactive=False)
    def func3(x):
        assert_false(ui.is_interactive)
        return x*3
    eq_(func3(2), 6)
