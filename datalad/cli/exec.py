"""Call a command interface

Provide a callable to register in a cmdline parser, for executing
a parameterized command call.
"""

# ATTN!
# Top-level inputs should be minimized. This module must be imported
# for parser construction, but the key function call_from_parser()
# is only executed when a command is actually engaged -- but not
# for a help action.
# Therefore no additional top-level imports beyond those already
# caused unconditionally by .main, and .parser.

from datalad import cfg
from datalad.interface.base import is_api_arg
from datalad.utils import getargspec

# only imported during command execution
# .interface._has_eval_results_call
# from .utils import EnsureKeyChoice

# special-case imports
# .renderer.DefaultOutputRenderer
# from datalad.ui import ui
# from .exceptions import CapturedException


def call_from_parser(cls, args):
    """Executable to be registered with the parser for a particular command

    Parameters
    ----------
    cls : Interface
      Class implementing a particular interface.
    args : Namespace
      Populated argparse namespace instance.

    Returns
    -------
    iterable
      Returns the iterable return by an command's implementation of
      ``__call__()``. It is unwound, in case of a generator being
      returned to actually trigger the underlying processing.
    """
    # XXX needs safety check for name collisions
    import inspect

    from datalad.interface.base import _has_eval_results_call

    argspec = getargspec(cls.__call__, include_kwonlyargs=True)
    if argspec.keywords is None:
        # no **kwargs in the call receiver, pull argnames from signature
        argnames = argspec.args
    else:
        # common options
        # XXX define or better get from elsewhere
        # ultimately .common_args.common_args could be used, but
        # it is presently unclear what is being excluded here (incomplete set)
        common_opts = ('change_path', 'common_debug', 'common_idebug', 'func',
                       'help', 'log_level', 'logger',
                       'result_renderer', 'subparser')
        argnames = [name for name in dir(args)
                    if not (name.startswith('_') or name in common_opts)]
    kwargs = {k: getattr(args, k)
              for k in argnames
              # some arguments might be Python-only and do not appear in the
              # parser Namespace
              if hasattr(args, k) and is_api_arg(k)}
    # we are coming from the entry point, this is the toplevel command,
    # let it run like generator so we can act on partial results quicker
    # TODO remove following condition test when transition is complete and
    # run indented code unconditionally
    if _has_eval_results_call(cls):
        # set all common args explicitly  to override class defaults
        # that are tailored towards the the Python API
        kwargs['return_type'] = 'generator'
        kwargs['result_xfm'] = None
        if '{' in args.common_result_renderer:
            from .renderer import DefaultOutputRenderer

            # stupid hack, could and should become more powerful
            kwargs['result_renderer'] = DefaultOutputRenderer(
                args.common_result_renderer)
        else:
            # allow commands to override the default, unless something other
            # than the default 'tailored' is requested
            kwargs['result_renderer'] = \
                args.common_result_renderer \
                    if args.common_result_renderer != 'tailored' \
                    else getattr(cls, 'result_renderer', 'generic')
        if args.common_on_failure:
            kwargs['on_failure'] = args.common_on_failure
        # compose filter function from to be invented cmdline options
        res_filter = _get_result_filter(args)
        if res_filter is not None:
            # Don't add result_filter if it's None because then
            # eval_results can't distinguish between --report-{status,type}
            # not specified via the CLI and None passed via the Python API.
            kwargs['result_filter'] = res_filter

    ret = cls.__call__(**kwargs)
    if inspect.isgenerator(ret):
        ret = list(ret)
    return ret


def _get_result_filter(args):
    from datalad.support.constraints import EnsureKeyChoice

    result_filter = None
    if args.common_report_status or 'datalad.runtime.report-status' in cfg:
        report_status = args.common_report_status or \
                        cfg.obtain('datalad.runtime.report-status')
        if report_status == "all":
            pass  # no filter
        elif report_status == 'success':
            result_filter = EnsureKeyChoice('status', ('ok', 'notneeded'))
        elif report_status == 'failure':
            result_filter = EnsureKeyChoice('status',
                                           ('impossible', 'error'))
        else:
            result_filter = EnsureKeyChoice('status', (report_status,))
    if args.common_report_type:
        tfilt = EnsureKeyChoice('type', tuple(args.common_report_type))
        result_filter = result_filter & tfilt if result_filter else tfilt
    return result_filter
