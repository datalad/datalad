# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

__docformat__ = 'restructuredtext'

import argparse
import logging
import os
import re
import sys
import gzip
import textwrap
import warnings
from tempfile import NamedTemporaryFile
from textwrap import wrap

from datalad import __version__
from ..cmd import WitlessRunner as Runner
from ..interface.common_opts import eval_defaults
from ..log import is_interactive
from datalad.support.exceptions import CapturedException
from ..ui.utils import get_console_width
from ..utils import (
    ensure_unicode,
    getpwd,
    unlink,
    get_suggestions_msg,
)

from appdirs import AppDirs
from os.path import join as opj

dirs = AppDirs("datalad", "datalad.org")


from logging import getLogger
lgr = getLogger('datalad.cmdline')


class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        # Lets use the manpage on mature systems but only for subcommands --
        # --help should behave similar to how git does it:
        # regular --help for "git" but man pages for specific commands.
        # It is important since we do discover all subcommands from entry
        # points at run time and thus any static manpage would like be out of
        # date
        interactive = is_interactive()
        if interactive \
                and option_string == '--help' \
                and ' ' in parser.prog:  # subcommand
            try:
                import subprocess
                # get the datalad manpage to use
                manfile = os.environ.get('MANPATH', '/usr/share/man') \
                    + '/man1/{0}.1.gz'.format(parser.prog.replace(' ', '-'))
                # extract version field from the manpage
                if not os.path.exists(manfile):
                    raise IOError("manfile is not found")
                with gzip.open(manfile) as f:
                    man_th = [line for line in f if line.startswith(b".TH")][0]
                man_version = man_th.split(b' ')[-1].strip(b" '\"\t\n").decode('utf-8')

                # don't show manpage if man_version not equal to current datalad_version
                if __version__ != man_version:
                    raise ValueError
                subprocess.check_call(
                    'man %s 2> /dev/null' % manfile,
                    shell=True)
                sys.exit(0)
            except (subprocess.CalledProcessError, IOError, OSError, IndexError, ValueError) as e:
                ce = CapturedException(e)
                lgr.debug("Did not use manpage since %s", ce)
        if option_string == '-h':
            usage = parser.format_usage()
            ucomps = re.match(
                r'(?P<pre>.*){(?P<cmds>.*)}(?P<post>....*)',
                usage,
                re.DOTALL)
            if ucomps:
                ucomps = ucomps.groupdict()
                indent_level = len(ucomps['post']) - len(ucomps['post'].lstrip())
                usage = '{pre}{{{cmds}}}{post}'.format(
                    pre=ucomps['pre'],
                    cmds='\n'.join(wrap(
                        ', '.join(sorted(c.strip() for c in ucomps['cmds'].split(','))),
                        break_on_hyphens=False,
                        subsequent_indent=' ' * indent_level)),
                    post=ucomps['post'],
                )
            helpstr = "%s\n%s" % (
                usage,
                "Use '--help' to get more comprehensive information.")
        else:
            helpstr = parser.format_help()
        # better for help2man
        # for main command -- should be different sections. And since we are in
        # heavy output massaging mode...
        if "commands for dataset operations" in helpstr.lower():
            opt_args_str = '*Global options*'
            pos_args_str = '*Commands*'
            # tune up usage -- default one is way too heavy
            helpstr = re.sub(r'^[uU]sage: .*?\n\s*\n',
                             'Usage: datalad [global-opts] command [command-opts]\n\n',
                             helpstr,
                             flags=re.MULTILINE | re.DOTALL)
            # and altogether remove sections with long list of commands
            helpstr = re.sub(r'positional arguments:\s*\n\s*{.*}\n', '', helpstr)
        else:
            opt_args_str = "*Options*"
            pos_args_str = "*Arguments*"
        # in python 3.10 it switched from "optional arguments" to "options"
        helpstr = re.sub(r'(optional arguments|options):', opt_args_str, helpstr)
        helpstr = re.sub(r'positional arguments:', pos_args_str, helpstr)
        # usage is on the same line
        helpstr = re.sub(r'^usage:', 'Usage:', helpstr)

        if interactive and option_string == '--help':
            import pydoc
            pydoc.pager(helpstr)
        else:
            print(helpstr)
        sys.exit(0)


class LogLevelAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from ..log import LoggerHelper
        LoggerHelper().set_level(level=values)


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
            except:
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


def parser_add_common_opt(parser, opt, names=None, **kwargs):
    from . import common_args
    opt_tmpl = getattr(common_args, opt)
    opt_kwargs = opt_tmpl[2].copy()
    opt_kwargs.update(kwargs)
    if names is None:
        parser.add_argument(*opt_tmpl[1], **opt_kwargs)
    else:
        parser.add_argument(*names, **opt_kwargs)


def parser_add_common_options(parser, version=None):
    parser_add_common_opt(parser, 'log_level')
    parser_add_common_opt(parser, 'pbs_runner')
    parser_add_common_opt(parser, 'change_path')
    if version is not None:
        warnings.warn("Passing 'version' to parser_add_common_options "
                      "no longer has an effect "
                      "and will be removed in a future release.",
                      DeprecationWarning)
    parser_add_version_opt(parser, 'datalad', include_name=True, delay=True)
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
    # CLI analog of eval_params.result_renderer but with `<template>` handling
    # and a different default: in Python API we have None as default and do not render
    # the results but return them.  In CLI we default to "default" renderer
    parser.add_argument(
        '-f', '--output-format', dest='common_output_format',
        default='tailored',
        type=ensure_unicode,
        metavar="{default,json,json_pp,tailored,'<template>'}",
        help="""select format for returned command results. 'tailored'
        enables a command-specific rendering style that is typically
        tailored to human consumption, if there is one for a specific
        command, or otherwise falls back on the the 'default' output
        format (this is the standard behavior); 'default' give one line
        per result reporting action, status, path and an optional message;
        'json' renders a JSON object with all properties for each result (one per
        line); 'json_pp' pretty-prints JSON spanning multiple lines;
        '<template>' reports any value(s) of any result properties in any format
        indicated by the template (e.g. '{path}'; compare with JSON
        output for all key-value choices). The template syntax follows the Python
        "format() language". It is possible to report individual
        dictionary values, e.g. '{metadata[name]}'. If a 2nd-level key contains
        a colon, e.g. 'music:Genre', ':' must be substituted by '#' in the template,
        like so: '{metadata[music#Genre]}'. [Default: '%(default)s']""")
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
    # CLI analog of eval_params.on_failure. TODO: dedup
    parser.add_argument(
        '--on-failure', dest='common_on_failure',
        default=eval_defaults['on_failure'],
        choices=['ignore', 'continue', 'stop'],
        help="""when an operation fails: 'ignore' and continue with remaining
        operations, the error is logged but does not lead to a non-zero exit code
        of the command; 'continue' works like 'ignore', but an error causes a
        non-zero exit code; 'stop' halts on first failure and yields non-zero exit
        code. A failure is any result with status 'impossible' or 'error'.
        [Default: '%(default)s']""")
    parser.add_argument(
        '--cmd', dest='_', action='store_true',
        help="""syntactical helper that can be used to end the list of global
        command line options before the subcommand label. Options taking
        an arbitrary number of arguments may require to be followed by a single
        --cmd in order to enable identification of the subcommand.""")


def strip_arg_from_argv(args, value, opt_names):
    """Strip an originally listed option (with its value) from the list cmdline args
    """
    # Yarik doesn't know better
    if args is None:
        args = sys.argv
    # remove present pbs-runner option
    args_clean = []
    skip = 0
    for i, arg in enumerate(args):
        if skip:
            # we skip only one as instructed
            skip -= 1
            continue
        if not (arg in opt_names and i < len(args) - 1 and args[i + 1] == value):
            args_clean.append(arg)
        else:
            # we need to skip this one and next one
            skip = 1
    return args_clean


def run_via_pbs(args, pbs):
    warnings.warn("Job submission via --pbs-runner is deprecated."
                  "Use something like condor_run",
                  DeprecationWarning)

    assert(pbs in ('condor',))  # for now

    # TODO: RF to support multiple backends, parameters, etc, for now -- just condor, no options
    f = NamedTemporaryFile('w', prefix='datalad-%s-' % pbs, suffix='.submit', delete=False)
    try:
        pwd = getpwd()
        logs = f.name.replace('.submit', '.log')
        exe = args[0]
        # TODO: we might need better way to join them, escaping spaces etc.  There must be a stock helper
        #exe_args = ' '.join(map(repr, args[1:])) if len(args) > 1 else ''
        exe_args = ' '.join(args[1:]) if len(args) > 1 else ''
        f.write("""\
Executable = %(exe)s
Initialdir = %(pwd)s
Output = %(logs)s
Error = %(logs)s
getenv = True

arguments = %(exe_args)s
queue
""" % locals())
        f.close()
        Runner().run(['condor_submit', f.name])
        lgr.info("Scheduled execution via %s.  Logs will be stored under %s", pbs, logs)
    finally:
        unlink(f.name)


def get_repo_instance(path=os.curdir, class_=None):
    """Returns an instance of appropriate datalad repository for path.
    Check whether a certain path is inside a known type of repository and
    returns an instance representing it. May also check for a certain type
    instead of detecting the type of repository.

    Parameters
    ----------
    path: str
      path to check; default: current working directory
    class_: class
      if given, check whether path is inside a repository, that can be
      represented as an instance of the passed class.

    Raises
    ------
    RuntimeError, in case cwd is not inside a known repository.
    """

    from os.path import ismount, exists, normpath, isabs
    from datalad.support.exceptions import InvalidGitRepositoryError
    from ..utils import expandpath
    from ..support.gitrepo import GitRepo
    from ..support.annexrepo import AnnexRepo

    dir_ = expandpath(path)
    abspath_ = path if isabs(path) else dir_
    if class_ is not None:
        if class_ == AnnexRepo:
            type_ = "annex"
        elif class_ == GitRepo:
            type_ = "git"
        else:
            raise RuntimeError("Unknown class %s." % str(class_))

    while not ismount(dir_):  # TODO: always correct termination?
        if exists(opj(dir_, '.git')):
            # found git dir
            if class_ is None:
                # detect repo type:
                try:
                    return AnnexRepo(dir_, create=False)
                except RuntimeError as e:
                    pass
                try:
                    return GitRepo(dir_, create=False)
                except InvalidGitRepositoryError as e:
                    raise RuntimeError("No datalad repository found in %s" %
                                       abspath_)
            else:
                try:
                    return class_(dir_, create=False)
                except (RuntimeError, InvalidGitRepositoryError) as e:
                    raise RuntimeError("No %s repository found in %s." %
                                       (type_, abspath_))
        else:
            dir_ = normpath(opj(dir_, ".."))

    if class_ is not None:
        raise RuntimeError("No %s repository found in %s" % (type_, abspath_))
    else:
        raise RuntimeError("No datalad repository found in %s" % abspath_)

#
# Some logic modules extracted from main.py to de-spagetify
#

def _maybe_get_single_subparser(cmdlineargs, parser, interface_groups,
                                return_subparsers, completing, help_ignore_extensions):
    """Performs early analysis of the cmdline

    Looks at the first unparsed argument and if a known command, would return_subparsers
    is False, would return only that one.

    For the analysis to be complete etc, would also load commands from entrypoints etc

    Returns
    -------
    None or str
    """
    # Before doing anything additional and possibly expensive see may be that
    # we have got the command already
    need_single_subparser = False if return_subparsers else None
    fail_handler = (lambda *a, **kw: True) \
        if return_subparsers else fail_with_short_help
    try:
        parsed_args, unparsed_args = parser._parse_known_args(
            cmdlineargs[1:], argparse.Namespace())
        # before anything handle possible datalad --version
        if not unparsed_args and getattr(parsed_args, 'version', None):
            parsed_args.version()  # will exit with 0
        if not (completing or unparsed_args):
            fail_handler(
                parser,
                msg="too few arguments, run with --help or visit https://handbook.datalad.org",
                exit_code=2)
        lgr.debug("Command line args 1st pass for DataLad %s. Parsed: %s Unparsed: %s",
                  __version__, parsed_args, unparsed_args)
    except Exception as exc:
        ce = CapturedException(exc)
        lgr.debug("Early parsing failed with %s", ce)
        need_single_subparser = False
        unparsed_args = cmdlineargs[1:]  # referenced before assignment otherwise
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
    return need_single_subparser


def _maybe_get_interface_subparser(_intfspec, subparsers, cmd_name, formatter_class, group_name,
                                   grp_short_descriptions):
    """Given an interface spec, add a subparser to subparsers under cmd_name

    That subparser is also gets added to the grp_short_descriptions
    """
    from ..interface.base import (
        alter_interface_docs_for_cmdline,
        get_cmd_doc,
        get_cmd_ex,
        load_interface,
    )
    _intf = load_interface(_intfspec)
    if _intf is None:  # failed to load
        return
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
    parser_add_common_opt(subparser, 'help')
    # let module configure the parser
    _intf.setup_parser(subparser)
    # and we would add custom handler for --version
    parser_add_version_opt(subparser, _intf.__module__.split('.', 1)[0], include_name=True)
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
    grp_short_descriptions[group_name].append((cmd_name, sdescr))
    return subparser


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
            ce = CapturedException(ce)
            lgr.warning('Failed to load entrypoint %s: %s', ep.name, ce)
            continue


def get_commands_from_groups(groups):
    """Get a dictionary of command: interface_spec"""
    from ..interface.base import get_cmdline_command_name
    return {
        get_cmdline_command_name(_intfspec): _intfspec
        for _, _, _interfaces in groups
        for _intfspec in _interfaces
    }


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
            out.write(get_suggestions_msg(provided, known))
    if hint:
        out.write("Hint: %s\n" % hint)
    raise SystemExit(exit_code)


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


def _parse_overrides_from_cmdline(cmdlineargs):
    """parse config overrides provided in command line

    Might exit(3) the entire process if value is not assigned"""
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
    overrides = dict(o.split('=', 1) for o in cmdlineargs.cfg_overrides)
    return overrides
