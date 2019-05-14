# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test GlobbedPaths
"""

__docformat__ = 'restructuredtext'

import logging
from mock import patch
import os.path as op

from datalad.support.globbedpaths import GlobbedPaths
from datalad.tests.utils import assert_in
from datalad.tests.utils import eq_
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import with_tree


def test_globbedpaths_get_sub_patterns():
    gp = GlobbedPaths([], "doesn't matter")
    for pat, expected in [
            # If there are no patterns in the directory component, we get no
            # sub-patterns.
            ("", []),
            ("nodir", []),
            (op.join("nomagic", "path"), []),
            (op.join("nomagic", "path*"), []),
            # Create sub-patterns from leading path, successively dropping the
            # right-most component.
            (op.join("s*", "path"), ["s*" + op.sep]),
            (op.join("s", "ss*", "path"), [op.join("s", "ss*") + op.sep]),
            (op.join("s", "ss*", "path*"), [op.join("s", "ss*") + op.sep]),
            (op.join("s", "ss*" + op.sep), []),
            (op.join("s*", "ss", "path*"),
             [op.join("s*", "ss") + op.sep,
              "s*" + op.sep]),
            (op.join("s?", "ss", "sss*", "path*"),
             [op.join("s?", "ss", "sss*") + op.sep,
              op.join("s?", "ss") + op.sep,
              "s?" + op.sep])]:
        eq_(gp._get_sub_patterns(pat), expected)


@with_tree(tree={"1.txt": "",
                 "2.dat": "",
                 "3.txt": "",
                 # Avoid OBSCURE_FILENAME to avoid windows-breakage (gh-2929).
                 u"bβ.dat": "",
                 "subdir": {"1.txt": "", "2.txt": ""}})
def test_globbedpaths(path):
    dotdir = op.curdir + op.sep

    for patterns, expected in [
            (["1.txt", "2.dat"], {"1.txt", "2.dat"}),
            ([dotdir + "1.txt", "2.dat"], {dotdir + "1.txt", "2.dat"}),
            (["*.txt", "*.dat"], {"1.txt", "2.dat", u"bβ.dat", "3.txt"}),
            ([dotdir + "*.txt", "*.dat"],
             {dotdir + "1.txt", "2.dat", u"bβ.dat", dotdir + "3.txt"}),
            (["subdir/*.txt"], {"subdir/1.txt", "subdir/2.txt"}),
            ([dotdir + "subdir/*.txt"],
             {dotdir + p for p in ["subdir/1.txt", "subdir/2.txt"]}),
            (["*.txt"], {"1.txt", "3.txt"})]:
        gp = GlobbedPaths(patterns, pwd=path)
        eq_(set(gp.expand()), expected)
        eq_(set(gp.expand(full=True)),
            {op.join(path, p) for p in expected})

    pardir = op.pardir + op.sep
    subdir_path = op.join(path, "subdir")
    for patterns, expected in [
            (["*.txt"], {"1.txt", "2.txt"}),
            ([dotdir + "*.txt"], {dotdir + p for p in ["1.txt", "2.txt"]}),
            ([pardir + "*.txt"], {pardir + p for p in ["1.txt", "3.txt"]}),
            ([dotdir + pardir + "*.txt"],
             {dotdir + pardir + p for p in ["1.txt", "3.txt"]}),
            (["subdir/"], {"subdir/"})]:
        gp = GlobbedPaths(patterns, pwd=subdir_path)
        eq_(set(gp.expand()), expected)
        eq_(set(gp.expand(full=True)),
            {op.join(subdir_path, p) for p in expected})

    # Full patterns still get returned as relative to pwd.
    gp = GlobbedPaths([op.join(path, "*.dat")], pwd=path)
    eq_(gp.expand(), ["2.dat", u"bβ.dat"])

    # "." gets special treatment.
    gp = GlobbedPaths([".", "*.dat"], pwd=path)
    eq_(set(gp.expand()), {"2.dat", u"bβ.dat", "."})
    eq_(gp.expand(dot=False), ["2.dat", u"bβ.dat"])
    gp = GlobbedPaths(["."], pwd=path, expand=False)
    eq_(gp.expand(), ["."])
    eq_(gp.paths, ["."])

    # We can the glob outputs.
    glob_results = {"z": "z",
                    "a": ["x", "d", "b"]}
    with patch('glob.glob', glob_results.get):
        gp = GlobbedPaths(["z", "a"])
        eq_(gp.expand(), ["z", "b", "d", "x"])

    # glob expansion for paths property is determined by expand argument.
    for expand, expected in [(True, ["2.dat", u"bβ.dat"]),
                             (False, ["*.dat"])]:
        gp = GlobbedPaths(["*.dat"], pwd=path, expand=expand)
        eq_(gp.paths, expected)

    with swallow_logs(new_level=logging.DEBUG) as cml:
        GlobbedPaths(["not here"], pwd=path).expand()
        assert_in("No matching files found for 'not here'", cml.out)
