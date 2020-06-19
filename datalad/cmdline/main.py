# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""
from datalad.ui.utils import get_console_width

__docformat__ = 'restructuredtext'

import logging
lgr = logging.getLogger('datalad.cmdline')

lgr.log(5, "Importing cmdline.main")

import argparse
from collections import defaultdict
import sys
import textwrap
import os


import datalad

from datalad.cmdline import helpers
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.exceptions import CommandError
from .helpers import strip_arg_from_argv
from ..utils import (
    assure_unicode,
    chpwd,
    get_suggestions_msg,
    on_msys_tainted_paths,
    setup_exceptionhook,
)
from ..dochelpers import exc_str


def _license_info():
    return """\
Copyright (c) 2013-2019 DataLad developers

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


class ArgumentParserDisableAbbrev(argparse.ArgumentParser):
    # Don't accept abbreviations for long options. This kludge was originally
    # added at a time when our minimum required Python version was below 3.5,
    # preventing us from using allow_abbrev=False. Now our minimum Python
    # version is high enough, but we still can't use allow_abbrev=False because
    # it suffers from the problem described in 6b3f2fffe (BF: cmdline: Restore
    # handling of short options, 2018-07-23).
    #
    # Modified from the solution posted at
    # https://bugs.python.org/issue14910#msg204678
    def _get_option_tuples(self, option_string):
        chars = self.prefix_chars
        if option_string[0] in chars and option_string[1] in chars:
            # option_string is a long flag. Disable abbreviation.
            return []
        return super(ArgumentParserDisableAbbrev, self)._get_option_tuples(
            option_string)


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
    lgr.log(5, "Starting to setup_parser")
    # delay since it can be a heavy import
    from ..interface.base import dedent_docstring, get_interface_groups, \
        get_cmdline_command_name, alter_interface_docs_for_cmdline, \
        load_interface, get_cmd_doc, get_cmd_ex
    # setup cmdline args parser
    parts = {}
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
            it primarly extends their functionality to transparently and
            simultaneously work with multiple inter-related repositories."""),
        epilog='"Be happy!"',
        formatter_class=formatter_class,
        add_help=False)
    # common options
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(parser, 'pbs_runner')
    helpers.parser_add_common_opt(parser, 'change_path')
    helpers.parser_add_common_opt(
        parser,
        'version',
        version='datalad %s\n' % datalad.__version__)
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
        '-f', '--output-format', dest='common_output_format',
        default='default',
        type=assure_unicode,
        metavar="{default,json,json_pp,tailored,'<template>'}",
        help="""select format for returned command results. 'default' give one line
        per result reporting action, status, path and an optional message;
        'json' renders a JSON object with all properties for each result (one per
        line); 'json_pp' pretty-prints JSON spanning multiple lines; 'tailored'
        enables a command-specific rendering style that is typically
        tailored to human consumption (no result output otherwise),
        '<template>' reports any value(s) of any result properties in any format
        indicated by the template (e.g. '{path}'; compare with JSON
        output for all key-value choices). The template syntax follows the Python
        "format() language". It is possible to report individual
        dictionary values, e.g. '{metadata[name]}'. If a 2nd-level key contains
        a colon, e.g. 'music:Genre', ':' must be substituted by '#' in the template,
        like so: '{metadata[music#Genre]}'.""")
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
    parser.add_argument(
        '--cmd', dest='_', action='store_true',
        help="""syntactical helper that can be used to end the list of global
        command line options before the subcommand label. Options taking
        an arbitrary number of arguments may require to be followed by a single
        --cmd in order to enable identification of the subcommand.""")

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

    # Before doing anything additional and possibly expensive see may be that
    # we have got the command already
    need_single_subparser = False if return_subparsers else None
    fail_handler = (lambda *a, **kw: True) \
        if return_subparsers else fail_with_short_help
    try:
        parsed_args, unparsed_args = parser._parse_known_args(
            cmdlineargs[1:], argparse.Namespace())
        if not (completing or unparsed_args):
            fail_handler(parser, msg="too few arguments", exit_code=2)
        lgr.debug("Command line args 1st pass. Parsed: %s Unparsed: %s",
                  parsed_args, unparsed_args)
    except Exception as exc:
        lgr.debug("Early parsing failed with %s", exc_str(exc))
        need_single_subparser = False
        unparsed_args = cmdlineargs[1:]  # referenced before assignment otherwise

    interface_groups = get_interface_groups(include_plugins=True)

    # First unparsed could be either unknown option to top level "datalad"
    # or a command. Among unknown could be --help/--help-np which would
    # need to be dealt with
    unparsed_arg = unparsed_args[0] if unparsed_args else None
    if need_single_subparser is not None \
            or unparsed_arg in ('--help', '--help-np', '-h'):
        need_single_subparser = False
        if not help_ignore_extensions:
            add_entrypoints_to_interface_groups(interface_groups)
    elif not completing and unparsed_arg.startswith('-'):  # unknown option
        fail_with_short_help(parser,
                             msg="unrecognized argument %s" % unparsed_arg,
                             exit_code=2)
        # if we could get a list of options known to parser,
        # we could suggest them
        # known=get_all_options(parser), provided=unparsed_arg)
    else:  # the command to handle
        known_commands = get_commands_from_groups(interface_groups)
        if unparsed_arg not in known_commands:
            # need to load all the extensions and try again
            add_entrypoints_to_interface_groups(interface_groups)
            known_commands = get_commands_from_groups(interface_groups)

        if unparsed_arg not in known_commands:
            # check if might be coming from known extensions
            from ..interface import (
                _known_extension_commands,
                _deprecated_commands,
            )
            extension_commands = {
                c: e
                for e, commands in _known_extension_commands.items()
                for c in commands
            }
            hint = None
            if unparsed_arg in extension_commands:
                hint = "Command %s is provided by (not installed) extension %s." \
                      % (unparsed_arg, extension_commands[unparsed_arg])
            elif unparsed_arg in _deprecated_commands:
                hint_cmd = _deprecated_commands[unparsed_arg]
                hint = "Command %r was deprecated" % unparsed_arg
                hint += (" in favor of %r command." % hint_cmd) if hint_cmd else '.'
            if not completing:
                fail_with_short_help(
                    parser,
                    hint=hint,
                    provided=unparsed_arg,
                    known=list(known_commands.keys()) + list(extension_commands.keys())
                )
        if need_single_subparser is None:
            need_single_subparser = unparsed_arg

    # --help specification was delayed since it causes immediate printout of
    # --help output before we setup --help for each command
    helpers.parser_add_common_opt(parser, 'help')

    grp_short_descriptions = defaultdict(list)
    # create subparser, use module suffix as cmd name
    subparsers = parser.add_subparsers()
    for group_name, _, _interfaces \
            in sorted(interface_groups, key=lambda x: x[1]):
        for _intfspec in _interfaces:
            cmd_name = get_cmdline_command_name(_intfspec)
            if need_single_subparser and cmd_name != need_single_subparser:
                continue
            _intf = load_interface(_intfspec)
            if _intf is None:
                # TODO(yoh):  add doc why we could skip this one... makes this
                # loop harder to extract into a dedicated function
                continue
            # deal with optional parser args
            if hasattr(_intf, 'parser_args'):
                parser_args = _intf.parser_args
            else:
                parser_args = dict(formatter_class=formatter_class)
                # use class description, if no explicit description is available
                intf_doc = get_cmd_doc(_intf)
                parser_args['description'] = alter_interface_docs_for_cmdline(
                    intf_doc)
                if hasattr(_intf, '_examples_'):
                    intf_ex = alter_interface_docs_for_cmdline(get_cmd_ex(_intf))
                    parser_args['description'] += intf_ex
            subparser = subparsers.add_parser(cmd_name, add_help=False, **parser_args)
            # our own custom help for all commands
            helpers.parser_add_common_opt(subparser, 'help')
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
            parts[cmd_name] = subparser
            # store short description for later
            sdescr = getattr(_intf, 'short_description',
                             parser_args['description'].split('\n')[0])
            grp_short_descriptions[group_name].append((cmd_name, sdescr))

    # create command summary
    if '--help' in cmdlineargs or '--help-np' in cmdlineargs:
        parser.description = get_description_with_cmd_summary(
            grp_short_descriptions,
            interface_groups,
            parser.description)

    parts['datalad'] = parser
    lgr.log(5, "Finished setup_parser")
    if return_subparsers:
        return parts
    else:
        return parser


def fail_with_short_help(parser=None,
                         msg=None,
                         known=None, provided=None,
                         hint=None,
                         exit_code=1,
                         what="command",
                         out=None):
    """Generic helper to fail
    with short help possibly hinting on what was intended if `known`
    were provided
    """
    out = out or sys.stderr
    if msg:
        out.write("error: %s\n" % msg)
    if not known:
        if parser:
            # just to appear in print_usage also consistent with --help output
            parser.add_argument("command [command-opts]")
            parser.print_usage(file=out)
    else:
        out.write(
            "datalad: Unknown %s %r.  See 'datalad --help'.\n\n"
            % (what, provided,))
        if provided not in known:
            out.write(get_suggestions_msg(provided, known))
        # Too noisy
        # sys.stderr.write(" All known %ss: %s\n"
        #                   % (what, ", ".join(sorted(known))))
    if hint:
        out.write("Hint: %s\n" % hint)
    raise SystemExit(exit_code)


def get_description_with_cmd_summary(grp_short_descriptions, interface_groups,
                                     parser_description):
    from ..interface.base import dedent_docstring
    from ..interface.base import get_cmd_summaries
    lgr.debug("Generating detailed description for the parser")

    console_width = get_console_width()
    cmd_summary = get_cmd_summaries(grp_short_descriptions, interface_groups,
                                    width=console_width)
    # we need one last formal section to not have the trailed be
    # confused with the last command group
    cmd_summary.append('\n*General information*\n')
    detailed_description = '%s\n%s\n\n%s' \
                           % (parser_description,
                              '\n'.join(cmd_summary),
                              textwrap.fill(dedent_docstring("""\
    Detailed usage information for individual commands is
    available via command-specific --help, i.e.:
    datalad <command> --help"""),
                                            console_width - 5,
                                            initial_indent='',
                                            subsequent_indent=''))
    return detailed_description


def get_commands_from_groups(groups):
    """Get a dictionary of command: interface_spec"""
    from ..interface.base import get_cmdline_command_name
    return {
        get_cmdline_command_name(_intfspec): _intfspec
        for _, _, _interfaces in groups
        for _intfspec in _interfaces
    }


def add_entrypoints_to_interface_groups(interface_groups):
    lgr.debug("Loading entrypoints")
    from pkg_resources import iter_entry_points  # delay expensive import
    for ep in iter_entry_points('datalad.extensions'):
        lgr.debug(
            'Loading entrypoint %s from datalad.extensions for docs building',
            ep.name)
        try:
            spec = ep.load()
            if len(spec) < 2 or not spec[1]:
                lgr.debug(
                    'Extension does not provide a command suite: %s',
                    ep.name)
                continue
            interface_groups.append((ep.name, spec[0], spec[1]))
            lgr.debug('Loaded entrypoint %s', ep.name)
        except Exception as e:
            lgr.warning('Failed to load entrypoint %s: %s', ep.name, exc_str(e))
            continue

def _fix_datalad_ri(s):
    """Fixup argument if it was a DataLadRI and had leading / removed

    See gh-2643
    """
    if s.startswith('//') and (len(s) == 2 or (len(s) > 2 and s[2] != '/')):
        lgr.info(
            "Changing %s back to /%s as it was probably changed by MINGW/MSYS, "
            "see http://www.mingw.org/wiki/Posix_path_conversion", s, s)
        return "/" + s
    return s


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
        import re
        # this expression is deliberately loose as gitconfig offers
        # quite some flexibility -- this is just meant to catch stupid
        # errors: we need a section, a variable, and a value at minimum
        # otherwise we break our own config parsing helpers
        # https://github.com/datalad/datalad/issues/3451
        noassign_expr = re.compile(r'[^\s]+\.[^\s]+=[\S]+')
        noassign = [
            o
            for o in cmdlineargs.cfg_overrides
            if not noassign_expr.match(o)
        ]
        if noassign:
            lgr.error(
                "Configuration override without section/variable "
                "or value assignment (must be 'section.variable=value'): %s",
                noassign)
            sys.exit(3)
        overrides = dict([
            (o.split('=')[0], '='.join(o.split('=')[1:]))
            for o in cmdlineargs.cfg_overrides])
        datalad.cfg.overrides.update(overrides)

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
