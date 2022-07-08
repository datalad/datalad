# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import os.path as op
from itertools import product
from unittest.mock import patch

from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    assert_in,
    eq_,
    swallow_logs,
    with_tree,
)

from ..globbedpaths import GlobbedPaths


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


bOBSCURE_FILENAME = f"b{OBSCURE_FILENAME}.dat"


@with_tree(tree={"1.txt": "",
                 "2.dat": "",
                 "3.txt": "",
                 bOBSCURE_FILENAME: "",
                 "subdir": {"1.txt": "", "2.txt": "", "subsub": {"3.dat": ""}}})
def test_globbedpaths(path=None):
    dotdir = op.curdir + op.sep

    for patterns, expected in [
            (["1.txt", "2.dat"], {"1.txt", "2.dat"}),
            ([dotdir + "1.txt", "2.dat"], {dotdir + "1.txt", "2.dat"}),
            (["*.txt", "*.dat"], {"1.txt", "2.dat", bOBSCURE_FILENAME, "3.txt"}),
            ([dotdir + "*.txt", "*.dat"],
             {dotdir + "1.txt", "2.dat", bOBSCURE_FILENAME, dotdir + "3.txt"}),
            ([op.join("subdir", "*.txt")],
             {op.join("subdir", "1.txt"), op.join("subdir", "2.txt")}),
            (["subdir" + op.sep], {"subdir" + op.sep}),
            ([dotdir + op.join("subdir", "*.txt")],
             {dotdir + op.join(*ps)
              for ps in [("subdir", "1.txt"), ("subdir", "2.txt")]}),
            (["*.txt"], {"1.txt", "3.txt"}),
            ([op.join("subdir", "**")],
             {op.join(*ps)
              for ps in [("subdir" + op.sep,), ("subdir", "subsub"),
                         ("subdir", "1.txt"), ("subdir", "2.txt"),
                         ("subdir", "subsub", "3.dat")]}),
            ([dotdir + op.join("**", "*.dat")],
             {dotdir + op.join("2.dat"), dotdir + bOBSCURE_FILENAME,
              dotdir + op.join("subdir", "subsub", "3.dat")})]:
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
            # Patterns that don't match are retained by default.
            (["amiss"], {"amiss"})]:
        gp = GlobbedPaths(patterns, pwd=subdir_path)
        eq_(set(gp.expand()), expected)
        eq_(set(gp.expand(full=True)),
            {op.join(subdir_path, p) for p in expected})

    # Full patterns still get returned as relative to pwd.
    gp = GlobbedPaths([op.join(path, "*.dat")], pwd=path)
    eq_(gp.expand(), ["2.dat", bOBSCURE_FILENAME])

    # "." gets special treatment.
    gp = GlobbedPaths([".", "*.dat"], pwd=path)
    eq_(set(gp.expand()), {"2.dat", bOBSCURE_FILENAME, "."})
    eq_(gp.expand(dot=False), ["2.dat", bOBSCURE_FILENAME])
    gp = GlobbedPaths(["."], pwd=path, expand=False)
    eq_(gp.expand(), ["."])
    eq_(gp.paths, ["."])

    # We can the glob outputs.
    glob_results = {"z": "z",
                    "a": ["x", "d", "b"]}
    with patch('glob.glob', lambda k, **kwargs: glob_results[k]):
        gp = GlobbedPaths(["z", "a"])
        eq_(gp.expand(), ["z", "b", "d", "x"])

    # glob expansion for paths property is determined by expand argument.
    for expand, expected in [(True, ["2.dat", bOBSCURE_FILENAME]),
                             (False, ["*.dat"])]:
        gp = GlobbedPaths(["*.dat"], pwd=path, expand=expand)
        eq_(gp.paths, expected)

    with swallow_logs(new_level=logging.DEBUG) as cml:
        GlobbedPaths(["not here"], pwd=path).expand()
        assert_in("No matching files found for 'not here'", cml.out)


@with_tree(tree={"1.txt": "", "2.dat": "", "3.txt": ""})
def test_globbedpaths_misses(path=None):
    gp = GlobbedPaths(["amiss"], pwd=path)
    eq_(gp.expand_strict(), [])
    eq_(gp.misses, ["amiss"])
    eq_(gp.expand(include_misses=True), ["amiss"])

    # miss at beginning
    gp = GlobbedPaths(["amiss", "*.txt", "*.dat"], pwd=path)
    eq_(gp.expand_strict(), ["1.txt", "3.txt", "2.dat"])
    eq_(gp.expand(include_misses=True),
        ["amiss", "1.txt", "3.txt", "2.dat"])

    # miss in middle
    gp = GlobbedPaths(["*.txt", "amiss", "*.dat"], pwd=path)
    eq_(gp.expand_strict(), ["1.txt", "3.txt", "2.dat"])
    eq_(gp.misses, ["amiss"])
    eq_(gp.expand(include_misses=True),
        ["1.txt", "3.txt", "amiss", "2.dat"])

    # miss at end
    gp = GlobbedPaths(["*.txt", "*.dat", "amiss"], pwd=path)
    eq_(gp.expand_strict(), ["1.txt", "3.txt", "2.dat"])
    eq_(gp.misses, ["amiss"])
    eq_(gp.expand(include_misses=True),
        ["1.txt", "3.txt", "2.dat", "amiss"])

    # miss at beginning, middle, and end
    gp = GlobbedPaths(["amiss1", "amiss2", "*.txt", "amiss3", "*.dat",
                       "amiss4"],
                      pwd=path)
    eq_(gp.expand_strict(), ["1.txt", "3.txt", "2.dat"])
    eq_(gp.misses, ["amiss1", "amiss2", "amiss3", "amiss4"])
    eq_(gp.expand(include_misses=True),
        ["amiss1", "amiss2", "1.txt", "3.txt", "amiss3", "2.dat", "amiss4"])

    # Property expands if needed.
    gp = GlobbedPaths(["amiss"], pwd=path)
    eq_(gp.misses, ["amiss"])


@with_tree(tree={"adir": {},
                 "bdir": {},
                 "other": {},
                 "1.txt": "", "2.dat": "", "3.txt": ""})
def test_globbedpaths_partial_matches(path=None):
    gp = GlobbedPaths([op.join("?dir", "*.txt"), "*.txt"], pwd=path)
    eq_(gp.expand_strict(), ["1.txt", "3.txt"])

    expected_partial = ["adir" + op.sep, "bdir" + op.sep]
    eq_(gp.partial_hits, expected_partial)
    eq_(gp.expand(include_partial=True),
        expected_partial + ["1.txt", "3.txt"])

    # Property expands if needed.
    gp = GlobbedPaths([op.join("?dir", "*.txt")], pwd=path)
    eq_(gp.partial_hits, expected_partial)


@with_tree(tree={"1.txt": "",
                 "2.dat": "",
                 "3.txt": "",
                 "foo.dat": ""})
def test_globbedpaths_cached(path=None):
    # Smoke test to trigger cache handling.
    gp = GlobbedPaths([op.join("?", ".dat"), "*.txt"], pwd=path)
    for full, partial, misses in product([False, True], repeat=3):
        eq_(gp.expand(full=full,
                      include_misses=misses,
                      include_partial=partial),
            gp.expand(full=full,
                      include_misses=misses,
                      include_partial=partial))
