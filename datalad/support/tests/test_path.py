# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
from ..path import (
    abspath,
    curdir,
    get_parent_paths,
    robust_abspath,
    split_ext,
)
from ...utils import (
    chpwd,
    rmtree,
)
from ...tests.utils import (
    assert_raises,
    eq_,
    with_tempfile,
    SkipTest,
)


@with_tempfile(mkdir=True)
def test_robust_abspath(tdir):
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


def test_get_parent_paths():
    gpp = get_parent_paths

    # sanity/border checks
    eq_(gpp([], []), [])
    eq_(gpp([], ['a']), [])
    eq_(gpp(['a'], ['a']), ['a'])
    assert_raises(ValueError, gpp, '/a', ['a'])

    paths = ['a', 'a/b', 'a/b/file', 'c', 'd/sub/123']

    eq_(gpp(paths, []), paths)
    eq_(gpp(paths, [], True), [])

    # actually a tricky one!  we should check in descending lengths etc
    eq_(gpp(paths, paths), paths)
    # every path is also its own parent
    eq_(gpp(paths, paths, True), paths)

    # subdatasets not for every path -- multiple paths hitting the same parent,
    # and we will be getting only a single entry
    # to mimic how git ls-tree operates
    eq_(gpp(paths, ['a']), ['a', 'c', 'd/sub/123'])
    eq_(gpp(paths, ['a'], True), ['a'])

    # and we get the deepest parent
    eq_(gpp(['a/b/file', 'a/b/file2'], ['a', 'a/b']), ['a/b'])
