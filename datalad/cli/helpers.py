# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""CONFIRMED TO BE UNIQUE TO THE CLI
"""

__docformat__ = 'restructuredtext'

import argparse
import os
import re
import sys
import gzip
import textwrap
from textwrap import wrap

from datalad import __version__
# delay?
from datalad.support.exceptions import CapturedException
from datalad.ui.utils import get_console_width
from datalad.utils import is_interactive

from platformdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


from logging import getLogger
lgr = getLogger('datalad.cli.helpers')


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
        if "essential commands" in helpstr.lower():
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
        helpstr = re.sub(r'optional arguments:', opt_args_str, helpstr)
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
        from datalad.log import LoggerHelper
        LoggerHelper().set_level(level=values)


#
# Some logic modules extracted from main.py to de-spagetify
#


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
    from .interface import get_cmdline_command_name
    return {
        get_cmdline_command_name(_intfspec): _intfspec
        for _, _, _interfaces in groups
        for _intfspec in _interfaces
    }


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
    from .interface import (
        dedent_docstring,
    )
    from datalad.interface.base import get_cmd_summaries
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
