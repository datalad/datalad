# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

import logging
lgr = logging.getLogger('datalad.cmdline')

lgr.log(5, "Importing cmdline.main")

import argparse
from collections import defaultdict
import sys
import os

import datalad

from ..support.exceptions import (
    CapturedException,
    InsufficientArgumentsError,
    IncompleteResultsError,
    CommandError,
)
from ..utils import (
    chpwd,
    on_msys_tainted_paths,
    setup_exceptionhook,
)
from .helpers import (
    ArgumentParserDisableAbbrev,
    _fix_datalad_ri,
    _maybe_get_interface_subparser,
    _maybe_get_single_subparser,
    _parse_overrides_from_cmdline,
    get_description_with_cmd_summary,
    parser_add_common_options,
    parser_add_common_opt,
    strip_arg_from_argv,
)


# TODO:  OPT look into making setup_parser smarter to become faster
# Now it seems to take up to 200ms to do all the parser setup
# even though it might not be necessary to know about all the commands etc.
# I wondered if it could somehow decide on what commands to worry about etc
# by going through sys.args first
def setup_parser(
        cmdlineargs,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        return_subparsers=False,
        # Was this triggered by argparse?
        completing=False,
        # prevent loading of extension entrypoints when --help is requested
        # this is enabled when building docs to avoid pollution of generated
        # manpages with extensions commands (that should appear in their own
        # docs, but not in the core datalad package docs)
        help_ignore_extensions=False):
    """
    The holy grail of establishing CLI for DataLad's Interfaces

    Parameters
    ----------
    cmdlineargs:
    formatter_class:
    return_subparsers: bool, optional
      is used ATM only by BuildManPage in _datalad_build_support
    completing:
    help_ignore_extensions:
    """
    lgr.log(5, "Starting to setup_parser")
    # delay since it can be a heavy import
    from ..interface.base import (
        dedent_docstring,
        get_cmdline_command_name,
        get_interface_groups,
    )

    # setup cmdline args parser

    # "main" parser is under "datalad" name
    all_parsers = {}  # name: (sub)parser

    # main parser
    parser = ArgumentParserDisableAbbrev(
        fromfile_prefix_chars=None,
        # usage="%(prog)s ...",
        description=dedent_docstring("""\
            Comprehensive data management solution

            DataLad provides a unified data distribution system built on the Git
            and Git-annex. DataLad command line tools allow to manipulate (obtain,
            create, update, publish, etc.) datasets and provide a comprehensive
            toolbox for joint management of data and code. Compared to Git/annex
            it primarily extends their functionality to transparently and
            simultaneously work with multiple inter-related repositories."""),
        epilog='"Be happy!"',
        formatter_class=formatter_class,
        add_help=False)

    # common options
    parser_add_common_options(parser)

    interface_groups = get_interface_groups()

    single_subparser = _maybe_get_single_subparser(
        cmdlineargs, parser, interface_groups,
        return_subparsers, completing, help_ignore_extensions
    )

    # --help specification was delayed since it causes immediate printout of
    # --help output before we setup --help for each command
    parser_add_common_opt(parser, 'help')

    grp_short_descriptions = defaultdict(list)
    # create subparser, use module suffix as cmd name
    subparsers = parser.add_subparsers()
    for group_name, _, _interfaces \
            in sorted(interface_groups, key=lambda x: x[1]):
        for _intfspec in _interfaces:
            cmd_name = get_cmdline_command_name(_intfspec)
            if single_subparser and cmd_name != single_subparser:
                continue
            subparser = _maybe_get_interface_subparser(
                _intfspec, subparsers, cmd_name, formatter_class, group_name,
                grp_short_descriptions
            )
            if subparser:  # interface might have failed to "load"
                all_parsers[cmd_name] = subparser

    # create command summary
    if '--help' in cmdlineargs or '--help-np' in cmdlineargs:
        parser.description = get_description_with_cmd_summary(
            grp_short_descriptions,
            interface_groups,
            parser.description)

    all_parsers['datalad'] = parser
    lgr.log(5, "Finished setup_parser")
    if return_subparsers:
        return all_parsers
    else:
        return parser


def main(args=None):
    lgr.log(5, "Starting main(%r)", args)
    args = args or sys.argv
    if on_msys_tainted_paths:
        # Possibly present DataLadRIs were stripped of a leading /
        args = [_fix_datalad_ri(s) for s in args]
    # PYTHON_ARGCOMPLETE_OK
    parser = setup_parser(args, completing="_ARGCOMPLETE" in os.environ)
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # parse cmd args
    lgr.debug("Parsing known args among %s", repr(args))
    cmdlineargs, unparsed_args = parser.parse_known_args(args[1:])
    has_func = hasattr(cmdlineargs, 'func') and cmdlineargs.func is not None
    if unparsed_args:
        if has_func and cmdlineargs.func.__self__.__name__ != 'Export':
            lgr.error('unknown argument{}: {}'.format(
                's' if len(unparsed_args) > 1 else '',
                unparsed_args if len(unparsed_args) > 1 else unparsed_args[0]))
            cmdlineargs.subparser.print_usage()
            sys.exit(1)
        else:
            # store all unparsed arguments
            cmdlineargs.datalad_unparsed_args = unparsed_args

    # to possibly be passed into PBS scheduled call
    args_ = args or sys.argv

    if cmdlineargs.cfg_overrides is not None:
        datalad.cfg.overrides.update(
            _parse_overrides_from_cmdline(cmdlineargs)
        )

    # enable overrides
    datalad.cfg.reload(force=True)

    if cmdlineargs.change_path is not None:
        from .common_args import change_path as change_path_opt
        for path in cmdlineargs.change_path:
            chpwd(path)
            args_ = strip_arg_from_argv(args_, path, change_path_opt[1])

    ret = None
    if cmdlineargs.pbs_runner:
        from .helpers import run_via_pbs
        from .common_args import pbs_runner as pbs_runner_opt
        args_ = strip_arg_from_argv(args_, cmdlineargs.pbs_runner, pbs_runner_opt[1])
        # run the function associated with the selected command
        run_via_pbs(args_, cmdlineargs.pbs_runner)
    elif has_func:
        if cmdlineargs.common_debug or cmdlineargs.common_idebug:
            # so we could see/stop clearly at the point of failure
            setup_exceptionhook(ipython=cmdlineargs.common_idebug)
            from datalad.interface.base import Interface
            Interface._interrupted_exit_code = None
            ret = cmdlineargs.func(cmdlineargs)
        else:
            # otherwise - guard and only log the summary. Postmortem is not
            # as convenient if being caught in this ultimate except
            try:
                ret = cmdlineargs.func(cmdlineargs)
            except InsufficientArgumentsError as exc:
                ce = CapturedException(exc)
                # if the func reports inappropriate usage, give help output
                lgr.error('%s (%s)', ce, exc.__class__.__name__)
                cmdlineargs.subparser.print_usage(sys.stderr)
                sys.exit(2)
            except IncompleteResultsError as exc:
                ce = CapturedException(exc)
                # rendering for almost all commands now happens 'online'
                # hence we are no longer attempting to render the actual
                # results in an IncompleteResultsError, ubt rather trust that
                # this happened before

                # in general we do not want to see the error again, but
                # present in debug output
                lgr.debug('could not perform all requested actions: %s', ce)
                sys.exit(1)
            except CommandError as exc:
                ce = CapturedException(exc)
                # behave as if the command ran directly, importantly pass
                # exit code as is
                # to not duplicate any captured output in the exception
                # rendering, will come next
                exc_msg = exc.to_str(include_output=False)
                if exc_msg:
                    msg = exc_msg.encode() if isinstance(exc_msg, str) else exc_msg
                    os.write(2, msg + b"\n")
                if exc.stdout:
                    os.write(1, exc.stdout.encode() if isinstance(exc.stdout, str) else exc.stdout)
                if exc.stderr:
                    os.write(2, exc.stderr.encode() if isinstance(exc.stderr, str) else exc.stderr)
                # We must not exit with 0 code if any exception got here but
                # had no code defined
                sys.exit(exc.code if exc.code is not None else 1)
            except Exception as exc:
                ce = CapturedException(exc)
                lgr.error('%s (%s)', ce, exc.__class__.__name__)
                sys.exit(1)
    else:
        # just let argparser spit out its error, since there is smth wrong
        parser.parse_args(args)
        # if that one didn't puke -- we should
        parser.print_usage()
        lgr.error("Please specify the command")
        sys.exit(2)

    try:
        if hasattr(cmdlineargs, 'result_renderer'):
            cmdlineargs.result_renderer(ret, cmdlineargs)
    except Exception as exc:
        ce = CapturedException(exc)
        lgr.error("Failed to render results due to %s", ce)
        sys.exit(1)


lgr.log(5, "Done importing cmdline.main")
