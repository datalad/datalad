# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test testing utilities

"""

import inspect
import logging
import os
import os.path as op
import shutil
import stat
import sys
import time
from functools import wraps
from operator import itemgetter
from os.path import (
    abspath,
    basename,
    dirname,
    exists,
    expanduser,
    expandvars,
    isabs,
)
from os.path import join as opj
from os.path import (
    normpath,
    pardir,
)
from unittest.mock import patch

import pytest

from datalad import cfg as dl_cfg
from datalad.support.annexrepo import AnnexRepo
from datalad.utils import (
    CMD_MAX_ARG,
    Path,
    _path_,
    any_re_search,
    auto_repr,
    better_wraps,
    chpwd,
    create_tree,
    disable_logger,
    dlabspath,
    ensure_write_permission,
    expandpath,
    file_basename,
    find_files,
    generate_chunks,
    get_dataset_root,
    get_open_files,
    get_path_prefix,
    get_sig_param_names,
    get_timestamp_suffix,
    get_trace,
    getargspec,
    getpwd,
    import_module_from_file,
    import_modules,
    is_explicit_path,
    is_interactive,
    join_cmdline,
    knows_annex,
    line_profile,
    make_tempfile,
    map_items,
    md5sum,
    never_fail,
    not_supported_on_windows,
    obtain_write_permission,
    on_windows,
    partition,
    path_is_subpath,
    path_startswith,
    rotree,
    split_cmdline,
    swallow_logs,
    swallow_outputs,
    todo_interface_for_extensions,
    unique,
    unlink,
    updated,
)

from .utils_pytest import (
    OBSCURE_FILENAME,
    SkipTest,
    assert_cwd_unchanged,
    assert_equal,
    assert_false,
    assert_greater,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_true,
    ensure_bool,
    ensure_dict_from_str,
    ensure_iter,
    ensure_list,
    ensure_list_from_str,
    ensure_unicode,
    eq_,
    has_symlink_capability,
    known_failure,
    nok_,
    ok_,
    ok_file_has_content,
    ok_generator,
    ok_startswith,
    on_travis,
    probe_known_failure,
    skip_if,
    skip_if_no_module,
    skip_if_on_windows,
    skip_if_root,
    skip_known_failure,
    skip_wo_symlink_capability,
    with_tempfile,
    with_tree,
)


def test_better_wraps():
    def wraps_decorator(func):
        @wraps(func)
        def  _wrap_wraps_decorator(*args, **kwargs):
            return func(*args, **kwargs)

        return  _wrap_wraps_decorator

    def better_decorator(func):
        @better_wraps(func)
        def  _wrap_better_decorator(*args, **kwargs):
            return func(*args, **kwargs)

        return  _wrap_better_decorator

    @wraps_decorator
    def function1(a, b, c):
        return "function1"

    @better_decorator
    def function2(a, b, c):
        return "function2"

    eq_("function1", function1(1, 2, 3))
    # getargspec shim now can handle @wraps'ed functions just fine
    eq_(getargspec(function1)[0], ['a', 'b', 'c'])
    eq_("function2", function2(1, 2, 3))
    eq_(getargspec(function2)[0], ['a', 'b', 'c'])


# TODO?: make again parametric on eq_argspec invocations?
@pytest.mark.filterwarnings(r"ignore: inspect.getargspec\(\) is deprecated")
def test_getargspec():

    def eq_argspec(f, expected, has_kwonlyargs=False):
        """A helper to centralize testing of getargspec on original and wrapped function

        has_kwonlyargs is to instruct if function has kwonly args so we do not try to compare
        to inspect.get*spec functions, which would barf ValueError if attempted to run on a
        function with kwonlys. And also we pass it as include_kwonlyargs to our getargspec
        """
        # so we know that our expected is correct
        if not has_kwonlyargs:
            # if False - we test function with kwonlys - inspect.getargspec would barf
            if sys.version_info < (3, 11):
                eq_(inspect.getargspec(f), expected)
            # and getfullargspec[:4] wouldn't provide a full picture
            eq_(inspect.getfullargspec(f)[:4], expected)
        else:
            if sys.version_info < (3, 11):
                assert_raises(ValueError, inspect.getargspec, f)
            inspect.getfullargspec(f)  # doesn't barf
        eq_(getargspec(f, include_kwonlyargs=has_kwonlyargs), expected)

        # and lets try on a wrapped one -- only ours can do the right thing
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):  # pragma: no cover
                return f(*args, **kwargs)
            return wrapper
        fw = decorator(f)
        if has_kwonlyargs:
            # We barf ValueError similarly to inspect.getargspec, unless explicitly requested
            # to include kwonlyargs
            assert_raises(ValueError, getargspec, fw)
        eq_(getargspec(fw, include_kwonlyargs=has_kwonlyargs), expected)

    def f0():  # pragma: no cover
        pass

    eq_argspec(f0, ([], None, None, None))

    def f1(a1, kw1=None, kw0=1):  # pragma: no cover
        pass

    eq_argspec(f1, (['a1', 'kw1', 'kw0'], None, None, (None, 1)))

    # Having *a already makes keyword args to be kwonlyargs, in that
    # inspect.get*spec would barf
    def f1_args(a1, *a, kw1=None, kw0=1, **kw):  # pragma: no cover
        pass

    eq_argspec(f1_args, (['a1', 'kw1', 'kw0'], 'a', 'kw', (None, 1)), True)

    def f1_star(a1, *, kw1=None, kw0=1):  # pragma: no cover
        pass

    assert_raises(ValueError, getargspec, f1_star)
    eq_argspec(f1_star, (['a1', 'kw1', 'kw0'], None, None, (None, 1)), True)


def test_get_sig_param_names():
    def f(a1, kw1=None, *args, kw2=None, **kwargs):
        pass  # pragma: no cover

    # note: `a1` could be used either positionally or via keyword, so is listed in kw_any
    assert_equal(get_sig_param_names(f, ('kw_only', 'kw_any')), (['kw2'], ['a1', 'kw1', 'kw2']))
    assert_equal(get_sig_param_names(f, ('any',)), (['a1', 'kw1', 'kw2'],))
    assert_equal(get_sig_param_names(f, tuple()), ())
    assert_raises(ValueError, get_sig_param_names, f, ('mumba',))


@with_tempfile(mkdir=True)
def test_rotree(d=None):
    d2 = opj(d, 'd1', 'd2')  # deep nested directory
    f = opj(d2, 'f1')
    os.makedirs(d2)
    with open(f, 'w') as f_:
        f_.write("LOAD")
    with swallow_logs():
        ar = AnnexRepo(d2)
    rotree(d)
    # we shouldn't be able to delete anything UNLESS in "crippled" situation:
    # root, or filesystem is FAT etc
    # Theoretically annex should declare FS as crippled when ran as root, but
    # see http://git-annex.branchable.com/bugs/decides_that_FS_is_crippled_
    # under_cowbuilder___40__symlinks_supported_etc__41__/#comment-60c3cbe2710d6865fb9b7d6e247cd7aa
    # so explicit 'or'
    if not (ar.is_crippled_fs() or (os.getuid() == 0)):
        assert_raises(OSError, os.unlink, f)          # OK to use os.unlink
        assert_raises(OSError, unlink, f)   # and even with waiting and trying!
        assert_raises(OSError, shutil.rmtree, d)
        # but file should still be accessible
        with open(f) as f_:
            eq_(f_.read(), "LOAD")
    # make it RW
    rotree(d, False)
    unlink(f)
    shutil.rmtree(d)


def test_swallow_outputs():
    with swallow_outputs() as cm:
        eq_(cm.out, '')
        sys.stdout.write("out normal")
        sys.stderr.write("out error")
        eq_(cm.out, 'out normal')
        sys.stdout.write(" and more")
        eq_(cm.out, 'out normal and more')  # incremental
        eq_(cm.err, 'out error')
        eq_(cm.err, 'out error')  # the same value if multiple times


@with_tempfile
def test_swallow_logs(logfile=None):
    lgr = logging.getLogger('datalad')
    with swallow_logs(new_level=9) as cm:
        eq_(cm.out, '')
        lgr.log(8, "very heavy debug")
        eq_(cm.out, '')  # not even visible at level 9
        lgr.log(9, "debug1")
        eq_(cm.out, '[Level 9] debug1\n')  # not even visible at level 9
        lgr.info("info")
        # not even visible at level 9
        eq_(cm.out, '[Level 9] debug1\n[INFO] info\n')
    with swallow_logs(new_level=9, file_=logfile) as cm:
        eq_(cm.out, '')
        lgr.info("next info")
    from datalad.tests.utils_pytest import ok_file_has_content
    ok_file_has_content(logfile, "[INFO] next info", strip=True)


def test_swallow_logs_assert():
    lgr = logging.getLogger('datalad.tests')
    with swallow_logs(new_level=9) as cm:
        # nothing was logged so should fail
        assert_raises(AssertionError, cm.assert_logged)
        lgr.info("something")
        cm.assert_logged("something")
        cm.assert_logged(level="INFO")
        cm.assert_logged("something", level="INFO")

        # even with regex = False should match above
        cm.assert_logged("something", regex=False)
        cm.assert_logged(level="INFO", regex=False)
        cm.assert_logged("something", level="INFO", regex=False)

        # different level
        assert_raises(AssertionError,
                      cm.assert_logged, "something", level="DEBUG")
        assert_raises(AssertionError, cm.assert_logged, "else")

        cm.assert_logged("some.hing", level="INFO")  # regex ;-)
        # does match
        assert_raises(AssertionError,
                      cm.assert_logged, "ome.hing", level="INFO")
        # but we can change it
        cm.assert_logged("some.hing", level="INFO", match=False)
    # and we can continue doing checks after we left the cm block
    cm.assert_logged("some.hing", level="INFO", match=False)
    # and we indeed logged something
    cm.assert_logged(match=False)


def test_disable_logger():

    # get a logger hierarchy:
    lgr_top = logging.getLogger('datalad')
    lgr_middle = logging.getLogger('datalad.tests')
    lgr_bottom = logging.getLogger('datalad.tests.utils_pytest')

    with swallow_logs(new_level=logging.DEBUG) as cml:
        with disable_logger():  # default: 'datalad':
            lgr_top.debug("log sth at top level")
            lgr_middle.debug("log sth at mid level")
            lgr_bottom.debug("log sth at bottom level")
        # nothing logged:
        assert_raises(AssertionError, cml.assert_logged)

    # again, but pass in the logger at mid level:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        with disable_logger(lgr_middle):
            lgr_top.debug("log sth at top level")
            lgr_middle.debug("log sth at mid level")
            lgr_bottom.debug("log sth at bottom level")
        # top level unaffected:
        cml.assert_logged("log sth at top level", level="DEBUG", regex=False)
        # but both of the lower ones don't log anything:
        assert_raises(AssertionError, cml.assert_logged, "log sth at mid level")
        assert_raises(AssertionError, cml.assert_logged, "log sth at bottom level")


def test_md5sum():
    # just a smoke (encoding/decoding) test for md5sum
    _ = md5sum(__file__)


@with_tree([('1.tar.gz', (('1 f.txt', '1 f load'),))])
def test_md5sum_archive(d=None):
    # just a smoke (encoding/decoding) test for md5sum
    _ = md5sum(opj(d, '1.tar.gz'))


def test_updated():
    d = {}
    eq_(updated(d, {1: 2}), {1: 2})
    eq_(d, {})

    d = {'a': 'b'}
    eq_(updated(d, ((0, 1), (2, 3))), {0: 1, 'a': 'b', 2: 3})
    eq_(d, {'a': 'b'})

    # and that it would maintain the type
    d = dict(((99, 0), ('z', 0), ('a', 0)))
    d_ = updated(d, {0: 1})
    ok_(isinstance(d_, dict))
    eq_(d_, dict(((99, 0), ('z', 0), ('a', 0), (0, 1))))


def test_get_local_file_url_windows():
    raise SkipTest("TODO")


@assert_cwd_unchanged
def test_getpwd_basic():
    pwd = getpwd()
    ok_(isabs(pwd))
    eq_(os.getcwd(), abspath(pwd))

    # that we do not chdir anywhere if None provided
    with patch('os.chdir') as oschdir:
        with chpwd(None):
            eq_(getpwd(), pwd)
        assert_false(oschdir.called)


@with_tempfile(mkdir=True)
@assert_cwd_unchanged(ok_to_chdir=True)
def test_getpwd_change_mode(tdir=None):
    from datalad import utils
    if utils._pwd_mode != 'PWD':
        raise SkipTest("Makes sense to be tested only in PWD mode, "
                       "but we seems to be beyond that already")
    # The evil plain chdir call
    os.chdir(tdir)
    # Just testing the logic of switching to cwd mode and issuing a warning
    with swallow_logs(new_level=logging.DEBUG) as cml:
        pwd = getpwd()
        eq_(pwd, str(Path(pwd).resolve()))  # might have symlinks, thus realpath
    assert_in("symlinks in the paths will be resolved", cml.out)
    eq_(utils._pwd_mode, 'cwd')


@skip_wo_symlink_capability
@skip_if_on_windows
@with_tempfile(mkdir=True)
@assert_cwd_unchanged
def test_getpwd_symlink(tdir=None):
    sdir = opj(tdir, 's1')
    pwd_orig = getpwd()
    Path(sdir).symlink_to(Path('.'))
    s1dir = opj(sdir, 's1')
    s2dir = opj(sdir, 's2')
    try:
        chpwd(sdir)
        pwd = getpwd()
        eq_(pwd, sdir)
        chpwd('s1')
        eq_(getpwd(), s1dir)
        chpwd('.')
        eq_(getpwd(), s1dir)
        chpwd('..')
        eq_(getpwd(), sdir)
    finally:
        chpwd(pwd_orig)

    # test context handler way of use
    with chpwd(s1dir):
        eq_(getpwd(), s1dir)
    eq_(getpwd(), pwd_orig)

    assert_false(exists(s2dir))
    with assert_raises(OSError):
        with chpwd(s2dir):
            pass
    with chpwd(s2dir, mkdir=True):
        ok_(exists(s2dir))
        eq_(getpwd(), s2dir)


@with_tempfile(mkdir=True)
def test_chpwd_obscure_name(topdir=None):
    path = op.join(topdir, OBSCURE_FILENAME)
    os.mkdir(path)
    # Just check that call doesn't fail.
    with chpwd(path):
        pass


def test_auto_repr():

    class WithoutReprClass:
        def __init__(self):
            self.a = "does not matter"

    @auto_repr
    class buga:
        def __init__(self):
            self.a = 1
            self.b = list(range(20))
            self.c = WithoutReprClass()
            self._c = "protect me"

        def some(self):
            return "some"

    @auto_repr(short=False)
    class buga_long(object):
        def __init__(self):
            self.a = 1
            self.b = list(range(20))

        def some(self):
            return "some"

    assert_equal(
        repr(buga()),
        "buga(a=1, b=<<[0, 1, 2, 3, 4++52 chars++ 19]>>, c=<WithoutReprClass>)"
    )
    assert_equal(buga().some(), "some")

    assert_equal(
        repr(buga_long()),
        f"buga_long(a=1, b=[{', '.join(map(str, range(20)))}])"
    )
    assert_equal(buga_long().some(), "some")


def test_todo_interface_for_extensions():

    @todo_interface_for_extensions
    def f(i, j):
        return i*j

    assert_equal(f(2, 3), 6)


def test_assure_iter():
    s = {1}
    assert ensure_iter(None, set) == set()
    assert ensure_iter(1, set) == s
    assert ensure_iter(1, list) == [1]
    assert ensure_iter(s, set) is s
    assert ensure_iter(s, set, copy=True) is not s


def test_assure_list_copy():
    l = [1]
    assert ensure_list(l) is l
    assert ensure_list(l, copy=True) is not l


@pytest.mark.parametrize(
    "value,result",
    [
        ('', None),
        ([], None),
        ('somestring', ['somestring']),
        ('some\nmultiline\nstring', ['some', 'multiline', 'string']),
        (['something'], ['something']),
        (['a', 'listof', 'stuff'], ['a', 'listof', 'stuff']),
    ]
)
def test_assure_list_from_str(value, result):
    assert ensure_list_from_str(value) == result


def test_assure_dict_from_str():
    assert_equal(ensure_dict_from_str(''), None)
    assert_equal(ensure_dict_from_str({}), None)
    target_dict = dict(
        __ac_name='{user}', __ac_password='{password}',
        cookies_enabled='', submit='Log in'
    )
    string = '__ac_name={user}\n__ac_password={password}\nsubmit=Log ' \
               'in\ncookies_enabled='
    assert_equal(ensure_dict_from_str(string), target_dict)
    assert_equal(ensure_dict_from_str(
        target_dict),
        target_dict)


def test_assure_bool():
    for values, t in [
        (['True', 1, '1', 'yes', 'on'], True),
        (['False', 0, '0', 'no', 'off'], False)
    ]:
        for v in values:
            eq_(ensure_bool(v), t)
    assert_raises(ValueError, ensure_bool, "unknown")


def test_generate_chunks():
    ok_generator(generate_chunks([1], 1))
    eq_(list(generate_chunks([1], 1)), [[1]])
    eq_(list(generate_chunks([1], 2)), [[1]])
    eq_(list(generate_chunks([1, 2, 3], 2)), [[1, 2], [3]])
    # type is preserved
    eq_(list(generate_chunks((1, 2, 3), 2)), [(1, 2), (3,)])
    # no hangers
    eq_(list(generate_chunks((1, 2, 3, 4), 2)), [(1, 2), (3, 4)])
    assert_raises(AssertionError, list, generate_chunks([1], 0))


def test_any_re_search():
    assert_true(any_re_search('a', 'a'))
    assert_true(any_re_search('a', 'bab'))
    assert_false(any_re_search('^a', 'bab'))
    assert_true(any_re_search(['b', '.ab'], 'bab'))
    assert_false(any_re_search(['^b', 'bab'], 'ab'))


def test_find_files():
    tests_dir = dirname(__file__)
    proj_dir = normpath(opj(dirname(__file__), pardir))

    ff = find_files('.*', proj_dir)
    ok_generator(ff)
    files = list(ff)
    assert(len(files) > 10)  # we have more than 10 test files here
    assert_in(opj(tests_dir, 'test_utils.py'), files)
    # and no directories should be mentioned
    assert_not_in(tests_dir, files)

    ff2 = find_files('.*', proj_dir, dirs=True)
    files2 = list(ff2)
    assert_in(opj(tests_dir, 'test_utils.py'), files2)
    assert_in(tests_dir, files2)

    # now actually matching the path
    ff3 = find_files(
        r'.*\\test_.*\.py$' if on_windows else r'.*/test_.*\.py$',
        proj_dir, dirs=True)
    files3 = list(ff3)
    assert_in(opj(tests_dir, 'test_utils.py'), files3)
    assert_not_in(tests_dir, files3)
    for f in files3:
        ok_startswith(basename(f), 'test_')


@with_tree(tree={
    '.git': {
        '1': '2'
    },
    'd1': {
        '.git': 'possibly a link from submodule'
    },
    'git': 'just a file'
})
def test_find_files_exclude_vcs(repo=None):
    ff = find_files('.*', repo, dirs=True)
    files = list(ff)
    assert_equal({basename(f) for f in files}, {'d1', 'git'})
    assert_not_in(opj(repo, '.git'), files)

    ff = find_files('.*', repo, dirs=True, exclude_vcs=False)
    files = list(ff)
    assert_equal({basename(f) for f in files}, {'d1', 'git', '.git', '1'})
    assert_in(opj(repo, '.git'), files)


def test_not_supported_on_windows():
    with patch('datalad.utils.on_windows', True):
        assert_raises(NotImplementedError, not_supported_on_windows)
        assert_raises(NotImplementedError, not_supported_on_windows, "msg")

    with patch('datalad.utils.on_windows', False):
        assert_equal(not_supported_on_windows(), None)
        assert_equal(not_supported_on_windows("msg"), None)


def test_file_basename():
    eq_(file_basename('1'), '1')
    eq_(file_basename('d1/1'), '1')
    eq_(file_basename('/d1/1'), '1')
    eq_(file_basename('1.'), '1.')
    eq_(file_basename('1.tar.gz'), '1')
    eq_(file_basename('1.Tar.gz'), '1')
    eq_(file_basename('1._bak.gz'), '1')
    eq_(file_basename('1.tar.gz', return_ext=True), ('1', 'tar.gz'))
    eq_(file_basename('/tmp/1.tar.gz'), '1')
    eq_(file_basename('/tmp/1.longish.gz'), '1.longish')
    eq_(file_basename('1_R1.1.1.tar.gz'), '1_R1.1.1')
    eq_(file_basename('ds202_R1.1.1.tgz'), 'ds202_R1.1.1')


def test_expandpath():
    eq_(expandpath("some", False), expanduser('some'))
    eq_(expandpath("some", False), expandvars('some'))
    assert_true(isabs(expandpath('some')))
    # this may have to go because of platform issues
    if not on_windows:
        # expanduser is not influenced by our HOME setting adjustments
        # for the tests on windows
        eq_(expandpath("$HOME"), expanduser('~'))


def test_is_explicit_path():
    # by default expanded paths are absolute, hence explicit
    assert_true(is_explicit_path(expandpath('~')))
    assert_false(is_explicit_path("here"))


@with_tempfile
@with_tempfile
def test_knows_annex(here=None, there=None):
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.gitrepo import GitRepo
    GitRepo(path=here, create=True)
    assert_false(knows_annex(here))
    AnnexRepo(path=here, create=True)
    assert_true(knows_annex(here))
    GitRepo.clone(path=there, url=here, create=True)
    assert_true(knows_annex(there))


def test_make_tempfile():
    # check if mkdir, content conflict caught
    with assert_raises(ValueError):
        with make_tempfile(content="blah", mkdir=True):  # pragma: no cover
            pass


def test_unique():
    eq_(unique(range(3)), [0, 1, 2])
    eq_(unique(range(3), reverse=True), [0, 1, 2])
    eq_(unique((1, 0, 1, 3, 2, 0, 1)), [1, 0, 3, 2])
    eq_(unique((1, 0, 1, 3, 2, 0, 1), reverse=True), [3, 2, 0, 1])
    eq_(unique([]), [])
    eq_(unique([], reverse=True), [])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)]), [(1, 2), (1,), (0, 3)])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)], reverse=True),
        [(1,), (1, 2), (0, 3)])

    # with a key now
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)],
               key=itemgetter(0)), [(1, 2), (0, 3)])
    eq_(unique([(1, 2), (1,), (1, 2), (0, 3)],
               key=itemgetter(0), reverse=True), [(1, 2), (0, 3)])

    eq_(unique([(1, 2), (1, 3), (1, 2), (0, 3)],
               key=itemgetter(1)), [(1, 2), (1, 3)])
    eq_(unique([(1, 2), (1, 3), (1, 2), (0, 3)],
               key=itemgetter(1), reverse=True), [(1, 2), (0, 3)])


def test_partition():
    def fn(*args, **kwargs):
        left, right = partition(*args, **kwargs)
        return list(left), list(right)

    eq_(fn([False, True, False]),
        ([False, False], [True]))

    eq_(fn([1, 5, 4, 10], lambda x: x > 4),
        ([1, 4], [5, 10]))

    eq_(fn([1, 5, 4, 10], lambda x: x < 0),
        ([1, 5, 4, 10], []))


def test_path_():
    eq_(_path_('a'), 'a')
    if on_windows:
        eq_(_path_('a/b'), r'a\b')
    else:
        p = 'a/b/c'
        assert(_path_(p) is p)  # nothing is done to it whatsoever
        eq_(_path_(p, 'd'), 'a/b/c/d')


def test_get_timestamp_suffix():
    # we need to patch temporarily TZ
    with patch.dict('os.environ', {'TZ': 'GMT'}):
        # figure out how GMT time zone suffix is represented
        # could be +0 or -0, depending on platform
        # just use whatever it is, not the subject of this test
        tz_suffix = time.strftime('%z', time.gmtime(0))
        # skynet DOB
        target_ts = '1970-01-01T00:00:00' + tz_suffix
        assert_equal(get_timestamp_suffix(0), '-' + target_ts)
        assert_equal(get_timestamp_suffix(0, prefix="+"),
                     '+' + target_ts)
        # yoh found no way to mock things out and didn't want to provide
        # explicit call to anything to get current time with the timezone,
        # so disabling this test for now besides that it should return smth
        # sensible ;)
        #with patch.object(time, 'localtime', lambda: 1):
        #    assert_equal(get_timestamp_suffix(),
        #  '-1970-01-01T00:00:01+0000')  # skynet is 1 sec old
        assert(get_timestamp_suffix().startswith('-'))


def test_memoized_generator():
    called = [0]

    def g1(n):
        """a generator"""
        called[0] += 1
        for i in range(n):
            yield i

    from ..utils import saved_generator
    ok_generator(g1(3))
    g1_, g2_ = saved_generator(g1(3))
    ok_generator(g1_)
    ok_generator(g2_)
    target = list(g1(3))
    eq_(called[0], 1)
    eq_(target, list(g1_))
    eq_(called[0], 2)
    eq_(target, list(g2_))
    eq_(called[0], 2)  # no new call to make a generator
    # but we can't (ab)use 2nd time
    eq_([], list(g2_))


def test_assure_unicode():
    ok_(isinstance(ensure_unicode("m"), str))
    ok_(isinstance(ensure_unicode('grandchild_äöü東'), str))
    ok_(isinstance(ensure_unicode(u'grandchild_äöü東'), str))
    eq_(ensure_unicode('grandchild_äöü東'), u'grandchild_äöü東')
    # now, non-utf8
    # Decoding could be deduced with high confidence when the string is
    # really encoded in that codepage
    mom_koi8r = u"мама".encode('koi8-r')
    eq_(ensure_unicode(mom_koi8r), u"мама")
    eq_(ensure_unicode(mom_koi8r, confidence=0.9), u"мама")
    mom_iso8859 = u'mamá'.encode('iso-8859-1')
    eq_(ensure_unicode(mom_iso8859), u'mamá')
    eq_(ensure_unicode(mom_iso8859, confidence=0.5), u'mamá')
    # but when we mix, it does still guess something allowing to decode:
    mixedin = mom_koi8r + u'東'.encode('iso2022_jp') + u'東'.encode('utf-8')
    ok_(isinstance(ensure_unicode(mixedin), str))
    # but should fail if we request high confidence result:
    with assert_raises(ValueError):
        ensure_unicode(mixedin, confidence=0.9)
    # For other, non string values, actually just returns original value
    # TODO: RF to actually "assure" or fail??  For now hardcoding that assumption
    assert ensure_unicode(1) == 1


def test_pathlib_unicode():
    eq_(str(Path("a")), u"a")
    eq_(str(Path(u"β")), u"β")


@with_tempfile(mkdir=True)
def test_path_prefix(path=None):
    eq_(get_path_prefix(_p('/d1/d2'), _p('/d1/d2')), _p(''))
    # so we are under /d1/d2 so path prefix is ..
    eq_(get_path_prefix(_p('/d1/d2'), _p('/d1/d2/d3')), _p('..'))
    eq_(get_path_prefix(_p('/d1/d2/d3'), _p('/d1/d2')), _p('d3'))
    # but if outside -- full path
    eq_(get_path_prefix(_p('/d1/d2'), _p('/d1/d20/d3')), _p('/d1/d2'))
    with chpwd(path):
        eq_(get_path_prefix('.'), '')
        eq_(get_path_prefix('d1'), 'd1')
        eq_(get_path_prefix('d1', 'd2'), opj(path, 'd1'))
        eq_(get_path_prefix('..'), '..')


def test_get_trace():
    assert_raises(ValueError, get_trace, [], 'boom', 'does_not_matter')
    eq_(get_trace([('A', 'B')], 'A', 'A'), None)
    eq_(get_trace([('A', 'B')], 'A', 'B'), [])
    eq_(get_trace([('A', 'B')], 'A', 'C'), None)
    eq_(get_trace([('A', 'B'),
                   ('B', 'C')], 'A', 'C'), ['B'])
    # order of edges doesn't matter
    eq_(get_trace([
        ('B', 'C'),
        ('A', 'B')
        ], 'A', 'C'), ['B'])
    # mixed rubbish
    eq_(get_trace([
        (1, 3),
        ('B', 'C'),
        (None, ('schwak', 7)),
        ('A', 'B'),
        ], 'A', 'C'), ['B'])
    # long
    eq_(get_trace([
        ('B', 'C'),
        ('A', 'B'),
        ('distract', 'me'),
        ('C', 'D'),
        ('D', 'E'),
        ], 'A', 'E'), ['B', 'C', 'D'])


@with_tempfile(mkdir=True)
def test_get_dataset_root(path=None):
    eq_(get_dataset_root('/nonexistent'), None)
    with chpwd(path):
        repo = AnnexRepo(os.curdir, create=True)
        subdir = opj('some', 'deep')
        fname = opj(subdir, 'dummy')
        os.makedirs(subdir)
        with open(fname, 'w') as f:
            f.write('some')
        repo.add(fname)
        # we can find this repo
        eq_(get_dataset_root(os.curdir), os.curdir)
        # and we get the type of path that we fed in
        eq_(get_dataset_root(abspath(os.curdir)), abspath(os.curdir))
        # subdirs are no issue
        eq_(get_dataset_root(subdir), os.curdir)
        # even more subdirs are no issue
        eq_(get_dataset_root(opj(subdir, subdir)), os.curdir)
        # non-dir paths are no issue
        eq_(get_dataset_root(fname), os.curdir)


def _p(p: str) -> str:
    """A helper to code paths as POSIX paths in tests  below. Would prepend fake drive
       C: to absolute paths on Windows"""
    if on_windows:
        pm = p.replace('/', os.sep)
        if p.startswith('/'):
            return f"C:{pm}"
        else:
            return pm
    return p


def test_path_startswith():
    ok_(path_startswith(_p('/a/b'), _p('/a')))
    ok_(path_startswith(_p('/a/b'), _p('/a/b')))
    ok_(path_startswith(_p('/a/b'), _p('/a/b/')))
    ok_(path_startswith(_p('/a/b/'), _p('/a/b')))
    ok_(path_startswith(_p('/a/b'), _p('/')))
    ok_(path_startswith(_p('/aaa/b/c'), _p('/aaa')))
    nok_(path_startswith(_p('/aaa/b/c'), _p('/aa')))
    nok_(path_startswith(_p('/a/b'), _p('/a/c')))
    nok_(path_startswith(_p('/a/b/c'), _p('/a/c')))
    # must not mix relative and abs
    assert_raises(ValueError, path_startswith, _p('a/b'), _p('/a'))
    assert_raises(ValueError, path_startswith, _p('/a/b'), _p('a'))


def test_path_is_subpath():
    ok_(path_is_subpath(_p('/a/b'), _p('/a')))
    ok_(path_is_subpath(_p('/a/b/c'), _p('/a')))
    nok_(path_is_subpath(_p('/a/b'), _p('/a/b')))
    nok_(path_is_subpath(_p('/a/b'), _p('/a/b/')))
    nok_(path_is_subpath(_p('/a/b/'), _p('/a/b')))
    ok_(path_is_subpath(_p('/a/b'), _p('/')))
    ok_(path_is_subpath(_p('/aaa/b/c'), _p('/aaa')))
    nok_(path_is_subpath(_p('/aaa/b/c'), _p('/aa')))
    nok_(path_is_subpath(_p('/a/b'), _p('/a/c')))
    nok_(path_is_subpath(_p('/a/b/c'), _p('/a/c')))
    # must not mix relative and abs
    assert_raises(ValueError, path_is_subpath, _p('a/b'), _p('/a'))
    assert_raises(ValueError, path_is_subpath, _p('/a/b'), _p('a'))


def test_probe_known_failure():

    # Note: we can't test the switch "datalad.tests.knownfailures.probe"
    # directly, since it was evaluated in the decorator already. So we need
    # to have different assertions in this test based on config and have it
    # tested across builds, which use different settings for that switch.

    @probe_known_failure
    def not_failing():
        pass

    @probe_known_failure
    def failing():
        raise AssertionError("Failed")

    switch = dl_cfg.obtain("datalad.tests.knownfailures.probe")

    if switch:
        # if probing is enabled the failing is considered to be expected and
        # therefore the decorated function doesn't actually fail:
        failing()
        # in opposition a function that doesn't fail raises an AssertionError:
        assert_raises(AssertionError, not_failing)
    else:
        # if probing is disabled it should just fail/pass as is:
        assert_raises(AssertionError, failing)
        not_failing()


def test_skip_if():

    def dummy():
        raise AssertionError

    assert_raises(AssertionError, dummy)
    # if cond is False, call the decorated function:
    assert_raises(AssertionError, skip_if(cond=False, method='raise')(dummy))
    # raises SkipTest if cond is True
    assert_raises(SkipTest, skip_if(cond=True, method='raise')(dummy))
    # but with method 'pass', there is neither SkipTest nor AssertionError.
    # Instead the function call is just skipped:
    skip_if(cond=True, method='pass')(dummy)
    # But if condition is False, the original function is still called:
    assert_raises(AssertionError, skip_if(cond=False, method='pass')(dummy))


def test_skip_known_failure():

    # Note: we can't test the switch "datalad.tests.knownfailures.skip"
    # directly, since it was evaluated in the decorator already. So we need
    # to have different assertions in this test based on config and have it
    # tested across builds, which use different settings for that switch.

    @skip_known_failure
    def failing():
        raise AssertionError("Failed")

    switch = dl_cfg.obtain("datalad.tests.knownfailures.skip")

    if switch:
        # if skipping is enabled, we shouldn't see the exception:
        failing()
    else:
        # if it's disabled, failing() is executed and therefore exception
        # is raised:
        assert_raises(AssertionError, failing)


def test_known_failure():

    @known_failure
    def failing():
        raise AssertionError("Failed")

    skip = dl_cfg.obtain("datalad.tests.knownfailures.skip")
    probe = dl_cfg.obtain("datalad.tests.knownfailures.probe")

    if skip:
        # skipping takes precedence over probing
        failing()
    elif probe:
        # if we probe a known failure it's okay to fail:
        failing()
    else:
        # not skipping and not probing results in the original failure:
        assert_raises(AssertionError, failing)


from datalad.utils import read_csv_lines


def test_known_failure_direct_mode():
    # Decorator is deprecated now and that is what we check
    from .utils_pytest import known_failure_direct_mode

    x = []
    with swallow_logs(new_level=logging.WARNING) as cml:
        @known_failure_direct_mode
        def failing():
            x.append('ok')
            raise AssertionError("Failed")

        assert_raises(AssertionError, failing)  # nothing is swallowed
        eq_(x, ['ok'])  # everything runs
        assert_in("Direct mode support is deprecated", cml.out)


@with_tempfile(content="h1 h2\nv1 2\nv2 3")
def test_read_csv_lines_basic(infile=None):
    # Just a basic test, next one with unicode
    gen = read_csv_lines(infile)
    ok_generator(gen)
    eq_(
        list(gen),
        [
            {u'h1': u'v1', u'h2': u'2'},
            {u'h1': u'v2', u'h2': u'3'},
        ]
    )


@with_tempfile(content=u"h1\th2\nv1\tдата".encode('utf-8'))
def test_read_csv_lines_tsv_unicode(infile=None):
    # Just a basic test, next one with unicode
    gen = read_csv_lines(infile)
    ok_generator(gen)
    eq_(
        list(gen),
        [
            {u'h1': u'v1', u'h2': u'дата'},
        ]
    )


@with_tempfile(content=u"h1\nv1\nv2")
def test_read_csv_lines_one_column(infile=None):
    # Just a basic test, next one with unicode
    eq_(
        list(read_csv_lines(infile)),
        [
            {u'h1': u'v1'},
            {u'h1': u'v2'},
        ]
    )


def _get_testm_tree(ind):
    """Generate a fake package with submodules

    We need to increment index for different tests since otherwise e.g.
    import_modules fails to import submodule if first import_module_from_file
    imports that one
    """
    return {
        'dltestm%d' % ind: {
            '__init__.py': '',
            'dlsub1': {'__init__.py': 'var = 1'},
            'dlsub2.py': 'var = 2'}
    }

@with_tree(tree=_get_testm_tree(1))
def test_import_modules(topdir=None):
    try:
        sys.path.append(topdir)
        mods = import_modules(['dlsub1', 'bogus'], 'dltestm1')
    finally:
        sys.path.pop(sys.path.index(topdir))
    eq_(len(mods), 1)
    eq_(mods[0].__name__, 'dltestm1.dlsub1')


@with_tree(tree=_get_testm_tree(2))
def test_import_module_from_file(topdir=None):
    with assert_raises(AssertionError):
        # we support only submodule files ending with .py ATM. TODO
        import_module_from_file(op.join(topdir, 'dltestm2', 'dlsub1'))

    dlsub2_path = op.join(topdir, 'dltestm2', 'dlsub2.py')
    mod = import_module_from_file(dlsub2_path)
    eq_(mod.__name__, 'dlsub2')  # we are not asking to import as submod of the dltestm1
    assert_in('dlsub2', sys.modules)

    try:
        sys.path.append(topdir)
        import dltestm2
        mod = import_module_from_file(dlsub2_path, pkg=dltestm2)
        eq_(mod.__name__, 'dltestm2.dlsub2')
        assert_in('dltestm2.dlsub2', sys.modules)
    finally:
        sys.path.pop(sys.path.index(topdir))


def test_import_modules_fail():
    # test that we log failures correctly
    failures = []
    import_modules(['bogus'], 'datalad', 'Fail {package}.{module}', failures.append)
    eq_(len(failures), 1)
    ok_startswith(failures[0], "Fail datalad.bogus: No module")


# Should be the last one since as discovered in NICEMAN might screw up coverage
def test_line_profile():
    skip_if_no_module('line_profiler')

    @line_profile
    def f(j):
        i = j + 1  # xyz
        return i

    with swallow_outputs() as cmo:
        assert_equal(f(3), 4)
        assert_equal(cmo.err, '')
        assert_in('i = j + 1  # xyz', cmo.out)


@with_tempfile(mkdir=True)
def test_dlabspath(path=None):
    if not has_symlink_capability():
        raise SkipTest
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    opath = opj(path, "origin")
    os.makedirs(opath)
    lpath = opj(path, "linked")
    os.symlink('origin', lpath)
    for d in opath, lpath:
        # regardless under which directory, all results should not resolve
        # anything
        eq_(d, dlabspath(d))
        # in the root of ds
        with chpwd(d):
            eq_(dlabspath("path"), opj(d, "path"))
            eq_(dlabspath("./path"), opj(d, "./path"))  # we do not normpath by default
            eq_(dlabspath("./path", norm=True), opj(d, "path"))


@with_tree({'1': 'content', 'd': {'2': 'more'}})
def test_get_open_files(p=None):
    pobj = Path(p)
    skip_if_no_module('psutil')
    eq_(get_open_files(p), {})
    f1 = pobj / '1'
    subd = pobj / 'd'
    with f1.open() as f:
        # since lsof does not care about PWD env var etc, paths
        # will not contain symlinks, we better realpath them
        # all before comparison
        eq_(get_open_files(p, log_open=40)[str(f1.resolve())].pid,
            os.getpid())

    assert not get_open_files(str(subd))

    if on_windows:
        # the remainder of the test assume a certain performance.
        # however, on windows get_open_files() can be very slow
        # (e.g. the first invocation in this test (above) can easily
        # take 30-50s). It is not worth slowing the tests to
        # accommodate this issue, given we have tested proper functioning
        # in principle already above).
        return

    # if we start a process within that directory, should get informed
    from subprocess import (
        PIPE,
        Popen,
    )
    from time import time
    t0 = time()
    proc = Popen([sys.executable, '-c',
                  r'import sys; sys.stdout.write("OK\n"); sys.stdout.flush();'
                  r'import time; time.sleep(10)'],
                 stdout=PIPE,
                 cwd=str(subd))
    # Assure that it started and we read the OK
    eq_(ensure_unicode(proc.stdout.readline().strip()), u"OK")
    assert time() - t0 < 5 # that we were not stuck waiting for process to finish
    eq_(get_open_files(p)[str(subd.resolve())].pid, proc.pid)
    eq_(get_open_files(subd)[str(subd.resolve())].pid, proc.pid)
    proc.terminate()
    assert_equal(get_open_files(str(subd)), {})


def test_map_items():
    def add10(x):
        return x + 10
    eq_(map_items(add10, {2: 3}), {12: 13})

    class Custom(object):
        """For testing with custom items possibly of varying length etc"""
        def __init__(self, items):
            self._items = list(items)

        def items(self):
            return self._items

    c = Custom([(1,), (2, 3), (4, 5, 6)])
    c_mapped = map_items(add10, c)
    assert type(c) is type(c_mapped)
    eq_(c_mapped.items(), [(11,), (12, 13), (14, 15, 16)])


def test_CMD_MAX_ARG():
    # 100 is arbitrarily large small integer ;)
    # if fails -- we are unlikely to be able to work on this system
    # and something went really wrong!
    assert_greater(CMD_MAX_ARG, 100)


@with_tempfile(mkdir=True)
def test_create_tree(path=None):
    content = u"мама мыла раму"
    create_tree(path, dict([
        ('1', content),
        ('sd', dict(
            [
            # right away an obscure case where we have both 1 and 1.gz
                ('1', content*2),
                ('1.gz', content*3),
                ('1.xz', content*4),
                ('1.lzma', content*5),
            ]
        )),
    ]))
    ok_file_has_content(op.join(path, '1'), content)
    ok_file_has_content(op.join(path, 'sd', '1'), content*2)
    ok_file_has_content(op.join(path, 'sd', '1.gz'), content*3, decompress=True)
    ok_file_has_content(op.join(path, 'sd', '1.xz'), content*4, decompress=True)
    ok_file_has_content(op.join(path, 'sd', '1.lzma'), content*5, decompress=True)


def test_never_fail():

    @never_fail
    def iamok(arg):
        return arg
    eq_(iamok(1), 1)

    @never_fail
    def ifail(arg):
        raise ValueError
    eq_(ifail(1), None)

    with patch.dict('os.environ', {'DATALAD_ALLOW_FAIL': '1'}):
        # decision to create failing or not failing function
        # is done at the time of decoration
        @never_fail
        def ifail2(arg):
            raise ValueError

        assert_raises(ValueError, ifail2, 1)


@pytest.mark.xfail(reason="TODO: for some reason fails on Travis")
@with_tempfile
def test_is_interactive(fout=None):
    # must not fail if one of the streams is no longer open:
    # https://github.com/datalad/datalad/issues/3267
    from datalad.cmd import (
        KillOutput,
        NoCapture,
        StdOutErrCapture,
        WitlessRunner,
    )
    from datalad.support.annexrepo import (
        AnnexInitOutput,
        AnnexJsonProtocol,
    )
    from datalad.support.gitrepo import GitProgress

    bools = ["False", "True"]

    def get_interactive(py_pre="", **run_kwargs):
        out = WitlessRunner().run(
            [sys.executable,
             "-c",
             py_pre +
             'from datalad.utils import is_interactive; '
             'f = open(%r, "w"); '
             'f.write(str(is_interactive())); '
             'f.close()'
             % fout
             ],
            **run_kwargs
        )
        with open(fout) as f:
            out = f.read()
        assert_in(out, bools)
        return bool(bools.index(out))

    # verify that NoCapture can make fully interactive execution
    # happen, also test the core protocols
    # (we can only be interactive in a runner, if the test execution
    # itself happens in an interactive environment)
    for proto, interactive in ((NoCapture,
                                # It is unclear why (on travis only) a child
                                # process can report to be interactive
                                # whenever the parent process is not.
                                # Maintain this test exception until
                                # someone can provide insight. The point of
                                # this test is to ensure that NoCapture
                                # in an interactive parent also keeps the
                                # child interactive, so this oddity is not
                                # relevant.
                                True if on_travis else is_interactive()),
                               (KillOutput, False),
                               (StdOutErrCapture, False),
                               (GitProgress, False),
                               (AnnexInitOutput, False),
                               (AnnexJsonProtocol, False)):
        eq_(get_interactive(protocol=proto),
            interactive,
            msg='{} -> {}'.format(str(proto), interactive))
    # and it must not crash if smth is closed
    for o in ('stderr', 'stdin', 'stdout'):
        eq_(get_interactive("import sys; sys.%s.close(); " % o), False)


def test_splitjoin_cmdline():
    # Do full round trip on a number of tricky samples
    for args in (
        ['cmd', '-o1', 'simple'],
        ['c o', r'\m', ''],
        ['c o', ' '],
    ):
        cmdline = join_cmdline(args)
        assert isinstance(cmdline, str)
        eq_(split_cmdline(cmdline), args)
    # assure that there is no needless quoting
    if on_windows:
        # in quote_cmdlinearg we always quote on Windows
        eq_(join_cmdline(['abc', 'def']), '"abc" "def"')
    else:
        eq_(join_cmdline(['abc', 'def']), 'abc def')


@skip_if_root
@with_tempfile
def test_obtain_write_permission(path=None):
    path = Path(path)

    # there's nothing at path yet:
    assert_raises(FileNotFoundError, obtain_write_permission, path)

    # Revoke write permission
    path.write_text("something")
    path.chmod(path.stat().st_mode & ~stat.S_IWRITE)
    assert_raises(PermissionError, path.write_text, "different thing")

    # Obtain and try again:
    obtain_write_permission(path)
    path.write_text("different thing")

    # Already having permission is no issue:
    obtain_write_permission(path)
    path.write_text("yet another thing")


@skip_if_root
@with_tempfile(mkdir=True)
def test_ensure_write_permission(path=None):

    # This is testing the usecase of write protected directories needed for
    # messing with an annex object tree (as done by the ORA special remote).
    # However, that doesn't work on Windows since we can't revoke write
    # permissions for the owner of a directory (at least on VFAT - may be
    # true for NTFS as well - don't know).
    # Hence, on windows/crippledFS only test on a file.

    dir_ = Path(path)
    if not on_windows and has_symlink_capability:
        # set up write-protected dir containing a file
        file_ = dir_ / "somefile"
        file_.write_text("whatever")
        dir_.chmod(dir_.stat().st_mode & ~stat.S_IWRITE)
        assert_raises(PermissionError, file_.unlink)

        # contextmanager lets us do it and restores permissions afterwards:
        mode_before = dir_.stat().st_mode
        with ensure_write_permission(dir_):
            file_.unlink()

        mode_after = dir_.stat().st_mode
        assert_equal(mode_before, mode_after)
        assert_raises(PermissionError, file_.write_text, "new file can't be "
                                                         "written")

        assert_raises(FileNotFoundError, ensure_write_permission(dir_ /
                      "non" / "existent").__enter__)

        # deletion within context doesn't let mode restoration fail:
        with ensure_write_permission(dir_):
            dir_.rmdir()

        dir_.mkdir()  # recreate, since next block is executed unconditionally

    # set up write-protected file:
    file2 = dir_ / "protected.txt"
    file2.write_text("unchangeable")
    file2.chmod(file2.stat().st_mode & ~stat.S_IWRITE)
    assert_raises(PermissionError, file2.write_text, "modification")

    # within context we can:
    with ensure_write_permission(file2):
        file2.write_text("modification")

    # mode is restored afterwards:
    assert_raises(PermissionError, file2.write_text, "modification2")
