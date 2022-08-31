# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os

from ...tests.utils_pytest import (
    SkipTest,
    assert_raises,
    eq_,
    with_tempfile,
)
from ...utils import (
    chpwd,
    on_windows,
    rmtree,
)
from ..path import (
    abspath,
    curdir,
    get_parent_paths,
    robust_abspath,
    split_ext,
)

import pytest


@with_tempfile(mkdir=True)
def test_robust_abspath(tdir=None):
    with chpwd(tdir):
        eq_(robust_abspath(curdir), tdir)
        try:
            if os.environ.get('DATALAD_ASSERT_NO_OPEN_FILES'):
                raise Exception("cannot test under such pressure")
            rmtree(tdir)
        except Exception as exc:
            # probably windows or above exception
            raise SkipTest(
                "Cannot test in current environment") from exc

        assert_raises(OSError, abspath, curdir)
        eq_(robust_abspath(curdir), tdir)


def test_split_ext():
    eq_(split_ext("file"), ("file", ""))

    eq_(split_ext("file.py"), ("file", ".py"))
    eq_(split_ext("file.tar.gz"), ("file", ".tar.gz"))
    eq_(split_ext("file.toolong.gz"), ("file.toolong", ".gz"))

    eq_(split_ext("file.a.b.c.d"), ("file", ".a.b.c.d"))
    eq_(split_ext("file.a.b.cccc.d"), ("file", ".a.b.cccc.d"))
    eq_(split_ext("file.a.b.ccccc.d"), ("file.a.b.ccccc", ".d"))

    eq_(split_ext("file.a.b..c"), ("file", ".a.b..c"))


@pytest.mark.parametrize("sep", [None, '/', '\\'])
def test_get_parent_paths(sep):
    if sep is None:
        gpp = get_parent_paths
    else:
        from functools import partial
        gpp = partial(get_parent_paths, sep=sep)

    # sanity/border checks
    eq_(gpp([], []), [])
    eq_(gpp([], ['a']), [])
    eq_(gpp(['a'], ['a']), ['a'])

    # Helper to provide testing across different seps and platforms while
    # specifying only POSIX paths here in the test
    def _p(path):
        if sep is None:
            return path
        else:
            return path.replace('/', sep)
    _pp = lambda paths: list(map(_p, paths))

    # no absolute paths anywhere
    if on_windows:
        assert_raises(ValueError, gpp, 'C:\\a', ['a'])
        assert_raises(ValueError, gpp, ['a'], 'C:\\a')
    elif sep != '\\':  # \ does not make it absolute
        assert_raises(ValueError, gpp, _p('/a'), ['a'])
        assert_raises(ValueError, gpp, ['a'], [_p('/a')])
    assert_raises(ValueError, gpp, [_p('a//a')], ['a'])
    # dups the actual code but there is no other way AFAIK
    asep = {'/': '\\', None: '\\', '\\': '/'}[sep]
    assert_raises(ValueError, gpp, [f'a{asep}a'], ['a'])

    paths = _pp(['a', 'a/b', 'a/b/file', 'c', 'd/sub/123'])

    eq_(gpp(paths, []), paths)
    eq_(gpp(paths, [], True), [])

    # actually a tricky one!  we should check in descending lengths etc
    eq_(gpp(paths, paths), paths)
    # every path is also its own parent
    eq_(gpp(paths, paths, True), paths)

    # subdatasets not for every path -- multiple paths hitting the same parent,
    # and we will be getting only a single entry
    # to mimic how git ls-tree operates
    eq_(gpp(paths, ['a']), ['a', 'c', _p('d/sub/123')])
    eq_(gpp(paths, ['a'], True), ['a'])

    # and we get the deepest parent
    eq_(gpp(_pp(['a/b/file', 'a/b/file2']), _pp(['a', 'a/b'])), _pp(['a/b']))
