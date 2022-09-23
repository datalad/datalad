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
            self._try_manpage(parser)
        if option_string == '-h':
            helpstr = self._get_short_help(parser)
        else:
            helpstr = self._get_long_help(parser)

        # normalize capitalization to what we "always" had
        helpstr = f'Usage:{helpstr[6:]}'

        if interactive and option_string == '--help':
            import pydoc
            pydoc.pager(helpstr)
        else:
            print(helpstr)
        sys.exit(0)

    def _get_long_help(self, parser):
        helpstr = parser.format_help()
        if ' ' in parser.prog:  # subcommand
            # in case of a subcommand there is no need to pull the
            # list of top-level subcommands
            return helpstr
        helpstr = re.sub(
            r'^[uU]sage: .*?\n\s*\n',
            'Usage: datalad [global-opts] command [command-opts]\n\n',
            helpstr,
            flags=re.MULTILINE | re.DOTALL)
        # split into preamble and options
        preamble = []
        options = []
        in_options = False
        for line in helpstr.splitlines():
            if line in ('options:', 'optional arguments:'):
                in_options = True
                continue
            (options if in_options else preamble).append(line)

        intf = self._get_all_interfaces()
        from datalad.interface.base import (
            get_cmd_doc,
            load_interface,
        )
        from .interface import (
            get_cmdline_command_name,
            alter_interface_docs_for_cmdline,
        )
        preamble = get_description_with_cmd_summary(
            # produce a mapping of command groups to
            # [(cmdname, description), ...]
            {
                i[0]: [(
                    get_cmdline_command_name(c),
                    # alter_interface_docs_for_cmdline is only needed, because
                    # some commands use sphinx markup in their summary line
                    # stripping that takes 10-30ms for a typical datalad
                    # installation with some extensions
                    alter_interface_docs_for_cmdline(
                        # we only take the first line
                        get_cmd_doc(
                            # we must import the interface class
                            # this will engage @build_doc -- unavoidable right
                            # now
                            load_interface(c)
                        ).split('\n', maxsplit=1)[0]))
                    for c in i[2]]
                for i in intf
            },
            intf,
            '\n'.join(preamble),
        )
        return '{}\n\n*Global options*\n{}\n'.format(
            preamble,
            '\n'.join(options),
        )

    def _get_short_help(self, parser):
        usage = parser.format_usage()
        hint = "Use '--help' to get more comprehensive information."
        if ' ' in parser.prog:  # subcommand
            # in case of a subcommand there is no need to pull the
            # list of top-level subcommands
            return f"{usage}\n{hint}"

        # get the list of commands and format them like
        # argparse would present subcommands
        commands = get_commands_from_groups(self._get_all_interfaces())
        indent = usage.splitlines()[-1]
        indent = indent[:-len(indent.lstrip())] + ' '
        usage += f'{indent[1:]}{{'
        usage += '\n'.join(wrap(
            ', '.join(sorted(c.strip() for c in commands)),
            break_on_hyphens=False,
            subsequent_indent=indent))
        usage += f'}}\n{indent[1:]}...\n'
        return f"{usage}\n{hint}"

    def _get_all_interfaces(self):
        # load all extensions and command specs
        # this does not fully tune all the command docs
        from datalad.interface.base import get_interface_groups
        interface_groups = get_interface_groups()
        add_entrypoints_to_interface_groups(interface_groups)
        return interface_groups

    def _try_manpage(self, parser):
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


class LogLevelAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        from datalad.log import LoggerHelper
        LoggerHelper().set_level(level=values)


#
# Some logic modules extracted from main.py to de-spagetify
#


def add_entrypoints_to_interface_groups(interface_groups):
    from datalad.support.entrypoints import iter_entrypoints
    for name, _, spec in iter_entrypoints('datalad.extensions', load=True):
        if len(spec) < 2 or not spec[1]:
            # entrypoint identity was logged by the iterator already
            lgr.debug('Extension does not provide a command suite')
            continue
        interface_groups.append((name, spec[0], spec[1]))


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
    detailed_description = '{}{}\n{}\n'.format(
        parser_description,
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
    assign_expr = re.compile(r'[^\s]+\.[^\s]+=[\S]+')
    unset_expr = re.compile(r':[^\s]+\.[^\s=]+')
    noassign = [
        o
        for o in cmdlineargs.cfg_overrides
        if not (assign_expr.match(o) or unset_expr.match(o))
    ]
    if noassign:
        lgr.error(
            "Configuration override without section/variable "
            "or unset marker or value assignment "
            "(must be '(:section.variable|section.variable=value)'): %s",
            noassign)
        sys.exit(3)
    overrides = dict(
        [o[1:], None] if o.startswith(':')
        else o.split('=', 1)
        for o in cmdlineargs.cfg_overrides
    )
    return overrides
