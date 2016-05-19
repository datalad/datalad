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


import argparse
import logging
import sys
import os
import textwrap
from importlib import import_module

import datalad
from datalad.log import lgr

from datalad.cmdline import helpers
from datalad.support.exceptions import InsufficientArgumentsError
from ..utils import setup_exceptionhook, chpwd
from ..dochelpers import exc_str

def _license_info():
    return """\
Copyright (c) 2013-2016 DataLad developers

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


def setup_parser():
    # Delay since can be a heavy import
    from ..interface.base import dedent_docstring, get_interface_groups
    # setup cmdline args parser
    # main parser
    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@',
        # usage="%(prog)s ...",
        description=dedent_docstring("""\
            DataLad provides a unified data distribution with the convenience of git-annex
            repositories as a backend.  datalad command line tool allows to manipulate
            (obtain, create, update, publish, etc.) datasets and their collections."""),
        epilog='"Control Your Data"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False)
    # common options
    helpers.parser_add_common_opt(parser, 'help')
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(parser, 'pbs_runner')
    helpers.parser_add_common_opt(
        parser,
        'version',
        version='datalad %s\n\n%s' % (datalad.__version__, _license_info()))
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="do not catch exceptions and show exception traceback")
    parser.add_argument(
        '-C', action='append', dest='change_path', metavar='PATH',
        help="""Run as if datalad was started in <path> instead
        of the current working directory. When multiple -C options are given,
        each subsequent non-absolute -C <path> is interpreted relative to the
        preceding -C <path>. This option affects the interpretations of the
        path names in that they are made relative to the working directory
        caused by the -C option.""")

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
    for grp_name, grp_descr, _interfaces in interface_groups:
        # for all subcommand modules it can find
        cmd_short_descriptions = []

        for _intfspec in _interfaces:
            # turn the interface spec into an instance
            _mod = import_module(_intfspec[0], package='datalad')
            _intf = getattr(_mod, _intfspec[1])
            if len(_intfspec) > 2:
                cmd_name = _intfspec[2]
            else:
                cmd_name = _intf.__module__.split('.')[-1].replace('_', '-')
            # deal with optional parser args
            if hasattr(_intf, 'parser_args'):
                parser_args = _intf.parser_args
            else:
                parser_args = dict(formatter_class=argparse.RawDescriptionHelpFormatter)
            # use class description, if no explicit description is available
                parser_args['description'] = dedent_docstring(_intf.__doc__)
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
        grp_short_descriptions.append(cmd_short_descriptions)

    # create command summary
    cmd_summary = []
    for i, grp in enumerate(interface_groups):
        grp_descr = grp[1]
        grp_cmds = grp_short_descriptions[i]

        cmd_summary.append('\n*%s*\n' % (grp_descr,))
        for cd in grp_cmds:
            cmd_summary.append('  - %s:  %s'
                               % (cd[0],
                                  textwrap.fill(
                                      cd[1].rstrip(' .'),
                                      75,
                                      #initial_indent=' ' * 4,
                                      subsequent_indent=' ' * 8)))
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
                         75, initial_indent='', subsequent_indent=''))
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
    # PYTHON_ARGCOMPLETE_OK
    parser = setup_parser()
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # parse cmd args
    cmdlineargs = parser.parse_args(args)
    if not cmdlineargs.change_path is None:
        for path in cmdlineargs.change_path:
            chpwd(path)

    ret = None
    if cmdlineargs.pbs_runner:
        from .helpers import run_via_pbs
        from .helpers import strip_arg_from_argv
        from .common_args import pbs_runner as pbs_runner_opt
        args_ = strip_arg_from_argv(args or sys.argv, cmdlineargs.pbs_runner, pbs_runner_opt[1])
        # run the function associated with the selected command
        run_via_pbs(args_, cmdlineargs.pbs_runner)
    elif cmdlineargs.common_debug:
        # So we could see/stop clearly at the point of failure
        setup_exceptionhook()
        ret = cmdlineargs.func(cmdlineargs)
    else:
        # Otherwise - guard and only log the summary. Postmortem is not
        # as convenient if being caught in this ultimate except
        try:
            ret = cmdlineargs.func(cmdlineargs)
        except InsufficientArgumentsError as exc:
            # if the func reports inappropriate usage, give help output
            lgr.error('%s (%s)' % (exc_str(exc), exc.__class__.__name__))
            cmdlineargs.subparser.print_usage()
            sys.exit(1)
        except Exception as exc:
            lgr.error('%s (%s)' % (exc_str(exc), exc.__class__.__name__))
            sys.exit(1)
    if hasattr(cmdlineargs, 'result_renderer'):
        cmdlineargs.result_renderer(ret)
