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
import sys
import textwrap
import shutil
from importlib import import_module
import os

from six import text_type

import datalad

from datalad.cmdline import helpers
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.exceptions import CommandError
from .helpers import strip_arg_from_argv
from ..utils import setup_exceptionhook, chpwd
from ..dochelpers import exc_str


def _license_info():
    return """\
Copyright (c) 2013-2017 DataLad developers

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


# TODO:  OPT look into making setup_parser smarter to become faster
# Now it seems to take up to 200ms to do all the parser setup
# even though it might not be necessary to know about all the commands etc.
# I wondered if it could somehow decide on what commands to worry about etc
# by going through sys.args first
def setup_parser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        return_subparsers=False):

    lgr.log(5, "Starting to setup_parser")
    # delay since it can be a heavy import
    from ..interface.base import dedent_docstring, get_interface_groups, \
        get_cmdline_command_name, alter_interface_docs_for_cmdline
    # setup cmdline args parser
    parts = {}
    # main parser
    parser = argparse.ArgumentParser(
        # cannot use '@' because we need to input JSON-LD properties (which might come wit @ prefix)
        # MH: question, do we need this at all?
        fromfile_prefix_chars=':',
        # usage="%(prog)s ...",
        description=dedent_docstring("""\
            DataLad provides a unified data distribution with the convenience of git-annex
            repositories as a backend.  DataLad command line tools allow to manipulate
            (obtain, create, update, publish, etc.) datasets and their collections."""),
        epilog='"Control Your Data"',
        formatter_class=formatter_class,
        add_help=False)
    # common options
    helpers.parser_add_common_opt(parser, 'help')
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(parser, 'pbs_runner')
    helpers.parser_add_common_opt(parser, 'change_path')
    helpers.parser_add_common_opt(
        parser,
        'version',
        version='datalad %s\n\n%s' % (datalad.__version__, _license_info()))
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="enter Python debugger when uncaught exception happens")
        parser.add_argument(
            '--idbg', action='store_true', dest='common_idebug',
            help="enter IPython debugger when uncaught exception happens")
    parser.add_argument(
        '-c', action='append', dest='cfg_overrides', metavar='KEY=VALUE',
        help="""configuration variable setting. Overrides any configuration
        read from a file, but is potentially overridden itself by configuration
        variables in the process environment.""")
    parser.add_argument(
        '--output-format', dest='common_output_format',
        default='default',
        metavar="{default,json,json_pp,tailored,'<template>'",
        help="""select format for returned command results. 'default' give one line
        per result reporting action, status, path and an optional message;
        'json' renders a JSON object with all properties for each result (one per 
        line); 'json_pp' pretty-prints JSON spanning multiple lines; 'tailored'
        enables a command-specific rendering style that is typically
        tailored to human consumption (no result output otherwise),
        '<template>' reports any value(s) of any result properties in any format
        indicated by the template (e.g. '{path}', compare with JSON
        output for all key-value choices).""")
    parser.add_argument(
        '--report-status', dest='common_report_status',
        choices=['success', 'failure', 'ok', 'notneeded', 'impossible', 'error'],
        help="""constrain command result report to records matching the given
        status. 'success' is a synonym for 'ok' OR 'notneeded', 'failure' stands
        for 'impossible' OR 'error'.""")
    parser.add_argument(
        '--report-type', dest='common_report_type',
        choices=['dataset', 'file'],
        action='append',
        help="""constrain command result report to records matching the given
        type. Can be given more than once to match multiple types.""")
    parser.add_argument(
        '--on-failure', dest='common_on_failure',
        choices=['ignore', 'continue', 'stop'],
        # no default: better be configure per-command
        help="""when an operation fails: 'ignore' and continue with remaining
        operations, the error is logged but does not lead to a non-zero exit code
        of the command; 'continue' works like 'ignore', but an error causes a
        non-zero exit code; 'stop' halts on first failure and yields non-zero exit
        code. A failure is any result with status 'impossible' or 'error'.""")

    # yoh: atm we only dump to console.  Might adopt the same separation later on
    #      and for consistency will call it --verbose-level as well for now
    # log-level is set via common_opts ATM
    # parser.add_argument('--log-level',
    #                     choices=('critical', 'error', 'warning', 'info', 'debug'),
    #                     dest='common_log_level',
    #                     help="""level of verbosity in log files. By default
    #                          everything, including debug messages is logged.""")
    #parser.add_argument('-l', '--verbose-level',
    #                    choices=('critical', 'error', 'warning', 'info', 'debug'),
    #                    dest='common_verbose_level',
    #                    help="""level of verbosity of console output. By default
    #                         only warnings and errors are printed.""")

    # subparsers
    subparsers = parser.add_subparsers()

    # auto detect all available interfaces and generate a function-based
    # API from them
    grp_short_descriptions = []
    interface_groups = get_interface_groups()
    for grp_name, grp_descr, _interfaces \
                in sorted(interface_groups, key=lambda x: x[1]):
        # for all subcommand modules it can find
        cmd_short_descriptions = []

        for _intfspec in _interfaces:
            # turn the interface spec into an instance
            lgr.log(5, "Importing module %s " % _intfspec[0])
            _mod = import_module(_intfspec[0], package='datalad')
            _intf = getattr(_mod, _intfspec[1])
            cmd_name = get_cmdline_command_name(_intfspec)
            # deal with optional parser args
            if hasattr(_intf, 'parser_args'):
                parser_args = _intf.parser_args
            else:
                parser_args = dict(formatter_class=formatter_class)
            # use class description, if no explicit description is available
                intf_doc = _intf.__doc__.strip()
                if hasattr(_intf, '_docs_'):
                    # expand docs
                    intf_doc = intf_doc.format(**_intf._docs_)
                parser_args['description'] = alter_interface_docs_for_cmdline(
                    intf_doc)
            # create subparser, use module suffix as cmd name
            subparser = subparsers.add_parser(cmd_name, add_help=False, **parser_args)
            # all subparser can report the version
            helpers.parser_add_common_opt(
                subparser, 'version',
                version='datalad %s %s\n\n%s' % (cmd_name, datalad.__version__,
                                                 _license_info()))
            # our own custom help for all commands
            helpers.parser_add_common_opt(subparser, 'help')
            helpers.parser_add_common_opt(subparser, 'log_level')
            helpers.parser_add_common_opt(subparser, 'pbs_runner')
            # let module configure the parser
            _intf.setup_parser(subparser)
            # logger for command

            # configure 'run' function for this command
            plumbing_args = dict(
                func=_intf.call_from_parser,
                logger=logging.getLogger(_intf.__module__),
                subparser=subparser)
            if hasattr(_intf, 'result_renderer_cmdline'):
                plumbing_args['result_renderer'] = _intf.result_renderer_cmdline
            subparser.set_defaults(**plumbing_args)
            # store short description for later
            sdescr = getattr(_intf, 'short_description',
                             parser_args['description'].split('\n')[0])
            cmd_short_descriptions.append((cmd_name, sdescr))
            parts[cmd_name] = subparser
        grp_short_descriptions.append(cmd_short_descriptions)

    # create command summary
    cmd_summary = []
    console_width = shutil.get_terminal_size()[0] \
        if hasattr(shutil, 'get_terminal_size') else 80

    for i, grp in enumerate(
            sorted(interface_groups, key=lambda x: x[1])):
        grp_descr = grp[1]
        grp_cmds = grp_short_descriptions[i]

        cmd_summary.append('\n*%s*\n' % (grp_descr,))
        for cd in grp_cmds:
            cmd_summary.append('  %s\n%s'
                               % ((cd[0],
                                  textwrap.fill(
                                      cd[1].rstrip(' .'),
                                      console_width - 5,
                                      initial_indent=' ' * 6,
                                      subsequent_indent=' ' * 6))))
    # we need one last formal section to not have the trailed be
    # confused with the last command group
    cmd_summary.append('\n*General information*\n')
    parser.description = '%s\n%s\n\n%s' \
        % (parser.description,
           '\n'.join(cmd_summary),
           textwrap.fill(dedent_docstring("""\
    Detailed usage information for individual commands is
    available via command-specific --help, i.e.:
    datalad <command> --help"""),
                         console_width - 5, initial_indent='', subsequent_indent=''))
    parts['datalad'] = parser
    lgr.log(5, "Finished setup_parser")
    if return_subparsers:
        return parts
    else:
        return parser


# yoh: arn't used
# def generate_api_call(cmdlineargs=None):
#     parser = setup_parser()
#     # parse cmd args
#     cmdlineargs = parser.parse_args(cmdlineargs)
#     # convert cmdline args into API call spec
#     functor, args, kwargs = cmdlineargs.func(cmdlineargs)
#     return cmdlineargs, functor, args, kwargs


def main(args=None):
    lgr.log(5, "Starting main(%r)", args)
    # PYTHON_ARGCOMPLETE_OK
    parser = setup_parser()
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # parse cmd args
    cmdlineargs, unparsed_args = parser.parse_known_args(args)
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

    # enable overrides
    datalad.cfg.reload()

    if cmdlineargs.cfg_overrides is not None:
        overrides = dict([
            (o.split('=')[0], '='.join(o.split('=')[1:]))
            for o in cmdlineargs.cfg_overrides])
        datalad.cfg.overrides.update(overrides)

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
            ret = cmdlineargs.func(cmdlineargs)
        else:
            # otherwise - guard and only log the summary. Postmortem is not
            # as convenient if being caught in this ultimate except
            try:
                ret = cmdlineargs.func(cmdlineargs)
            except InsufficientArgumentsError as exc:
                # if the func reports inappropriate usage, give help output
                lgr.error('%s (%s)' % (exc_str(exc), exc.__class__.__name__))
                cmdlineargs.subparser.print_usage(sys.stderr)
                sys.exit(2)
            except IncompleteResultsError as exc:
                # rendering for almost all commands now happens 'online'
                # hence we are no longer attempting to render the actual
                # results in an IncompleteResultsError, ubt rather trust that
                # this happened before

                # in general we do not want to see the error again, but
                # present in debug output
                lgr.debug('could not perform all requested actions: %s',
                          exc_str(exc))
                sys.exit(1)
            except CommandError as exc:
                # behave as if the command ran directly, importantly pass
                # exit code as is
                if exc.msg:
                    os.write(2, exc.msg.encode() if isinstance(exc.msg, text_type) else exc.msg)
                if exc.stdout:
                    os.write(1, exc.stdout.encode()) \
                        if hasattr(exc.stdout, 'encode')  \
                        else os.write(1, exc.stdout)
                if exc.stderr:
                    os.write(2, exc.stderr.encode()) \
                        if hasattr(exc.stderr, 'encode')  \
                        else os.write(2, exc.stderr)
                # We must not exit with 0 code if any exception got here but
                # had no code defined
                sys.exit(exc.code if exc.code is not None else 1)
            except Exception as exc:
                lgr.error('%s (%s)' % (exc_str(exc), exc.__class__.__name__))
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
        lgr.error("Failed to render results due to %s", exc_str(exc))
        sys.exit(1)

lgr.log(5, "Done importing cmdline.main")
