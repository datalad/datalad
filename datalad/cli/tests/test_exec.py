import argparse
from argparse import Namespace

import pytest

from datalad.interface.base import Interface
from datalad.support.param import Parameter
from datalad.tests.utils_pytest import (
    assert_not_in,
    eq_,
    patch_config,
)
from datalad.utils import updated

from ..exec import (
    _get_result_filter,
    call_from_parser,
)
from ..parser import (
    parser_add_common_options,
    setup_parser_for_interface,
)


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
                common_result_renderer="generic"
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
    val = call_from_parser(DummyOne, _args(arg="nothing"))
    eq_(val, "magical")


def test_call_from_parser_old_style_generator():
    # test that old style commands are invoked without any additional arguments
    class DummyOne(Interface):
        @staticmethod
        def __call__(arg=None):
            eq_(arg, "nothing")
            yield "nothing is"
            yield "magical"
    val = call_from_parser(DummyOne, _args(arg="nothing"))
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
            eq_(kwargs['common_result_renderer'], "generic")
            # with dissolution of _OLD_STYLE_COMMANDS yoh yet to find
            # a real interface which had return_type (defined in
            # eval_params) but no @eval_results
            # eq_(kwargs['return_type'], "generator")
            eq_(arg, "nothing")
            yield "nothing is"
            yield "magical"

    # just to be sure no evil spirits chase away our Dummy
    val = call_from_parser(DummyOne, _new_args(arg="nothing"))
    eq_(val, ["nothing is", "magical"])


def test_call_from_parser_result_filter():
    class DummyOne(Interface):
        @staticmethod
        def __call__(**kwargs):
            yield kwargs

    # call_from_parser doesn't add result_filter to the keyword arguments
    assert_not_in("result_filter",
                  call_from_parser(DummyOne, _new_args())[0])
    # with dissolution of _OLD_STYLE_COMMANDS and just relying on having
    # @eval_results, no result_filter is added, since those commands are
    # not guaranteed to return/yield any record suitable for filtering.
    # The effect is the same -- those "common" options are not really applicable
    # to Interface's which do not return/yield expected records
    assert_not_in(
        "result_filter",
        call_from_parser(
            DummyOne,
            _new_args(common_report_type="dataset"))[0])


def test_get_result_filter_arg_vs_config():
    # just tests that we would be obtaining the same constraints via
    # cmdline argument or via config variable.  With cmdline overloading
    # config
    f = _get_result_filter
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


@pytest.mark.parametrize(
    "how",
    ["bare", "dest", "args"]
)
def test_call_from_parser_pos_arg_underscore(how):
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
    setup_parser_for_interface(parser, Cmd)
    args = parser.parse_args(["val"])
    eq_(call_from_parser(Cmd, args),
        "val")

