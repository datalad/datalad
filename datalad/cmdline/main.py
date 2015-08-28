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
import textwrap

import datalad
from datalad.log import lgr

from datalad.cmdline import helpers
from ..interface.base import dedent_docstring
from ..utils import setup_exceptionhook


def _license_info():
    return """\
Copyright (c) 2013-2015 DataLad developers

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
    # setup cmdline args parser
    # main parser
    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@',
        # usage="%(prog)s ...",
        description=dedent_docstring("""\
    DataLad aims to expose (scientific) data available online as a unified data
    distribution with the convenience of git-annex repositories as a backend.

    datalad command line tool facilitates initial construction and update of
    harvested online datasets.  It supports following commands
    """),
        epilog='"Geet My Data"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False)
    # common options
    helpers.parser_add_common_opt(parser, 'help')
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(
        parser,
        'version',
        version='datalad %s\n\n%s' % (datalad.__version__, _license_info()))
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="do not catch exceptions and show exception traceback")

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
    # for all subcommand modules it can find
    cmd_short_description = []
    from ..interface.base import Interface as _Interface
    from .. import interface as _interfaces

    # auto detect all available interfaces and generate a function-based
    # API from them
    for _item in _interfaces.__dict__:
        _intfcls = getattr(_interfaces, _item)
        try:
            if not issubclass(_intfcls, _Interface):
                continue
        except TypeError:
            continue
        _intf = _intfcls()

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
        # let module configure the parser
        _intf.setup_parser(subparser)
        # logger for command

        # configure 'run' function for this command
        subparser.set_defaults(func=_intf.call_from_parser,
                               logger=logging.getLogger(_intf.__module__))
        # store short description for later
        sdescr = getattr(_intf, 'short_description',
                         parser_args['description'].split('\n')[0])
        cmd_short_description.append((cmd_name, sdescr))

    # create command summary
    cmd_summary = []
    for cd in cmd_short_description:
        cmd_summary.append('%s\n%s\n\n'
                           % (cd[0],
                              textwrap.fill(
                                  cd[1],
                                  75,
                                  initial_indent=' ' * 4,
                                  subsequent_indent=' ' * 4)))
    parser.description = '%s\n%s\n\n%s' \
        % (parser.description,
           '\n'.join(cmd_summary),
           textwrap.fill(dedent_docstring("""\
    Detailed usage information for individual commands is
    available via command-specific help options, i.e.:
    %s <command> --help""") % sys.argv[0],
                         75, initial_indent='', subsequent_indent=''))
    return parser


def generate_api_call(cmdlineargs=None):
    parser = setup_parser()
    # parse cmd args
    cmdlineargs = parser.parse_args(cmdlineargs)
    # convert cmdline args into API call spec
    functor, args, kwargs = cmdlineargs.func(cmdlineargs)
    return cmdlineargs, functor, args, kwargs


def main(cmdlineargs=None):
    parser = setup_parser()
    # parse cmd args
    cmdlineargs = parser.parse_args(cmdlineargs)
    # run the function associated with the selected command
    if cmdlineargs.common_debug:
        # So we could see/stop clearly at the point of failure
        setup_exceptionhook()
        cmdlineargs.func(cmdlineargs)
    else:
        # Otherwise - guard and only log the summary. Postmortem is not
        # as convenient if being caught in this ultimate except
        try:
            cmdlineargs.func(cmdlineargs)
        except Exception as exc:
            lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
            sys.exit(1)
