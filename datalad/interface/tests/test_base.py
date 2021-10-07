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

import argparse
import unittest.mock as mock
from datalad.tests.utils import (
    assert_in,
    assert_not_in,
    eq_,
    ok_,
    patch_config,
    swallow_outputs,
    with_tempfile,
)
from datalad.utils import (
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
    update_docstring_with_parameters,
)
from argparse import Namespace


def _args(**kwargs):
    return Namespace(
        # ATM duplicates definitions done by cmdline.main and
        # required by code logic to be defined. (should they?)
        #
        # TODO: The common options are now added by
        # cmdline.helpers.parser_add_common_options(), which can be reused by
        # tests.
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
            # with dissolution of _OLD_STYLE_COMMANDS yoh yet to find
            # a real interface which had return_type (defined in
            # eval_defaults and eval_params) but no @eval_results
            # eq_(kwargs['return_type'], "generator")
            eq_(arg, "nothing")
            yield "nothing is"
            yield "magical"

    # just to be sure no evil spirits chase away our Dummy
    val = DummyOne.call_from_parser(_new_args(arg="nothing"))
    eq_(val, ["nothing is", "magical"])


def test_call_from_parser_result_filter():
    class DummyOne(Interface):
        @staticmethod
        def __call__(**kwargs):
            yield kwargs

    # call_from_parser doesn't add result_filter to the keyword arguments
    assert_not_in("result_filter",
                  DummyOne.call_from_parser(_new_args())[0])
    # with dissolution of _OLD_STYLE_COMMANDS and just relying on having
    # @eval_results, no result_filter is added, since those commands are
    # not guaranteed to return/yield any record suitable for filtering.
    # The effect is the same -- those "common" options are not really applicable
    # to Interface's which do not return/yield expected records
    assert_not_in("result_filter",
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

    ds = Dataset(path).create()
    out = WitlessRunner(cwd=path).run(
        ["datalad", "--output-format=tailored", "status"],
        protocol=StdOutCapture)
    out_lines = out['stdout'].splitlines()
    ok_(out_lines)
    eq_(len(out_lines), len(set(out_lines)))

    with swallow_outputs() as cmo:
        ds.status(return_type="list", result_renderer="tailored")
        eq_(out_lines, cmo.out.splitlines())


def test_update_docstring_with_parameters_no_kwds():
    from datalad.support.param import Parameter

    def fn(pos0):
        "fn doc"

    assert_not_in("3", fn.__doc__)
    # Call doesn't crash when there are no keyword arguments.
    update_docstring_with_parameters(
        fn,
        dict(pos0=Parameter(doc="pos0 param doc"),
             pos1=Parameter(doc="pos1 param doc")),
        add_args={"pos1": 3})
    assert_in("3", fn.__doc__)


def test_update_docstring_with_parameters_single_line_prefix():
    from datalad.support.param import Parameter

    def fn(pos0, pos1):
        pass

    update_docstring_with_parameters(
        fn,
        dict(pos0=Parameter(doc="pos0 param doc"),
             pos1=Parameter(doc="pos1 param doc")),
        prefix="This is a single line.",
    )
    assert_in("This is a single line.\n\nParameters\n", fn.__doc__)


def check_call_from_parser_pos_arg_underscore(how):
    from datalad.cmdline.helpers import parser_add_common_options
    from datalad.support.param import Parameter

    kwds = {"doc": "pos_arg doc"}
    if how == "dest":
        kwds["dest"] = "pos_arg"
    elif how == "args":
        kwds["args"] = ("pos_arg",)
    elif how != "bare":
        raise AssertionError("Unrecognized how: {}".format(how))

    class Cmd(Interface):

        _params_ = dict(
            pos_arg=Parameter(**kwds))

        def __call__(pos_arg, **kwargs):
            return pos_arg

    parser = argparse.ArgumentParser()
    parser_add_common_options(parser)
    Cmd.setup_parser(parser)
    args = parser.parse_args(["val"])
    eq_(Cmd.call_from_parser(args),
        "val")


def test_call_from_parser_pos_arg_underscore():
    for how in "bare", "dest", "args":
        yield check_call_from_parser_pos_arg_underscore, how
