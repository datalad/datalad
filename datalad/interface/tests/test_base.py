# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test the holy grail of interfaces

"""

import unittest.mock as mock
from datalad.tests.utils import *
from datalad.utils import (
    swallow_outputs,
    updated,
)
from datalad.cmd import (
    StdOutCapture,
    WitlessRunner,
)

from ..base import (
    Interface,
    nadict,
    nagen,
    NA_STRING,
)
from argparse import Namespace


def _args(**kwargs):
    return Namespace(
        # ATM duplicates definitions done by cmdline.main and
        # required by code logic to be defined. (should they?)
        **updated(
            dict(
                common_output_format="default"
            ),
            kwargs
        )
    )


def _new_args(**kwargs):
    # A few more must be specified
    return _args(
        **updated(
            dict(
                common_on_failure=None,  # ['ignore', 'continue', 'stop']
                common_report_status=None,  # ['all', 'success', 'failure', 'ok', 'notneeded', 'impossible', 'error']
                common_report_type=None,  # ['dataset', 'file']
            ),
            kwargs
        )
    )


def test_call_from_parser_old_style():
    # test that old style commands are invoked without any additional arguments
    class DummyOne(Interface):
        @staticmethod
        def __call__(arg=None):
            eq_(arg, "nothing")
            return "magical"
    with mock.patch.object(Interface, '_OLDSTYLE_COMMANDS', ('DummyOne',)):
        val = DummyOne.call_from_parser(_args(arg="nothing"))
        eq_(val, "magical")


def test_call_from_parser_old_style_generator():
    # test that old style commands are invoked without any additional arguments
    class DummyOne(Interface):
        @staticmethod
        def __call__(arg=None):
            eq_(arg, "nothing")
            yield "nothing is"
            yield "magical"
    with mock.patch.object(Interface, '_OLDSTYLE_COMMANDS', ('DummyOne',)):
        val = DummyOne.call_from_parser(_args(arg="nothing"))
        eq_(val, ["nothing is", "magical"])


def test_call_from_parser_default_args():
    class DummyOne(Interface):
        # explicitly without @eval_results
        @staticmethod
        def __call__(arg=None, **kwargs):
            eq_(kwargs['common_on_failure'], None)
            eq_(kwargs['common_report_status'], None)
            eq_(kwargs['common_report_type'], None)
            # and even those we didn't pass
            eq_(kwargs['common_output_format'], "default")
            eq_(kwargs['return_type'], "generator")
            eq_(arg, "nothing")
            yield "nothing is"
            yield "magical"

    # just to be sure no evil spirits chase away our Dummy
    with mock.patch.object(Interface, '_OLDSTYLE_COMMANDS', tuple()):
        val = DummyOne.call_from_parser(_new_args(arg="nothing"))
        eq_(val, ["nothing is", "magical"])


def test_call_from_parser_result_filter():
    class DummyOne(Interface):
        @staticmethod
        def __call__(**kwargs):
            yield kwargs

    with mock.patch.object(Interface, '_OLDSTYLE_COMMANDS', tuple()):
        # call_from_parser doesn't add result_filter to the keyword arguments
        # unless a CLI option sets it to a non-None value.
        assert_not_in("result_filter",
                      DummyOne.call_from_parser(_new_args())[0])
        assert_in("result_filter",
                  DummyOne.call_from_parser(
                      _new_args(common_report_type="dataset"))[0])


def test_get_result_filter_arg_vs_config():
    # just tests that we would be obtaining the same constraints via
    # cmdline argument or via config variable.  With cmdline overloading
    # config
    f = Interface._get_result_filter
    eq_(f(_new_args()), None)  # by default, no filter

    for v in "success", "failure", "ok", "notneeded", "error":
        cargs = f(_new_args(common_report_status=v))
        assert cargs is not None
        with patch_config({"datalad.runtime.report-status": v}):
            ccfg = f(_new_args())
            ccfg_none = f(_new_args(common_report_status="all"))
        # cannot compare directly but at least could verify based on repr
        print("%s -> %s" % (v, repr(cargs)))
        eq_(repr(cargs), repr(ccfg))
        # and if 'all' - none filter
        eq_(None, ccfg_none)

        # and we overload the "error" in config
        with patch_config({"datalad.runtime.report-status": "error"}):
            cargs_overload = f(_new_args(common_report_status=v))
        eq_(repr(cargs), repr(cargs_overload))


def test_nagen():
    na = nagen()
    eq_(str(na), NA_STRING)
    eq_(repr(na), 'nagen()')
    assert na.unknown is na
    assert na['unknown'] is na

    eq_(str(nagen('-')), '-')


def test_nadict():
    d = nadict({1: 2})
    eq_(d[1], 2)
    eq_(str(d[2]), NA_STRING)


@with_tempfile(mkdir=True)
def test_status_custom_summary_no_repeats(path):
    from datalad.api import Dataset
    from datalad.core.local.status import Status

    # This regression test depends on the command having a custom summary
    # renderer *and* the particular call producing summary output. status()
    # having this method doesn't guarantee that it is still an appropriate
    # command for this test, but it's at least a necessary condition.
    ok_(hasattr(Status, "custom_result_summary_renderer"))

    # Note: This test was added on a branch without a60bf7274a (BF: Don't be
    # silent in default renderer when everything is clean, 2020-01-30), but
    # once merged into a branch with that commit, the block below and --annex
    # could be dropped.
    ds = Dataset(path).create()
    (ds.pathobj / "foo").write_text("foo content")
    ds.save()

    out = WitlessRunner(cwd=path).run(
        ["datalad", "--output-format=tailored", "status", "--annex"],
        protocol=StdOutCapture)
    out_lines = out['stdout'].splitlines()
    eq_(len(out_lines), len(set(out_lines)))
