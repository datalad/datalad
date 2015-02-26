# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'


import argparse
import logging
import sys
import textwrap

import datalad
from datalad import log
from datalad.log import lgr

import datalad.cmdline as mvcmd
from datalad.cmdline import helpers


def _license_info():
    return """\
Copyright (c) 2013-2014 DataLad developers

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

DataLad (originally DataGit) is written by Yaroslav Halchenko with the help
of numerous other contributors.  Skeleton for datalad's cmdline handling is
borrowed from testkraut (https://github.com/neurodebian/testkraut)
by Michael Hanke, Expat license as well.
"""


# setup cmdline args parser
# main parser
parser = argparse.ArgumentParser(
                fromfile_prefix_chars='@',
                # usage="%(prog)s ...",
                description="""\
DataLad aims to expose (scientific) data available online as a unified data distribution with the convenience of git-annex repositories as a backend.

datalad command line tool facilitates initial construction and update of harvested online datasets.  It supports following commands
""",
                epilog='"Geet My Data"',
                formatter_class=argparse.RawDescriptionHelpFormatter,
                add_help=False
            )
# common options
helpers.parser_add_common_opt(parser, 'help')
helpers.parser_add_common_opt(parser, 'log_level')
helpers.parser_add_common_opt(parser,
                              'version',
                              version='datalad %s\n\n%s' % (datalad.__version__,
                                                          _license_info()))
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
for cmd in sorted([c for c in dir(mvcmd) if c.startswith('cmd_')]):
    cmd_name = cmd[4:]
    subcmdmod = getattr(__import__('datalad.cmdline',
                                   globals(), locals(),
                                   [cmd], -1),
                        cmd)
    # deal with optional parser args
    if 'parser_args' in subcmdmod.__dict__:
        parser_args = subcmdmod.parser_args
    else:
        parser_args = dict()
    # use module description, if no explicit description is available
    if not 'description' in parser_args:
        parser_args['description'] = subcmdmod.__doc__
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
    subcmdmod.setup_parser(subparser)
    # logger for command

    # configure 'run' function for this command
    subparser.set_defaults(func=subcmdmod.run,
                           logger=logging.getLogger('datalad.%s' % cmd))
    # store short description for later
    sdescr = getattr(subcmdmod, 'short_description',
                     parser_args['description'].split('\n')[0])
    cmd_short_description.append((cmd_name, sdescr))

# create command summary
cmd_summary = []
for cd in cmd_short_description:
    cmd_summary.append('%s\n%s\n\n' \
                       % (cd[0],
                          textwrap.fill(cd[1], 75,
                              initial_indent=' ' * 4,
                              subsequent_indent=' ' * 4)))
parser.description = '%s\n%s\n\n%s' \
        % (parser.description,
           '\n'.join(cmd_summary),
           textwrap.fill("""\
Detailed usage information for individual commands is
available via command-specific help options, i.e.:
%s <command> --help""" % sys.argv[0],
                            75, initial_indent='',
                            subsequent_indent=''))

# parse cmd args
args = parser.parse_args()

# run the function associated with the selected command
try:
    args.func(args)
except Exception as exc:
    lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
    if args.common_debug:
        import pdb
        pdb.post_mortem()
    sys.exit(1)
