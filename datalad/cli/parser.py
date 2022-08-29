"""Components to build the parser instance for the CLI

This module must import (and run) really fast for a responsive CLI.
It is unconditionally imported by the main() entrypoint.
"""

# ATTN!
# All top-imports are limited to functionality that is necessary for the
# non-error case of constructing of a single target command parser only.
# For speed reasons, all other imports necessary for special cases,
# like error handling, must be done conditionally in-line.

import argparse
from collections import defaultdict
from functools import partial
import sys


from datalad import __version__

from .common_args import common_args
from datalad.interface.base import (
    is_api_arg,
    get_cmd_doc,
    get_interface_groups,
    load_interface,
)
from datalad.utils import getargspec
from .interface import (
    alter_interface_docs_for_cmdline,
    get_cmd_ex,
    get_cmdline_command_name,
)
from datalad.support.constraints import EnsureChoice
from .helpers import get_commands_from_groups
from .exec import call_from_parser

# special case imports
#  .helpers import add_entrypoints_to_interface_groups
#  .helpers.get_description_with_cmd_summary
#  .helpers.get_commands_from_groups
#  .utils.get_suggestions_msg,
#  .interface._known_extension_commands
#  .interface._deprecated_commands

import logging
lgr = logging.getLogger('datalad.cli.parser')


help_gist = """\
Comprehensive data management solution

DataLad provides a unified data distribution system built on the Git
and Git-annex. DataLad command line tools allow to manipulate (obtain,
create, update, publish, etc.) datasets and provide a comprehensive
toolbox for joint management of data and code. Compared to Git/annex
it primarily extends their functionality to transparently and
simultaneously work with multiple inter-related repositories."""


# TODO:  OPT look into making setup_parser smarter to become faster
# Now it seems to take up to 200ms to do all the parser setup
# even though it might not be necessary to know about all the commands etc.
# I wondered if it could somehow decide on what commands to worry about etc
# by going through sys.args first
def setup_parser(
        cmdlineargs,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        return_subparsers=False,
        completing=False,
        help_ignore_extensions=False):
    """
    The holy grail of establishing CLI for DataLad's Interfaces

    Parameters
    ----------
    cmdlineargs: sys.argv
      Used to make some shortcuts when construction of a full parser can be
      avoided.
    formatter_class:
      Passed to argparse
    return_subparsers: bool, optional
      is used ATM only by BuildManPage in _datalad_build_support
    completing: bool, optional
      Flag to indicate whether the process was invoked by argcomplete
    help_ignore_extensions: bool, optional
      Prevent loading of extension entrypoints when --help is requested.
      This is enabled when building docs to avoid pollution of generated
      manpages with extensions commands (that should appear in their own
      docs, but not in the core datalad package docs)
    """
    lgr.log(5, "Starting to setup_parser")

    # main parser
    parser = ArgumentParserDisableAbbrev(
        fromfile_prefix_chars=None,
        prog='datalad',
        # usage="%(prog)s ...",
        description=help_gist,
        epilog='"Be happy!"',
        formatter_class=formatter_class,
        add_help=False,
        # TODO: when dropping support for Python 3.8: uncomment below
        # and use parse_known_args instead of _parse_known_args:
        # # set to False so parse_known_args does not add its error handling
        # # Added while RFing from using _parse_known_args to parse_known_args.
        # exit_on_error=False,
    )

    # common options
    parser_add_common_options(parser)

    # get all interface definitions from datalad-core
    interface_groups = get_interface_groups()

    # try to figure out whether the parser construction can be limited to
    # a single (sub)command -- don't even try to do this, when we are in
    # any of the doc-building capacities -- timing is not relevant there
    status, parseinfo = single_subparser_possible(
        cmdlineargs,
        parser,
        completing,
    ) if not return_subparsers else ('allparsers', None)

    command_provider = 'core'

    if status == 'allparsers' and not help_ignore_extensions:
        from .helpers import add_entrypoints_to_interface_groups
        add_entrypoints_to_interface_groups(interface_groups)

    # when completing and we have no incomplete option or parameter
    # we still need to offer all commands for completion
    if (completing and status == 'allknown') or (
            status == 'subcommand' and parseinfo not in
            get_commands_from_groups(interface_groups)):
        # we know the command is not in the core package
        # still a chance it could be in an extension
        command_provider = 'extension'
        # we need the full help, or we have a potential command that
        # lives in an extension, must load all extension, expensive
        from .helpers import add_entrypoints_to_interface_groups
        # need to load all the extensions and try again
        # TODO load extensions one-by-one and stop when a command was found
        add_entrypoints_to_interface_groups(interface_groups)

        if status == 'subcommand':
            known_commands = get_commands_from_groups(interface_groups)
            if parseinfo not in known_commands:
                # certainly not possible to identify a single parser that
                # could be constructed, but we can be helpful
                # will sys.exit() unless we are completing
                try_suggest_extension_with_command(
                    parser, parseinfo, completing, known_commands)
                # in completion mode we can get here, even for a command
                # that does not exist at all!
                command_provider = None

    # TODO check if not needed elsewhere
    if status == 'help' or completing and status in ('allknown', 'unknownopt'):
        # --help specification was delayed since it causes immediate
        # printout of
        # --help output before we setup --help for each command
        parser_add_common_opt(parser, 'help')

    all_parsers = {}  # name: (sub)parser

    if (completing and status == 'allknown') or status \
            in ('allparsers', 'subcommand', 'error'):
        # parseinfo could be None here, when we could not identify
        # a subcommand, but need to locate matching ones for
        # completion
        # create subparser, use module suffix as cmd name
        subparsers = parser.add_subparsers()
        for _, _, _interfaces \
                in sorted(interface_groups, key=lambda x: x[1]):
            for _intfspec in _interfaces:
                cmd_name = get_cmdline_command_name(_intfspec)
                if status == 'subcommand':
                    # in case only a subcommand is desired, we could
                    # skip some processing
                    if command_provider and cmd_name != parseinfo:
                        # a known command, but know what we are looking for
                        continue
                    if command_provider is None and not cmd_name.startswith(
                            parseinfo):
                        # an unknown command, and has no common prefix with
                        # the current command candidate, not even good
                        # for completion
                        continue
                subparser = add_subparser(
                    _intfspec,
                    subparsers,
                    cmd_name,
                    formatter_class,
                    completing=completing,
                )
                if subparser:  # interface can fail to load
                    all_parsers[cmd_name] = subparser

    # "main" parser is under "datalad" name
    all_parsers['datalad'] = parser
    lgr.log(5, "Finished setup_parser")
    if return_subparsers:
        # TODO why not pull the subparsers from the main parser?
        return all_parsers
    else:
        return parser


def setup_parser_for_interface(parser, cls, completing=False):
    # XXX needs safety check for name collisions
    # XXX allow for parser kwargs customization
    # get the signature, order of arguments is taken from it
    ndefaults = 0
    args, varargs, varkw, defaults = getargspec(
        cls.__call__, include_kwonlyargs=True)
    if defaults is not None:
        ndefaults = len(defaults)
    default_offset = ndefaults - len(args)
    prefix_chars = parser.prefix_chars
    for i, arg in enumerate(args):
        if not is_api_arg(arg):
            continue

        param = cls._params_[arg]
        defaults_idx = default_offset + i
        if param.cmd_args == tuple():
            # explicitly provided an empty sequence of argument names
            # this shall not appear in the parser
            continue

        # set up the parameter
        setup_parserarg_for_interface(
            parser, arg, param, defaults_idx, prefix_chars, defaults,
            completing=completing)


def setup_parserarg_for_interface(parser, param_name, param, defaults_idx,
                                  prefix_chars, defaults, completing=False):
    cmd_args = param.cmd_args
    parser_kwargs = param.cmd_kwargs
    has_default = defaults_idx >= 0
    if cmd_args:
        if cmd_args[0][0] in prefix_chars:
            # TODO: All the Parameter(args=...) values in this code
            # base use hyphens, so there is no point in the below
            # conversion. If it looks like no extensions rely on this
            # behavior either, this could be dropped.
            parser_args = [c.replace('_', '-') for c in cmd_args]
        else:
            # Argparse will not convert dashes to underscores for
            # arguments that don't start with a prefix character, so
            # the above substitution must be avoided so that
            # call_from_parser() can find the corresponding parameter.
            parser_args = cmd_args
    elif has_default:
        # Construct the option from the Python parameter name.
        parser_args = ("--{}".format(param_name.replace("_", "-")),)
    else:
        # If args= wasn't given and its a positional argument in the
        # function, add a positional argument to argparse. If `dest` is
        # specified, we need to remove it from the keyword arguments
        # because add_argument() expects it as the first argument. Note
        # that `arg` shouldn't have a dash here, but `metavar` can be
        # used if a dash is preferred for the command-line help.
        parser_args = (parser_kwargs.pop("dest", param_name),)

    if has_default:
        parser_kwargs['default'] = defaults[defaults_idx]
    if param.constraints is not None:
        parser_kwargs['type'] = param.constraints
    if completing:
        help = None
        # if possible, define choices to enable their completion
        if 'choices' not in parser_kwargs and \
                isinstance(param.constraints, EnsureChoice):
            parser_kwargs['choices'] = [
                c for c in param.constraints._allowed if c is not None]
    else:
        help = _amend_param_parser_kwargs_for_help(
            parser_kwargs, param,
            defaults[defaults_idx] if defaults_idx >= 0 else None)
    # create the parameter, using the constraint instance for type
    # conversion
    parser.add_argument(*parser_args, help=help,
                        **parser_kwargs)


def _amend_param_parser_kwargs_for_help(parser_kwargs, param, default=None):
    if 'metavar' not in parser_kwargs and \
            isinstance(param.constraints, EnsureChoice):
        parser_kwargs['metavar'] = \
            '{%s}' % '|'.join(
                # don't use short_description(), because
                # it also needs to give valid output for
                # Python syntax (quotes...), but here we
                # can simplify to shell syntax where everything
                # is a string
                p for p in param.constraints._allowed
                # in the cmdline None pretty much means
                # don't give the options, so listing it
                # doesn't make sense. Moreover, any non-string
                # value cannot be given and very likely only
                # serves a special purpose in the Python API
                # or implementation details
                if isinstance(p, str))
    help = alter_interface_docs_for_cmdline(param._doc)
    if help:
        help = help.rstrip()
        if help[-1] != '.':
            help += '.'
        if param.constraints is not None:
            help += _get_help_for_parameter_constraint(param)
    if default is not None and \
            not parser_kwargs.get('action', '').startswith('store_'):
        # if it is a flag, in commandline it makes little sense to show
        # showing the Default: (likely boolean).
        # See https://github.com/datalad/datalad/issues/3203
        help += " [Default: %r]" % (default,)
    return help


def _get_help_for_parameter_constraint(param):
    # include value constraint description and default
    # into the help string
    cdoc = alter_interface_docs_for_cmdline(
        param.constraints.long_description())
    if cdoc[0] == '(' and cdoc[-1] == ')':
        cdoc = cdoc[1:-1]
    return '  Constraints: %s' % cdoc


def single_subparser_possible(cmdlineargs, parser, completing):
    """Performs early analysis of the cmdline

    Looks at the first unparsed argument and if a known command,
    would return only that one.

    When a plain command invocation with `--version` is detected, it will be
    acted on directly (until sys.exit(0) to avoid wasting time on unnecessary
    further processing.

    Returns
    -------
    {'error', 'allknown', 'help', 'unknownopt', 'subcommand'}, None or str
        Returns a status label and a parameter for this status.
        'error': parsing failed, 'allknown': the parser successfully
        identified all arguments, 'help': a help request option was found,
        'unknownopt': an unknown or incomplete option was found,
        'subcommand': a potential subcommand name was found. For the latter
        two modes the second return value is the option or command name.
        For all other modes the second return value is None.
    """
    # Before doing anything additional and possibly expensive see may be that
    # we have got the command already
    try:
        parsed_args, unparsed_args = parser._parse_known_args(
            cmdlineargs[1:], argparse.Namespace())
        # before anything handle possible datalad --version
        if not unparsed_args and getattr(parsed_args, 'version', None):
            parsed_args.version()  # will exit with 0
        if not (completing or unparsed_args):
            # there was nothing that could be a command
            fail_with_short_help(
                parser,
                msg="too few arguments, "
                    "run with --help or visit https://handbook.datalad.org",
                exit_code=2)
        lgr.debug("Command line args 1st pass for DataLad %s. "
                  "Parsed: %s Unparsed: %s",
                  __version__, parsed_args, unparsed_args)
    except Exception as exc:
        # this did not work out
        from datalad.support.exceptions import CapturedException
        ce = CapturedException(exc)
        lgr.debug("Early parsing failed with %s", ce)
        return 'error', None

    if not unparsed_args:
        # cannot possibly be a subcommand
        return 'allknown', None

    unparsed_arg = unparsed_args[0]

    # First unparsed could be either unknown option to top level "datalad"
    # or a command. Among unknown could be --help/--help-np which would
    # need to be dealt with
    if unparsed_arg in ('--help', '--help-np', '-h'):
        # not need to try to tune things, all these will result in everything
        # to be imported and parsed
        return 'help', None
    elif unparsed_arg.startswith('-'):  # unknown or incomplete option
        if completing:
            return 'unknownopt', unparsed_arg
        # will sys.exit
        fail_with_short_help(parser,
                             msg=f"unrecognized argument {unparsed_arg}",
                             # matches exit code of InsufficientArgumentsError
                             exit_code=2)
    else:  # potential command to handle
        return 'subcommand', unparsed_arg


def try_suggest_extension_with_command(parser, cmd, completing, known_cmds):
    """If completing=False, this function will trigger sys.exit()"""
    # check if might be coming from known extensions
    from .interface import (
        _known_extension_commands,
        _deprecated_commands,
    )
    extension_commands = {
        c: e
        for e, commands in _known_extension_commands.items()
        for c in commands
    }
    hint = None
    if cmd in extension_commands:
        hint = "Command %s is provided by (not installed) extension %s." \
               % (cmd, extension_commands[cmd])
    elif cmd in _deprecated_commands:
        hint_cmd = _deprecated_commands[cmd]
        hint = "Command %r was deprecated" % cmd
        hint += (" in favor of %r command." % hint_cmd) if hint_cmd else '.'
    if not completing:
        fail_with_short_help(
            parser,
            hint=hint,
            provided=cmd,
            known=list(known_cmds.keys()) + list(extension_commands.keys())
        )


def add_subparser(_intfspec, subparsers, cmd_name, formatter_class,
                  completing=False):
    """Given an interface spec, add a subparser to subparsers under cmd_name
    """
    _intf = load_interface(_intfspec)
    if _intf is None:
        # failed to load, error was already logged
        return

    # compose argparse.add_parser() arguments, focused on docs
    parser_args = dict(formatter_class=formatter_class)
    # use class description, if no explicit description is available
    intf_doc = get_cmd_doc(_intf)
    if not completing:
        parser_args['description'] = alter_interface_docs_for_cmdline(
            intf_doc)
        if hasattr(_intf, '_examples_'):
            intf_ex = alter_interface_docs_for_cmdline(get_cmd_ex(_intf))
            parser_args['description'] += intf_ex

    # create the sub-parser
    subparser = subparsers.add_parser(cmd_name, add_help=False, **parser_args)
    # our own custom help for all commands, we must do it here
    # (not in setup_parser_for_interface()) because the top-level parser must
    # not unconditionally have it available initially
    parser_add_common_opt(subparser, 'help')
    # let module configure the parser
    setup_parser_for_interface(subparser, _intf, completing=completing)
    # and we would add custom handler for --version
    parser_add_version_opt(
        subparser, _intf.__module__.split('.', 1)[0], include_name=True)
    # logger for command
    # configure 'run' function for this command
    plumbing_args = dict(
        # this is the key execution handler
        func=partial(call_from_parser, _intf),
        # use the logger of the module that defined the interface
        logger=logging.getLogger(_intf.__module__),
        subparser=subparser)
    if hasattr(_intf, 'result_renderer_cmdline'):
        plumbing_args['result_renderer'] = _intf.result_renderer_cmdline
    subparser.set_defaults(**plumbing_args)
    return subparser


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


def parser_add_common_opt(parser, opt, names=None, **kwargs):
    opt_tmpl = common_args[opt]
    opt_kwargs = opt_tmpl[1].copy()
    opt_kwargs.update(kwargs)
    if names is None:
        parser.add_argument(*opt_tmpl[0], **opt_kwargs)
    else:
        parser.add_argument(*names, **opt_kwargs)


def parser_add_common_options(parser, version=None):
    """Add all options defined in common_args, but excludes 'help'"""
    # populate with standard options
    for arg in common_args:
        if arg == 'help':
            continue
        parser_add_common_opt(parser, arg)
    # special case version arg
    if version is not None:
        import warnings
        warnings.warn("Passing 'version' to parser_add_common_options "
                      "no longer has an effect "
                      "and will be removed in a future release.",
                      DeprecationWarning)
    parser_add_version_opt(parser, 'datalad', include_name=True, delay=True)


def parser_add_version_opt(parser, mod_name, include_name=False, delay=False):
    """Setup --version option

    Parameters
    ----------
    parser:
    mod_name: str, optional
    include_name: bool, optional
    delay: bool, optional
      If set to True, no action is taken immediately, and rather
      we assign the function which would print the version. Necessary for
      early pre-parsing of the cmdline
    """

    def print_version():
        mod = sys.modules.get(mod_name, None)
        version = getattr(mod, '__version__', None)
        if version is None:
            # Let's use the standard Python mechanism if underlying module
            # did not provide __version__
            try:
                import pkg_resources
                version = pkg_resources.get_distribution(mod_name).version
            except Exception:
                version = "unknown"
        if include_name:
            print("%s %s" % (mod_name, version))
        else:
            print(version)
        sys.exit(0)

    class versionAction(argparse.Action):
        def __call__(self, parser, args, values, option_string=None):
            if delay:
                setattr(args, self.dest, print_version)
            else:
                print_version()

    parser.add_argument(
        "--version",
        nargs=0,
        action=versionAction,
        help=(
            "show the program's version"
            if not mod_name
            else "show the module and its version which provides the command")
    )


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
            parser_add_common_opt(parser, 'help')
            # just to appear in print_usage also consistent with --help output
            parser.add_argument("command [command-opts]")
            parser.print_usage(file=out)
    else:
        out.write(
            "datalad: Unknown %s %r.  See 'datalad --help'.\n\n"
            % (what, provided,))
        if provided not in known:
            from datalad.utils import get_suggestions_msg
            out.write(get_suggestions_msg(provided, known))
    if hint:
        out.write("Hint: %s\n" % hint)
    raise SystemExit(exit_code)
