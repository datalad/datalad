#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import platform

from glob import glob
import os
from os.path import sep as pathsep, join as opj, dirname

from setuptools import setup, find_packages

# imports for manpage generation
import datetime
from distutils.command.build import build
from distutils.core import Command
import argparse

# This might entail lots of imports which might not yet be available
# so let's do ad-hoc parsing of the version.py
#import datalad.version
with open(opj(dirname(__file__), 'datalad', 'version.py')) as f:
    version_lines = list(filter(lambda x: x.startswith('__version__'), f))
assert(len(version_lines) == 1)
version = version_lines[0].split('=')[1].strip(" '\"\t\n")

# Only recentish versions of find_packages support include
# datalad_pkgs = find_packages('.', include=['datalad*'])
# so we will filter manually for maximal compatibility
datalad_pkgs = [pkg for pkg in find_packages('.') if pkg.startswith('datalad')]

# keyring is a tricky one since it got split into two as of 8.0 and on older
# systems there is a problem installing via pip (e.g. on wheezy) so for those we
# would just ask for keyring
keyring_requires = ['keyring>=8.0', 'keyrings.alt']
pbar_requires = ['tqdm']

dist = platform.dist()
# on oldstable Debian let's ask for lower versions and progressbar instead
if dist[0] == 'debian' and dist[1].split('.', 1)[0] == '7':
    keyring_requires = ['keyring<8.0']
    pbar_requires = ['progressbar']

requires = {
    'core': [
        'appdirs',
        'GitPython>=2.0',
        'humanize',
        'mock',  # mock is also used for auto.py, not only for testing
        'patool>=1.7',
        'six>=1.8.0',
    ] + pbar_requires,
    'downloaders': [
        'boto',
        'msgpack-python',
        'requests>=1.2',
    ] + keyring_requires,
    'crawl': [
        'scrapy>=1.1.0rc3',  # versioning is primarily for python3 support
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.8.14',
        'mock',
        'nose>=1.3.4',
        'testtools',
        'vcrpy',
    ]
}
requires['full'] = sum(list(requires.values()), [])

#############################################################################
## Start of manpage generator code ##########################################
#############################################################################

# The BuildManPage code was originally distributed
# under the same License of Python
# Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>

"""
Add a `build_manpage` command  to your setup.py.
To use this Command class import the class to your setup.py,
and add a command to call this class::

    from build_manpage import BuildManPage

    ...
    ...

    setup(
    ...
    ...
    cmdclass={
        'build_manpage': BuildManPage,
    )

You can then use the following setup command to produce a man page::

    $ python setup.py build_manpage --output=prog.1
        --parser=yourmodule:argparser

Alternatively, set the variable AUTO_BUILD to True, and just invoke::

    $ python setup.py build

If automatically want to build the man page every time you invoke your build,
add to your ```setup.cfg``` the following::

    [build_manpage]
    output = <appname>.1
    parser = <path_to_your_parser>
"""

build.sub_commands.append(('build_manpage', None))


class BuildManPage(Command):

    description = 'Generate man page from an ArgumentParser instance.'

    user_options = [
        ('man_path=', None, 'output path for manpages'),
        ('rst_path=', None, 'output path for RST files'),
        ('parser=', None, 'module path to an ArgumentParser instance'
         '(e.g. mymod:func, where func is a method or function which return'
         'a dict with one or more arparse.ArgumentParser instances.'),
    ]

    def initialize_options(self):
        self.man_path = None
        self.rst_path = None
        self.parser = None

    def finalize_options(self):
        if self.man_path is None:
            raise DistutilsOptionError('\'man_path\' option is required')
        if self.rst_path is None:
            raise DistutilsOptionError('\'rst_path\' option is required')
        if self.parser is None:
            raise DistutilsOptionError('\'parser\' option is required')
        mod_name, func_name = self.parser.split(':')
        fromlist = mod_name.split('.')
        try:
            mod = __import__(mod_name, fromlist=fromlist)
            self._parser = getattr(mod, func_name)(
                formatter_class=ManPageFormatter,
                return_subparsers=True)

        except ImportError as err:
            raise err

        self.announce('Writing man page(s) to %s' % self.man_path)
        self._today = datetime.date.today()

    def run(self):

        dist = self.distribution
        #homepage = dist.get_url()
        #appname = self._parser.prog
        appname = 'datalad'

        sections = {
            'Authors': """{0} is developed by {1} <{2}>.""".format(
                appname, dist.get_author(), dist.get_author_email()),
        }

        dist = self.distribution
        for cls, opath, ext in ((ManPageFormatter, self.man_path, '1'),
                                (RSTManPageFormatter, self.rst_path, 'rst')):
            if not os.path.exists(opath):
                os.makedirs(opath)
            for cmdname in self._parser:
                p = self._parser[cmdname]
                cmdname = "{0}{1}".format(
                    'datalad-' if cmdname != 'datalad' else '',
                    cmdname)
                format = cls(cmdname, ext_sections=sections)
                formatted = format.format_man_page(p)
                with open(opj(opath, '{0}.{1}'.format(
                            cmdname,
                            ext)),
                          'w') as f:
                    f.write(formatted)


class ManPageFormatter(argparse.HelpFormatter):

    """
    Formatter class to create man pages.
    This class relies only on the parser, and not distutils.
    The following shows a scenario for usage::

        from pwman import parser_options
        from build_manpage import ManPageFormatter

        # example usage ...

        dist = distribution
        mpf = ManPageFormatter(appname,
                               desc=dist.get_description(),
                               long_desc=dist.get_long_description(),
                               ext_sections=sections)

        # parser is an ArgumentParser instance
        m = mpf.format_man_page(parsr)

        with open(self.output, 'w') as f:
            f.write(m)

    The last line would print all the options and help infomation wrapped with
    man page macros where needed.
    """

    def __init__(self,
                 prog,
                 indent_increment=2,
                 max_help_position=24,
                 width=None,
                 section=1,
                 ext_sections=None,
                 authors=None,
                 ):

        super(ManPageFormatter, self).__init__(prog)

        self._prog = prog
        self._section = 1
        self._today = datetime.date.today().strftime('%Y\\-%m\\-%d')
        self._ext_sections = ext_sections

    def _get_formatter(self, **kwargs):
        return self.formatter_class(prog=self.prog, **kwargs)

    def _markup(self, txt):
        return txt.replace('-', '\\-')

    def _underline(self, string):
        return "\\fI\\s-1" + string + "\\s0\\fR"

    def _bold(self, string):
        if not string.strip().startswith('\\fB'):
            string = '\\fB' + string
        if not string.strip().endswith('\\fR'):
            string = string + '\\fR'
        return string

    def _mk_synopsis(self, parser):
        self.add_usage(parser.usage, parser._actions,
                       parser._mutually_exclusive_groups, prefix='')
        usage = self._format_usage(None, parser._actions,
                                   parser._mutually_exclusive_groups, '')

        usage = usage.replace('%s ' % self._prog, '')
        usage = '.SH SYNOPSIS\n \\fB%s\\fR %s\n' % (self._markup(self._prog),
                                                    usage)
        return usage

    def _mk_title(self, prog):
        return '.TH {0} {1} {2}\n'.format(prog, self._section,
                                          self._today)

    def _make_name(self, parser):
        """
        this method is in consitent with others ... it relies on
        distribution
        """
        return '.SH NAME\n%s \\- %s\n' % (parser.prog,
                                          parser.description)

    def _mk_description(self, parser):
        desc = parser.description
        if not desc:
            return ''
        desc = desc.replace('\n', '\n.br\n')
        return '.SH DESCRIPTION\n%s\n' % self._markup(desc)

    def _mk_footer(self, sections):
        if not hasattr(sections, '__iter__'):
            return ''

        footer = []
        for section, value in sections.items():
            part = ".SH {}\n {}".format(section.upper(), value)
            footer.append(part)

        return '\n'.join(footer)

    def format_man_page(self, parser):
        page = []
        page.append(self._mk_title(self._prog))
        page.append(self._mk_synopsis(parser))
        page.append(self._mk_description(parser))
        page.append(self._mk_options(parser))
        page.append(self._mk_footer(self._ext_sections))

        return ''.join(page)

    def _mk_options(self, parser):

        formatter = parser._get_formatter()

        # positionals, optionals and user-defined groups
        for action_group in parser._action_groups:
            formatter.start_section(None)
            formatter.add_text(None)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(parser.epilog)

        # determine help from format above
        return '.SH OPTIONS\n' + formatter.format_help()

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend([self._bold(action_str) for action_str in
                              action.option_strings])

            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            else:
                default = self._underline(action.dest.upper())
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append('%s %s' % (self._bold(option_string),
                                            args_string))

            return ', '.join(parts)

#############################################################################
## End of manpage generator code ############################################
#############################################################################


class RSTManPageFormatter(ManPageFormatter):
    def _get_formatter(self, **kwargs):
        return self.formatter_class(prog=self.prog, **kwargs)

    def _markup(self, txt):
        # put general tune-ups here
        return txt

    def _underline(self, string):
        return "*{0}*".format(string)

    def _bold(self, string):
        return "**{0}**".format(string)

    def _mk_synopsis(self, parser):
        self.add_usage(parser.usage, parser._actions,
                       parser._mutually_exclusive_groups, prefix='')
        usage = self._format_usage(None, parser._actions,
                                   parser._mutually_exclusive_groups, '')

        usage = usage.replace('%s ' % self._prog, '')
        usage = 'Synopsis\n--------\n::\n\n  %s %s\n' % (self._markup(self._prog),
                                                    usage)
        return usage

    def _mk_title(self, prog):
        title = "{0}".format(prog)
        title += '\n{0}\n\n'.format('=' * len(title))
        return title

    def _make_name(self, parser):
        return ''

    def _mk_description(self, parser):
        desc = parser.description
        if not desc:
            return ''
        return 'Description\n-----------\n%s\n' % self._markup(desc)

    def _mk_footer(self, sections):
        if not hasattr(sections, '__iter__'):
            return ''

        footer = []
        for section, value in sections.items():
            part = "\n{0}\n{1}\n{2}\n".format(
                section,
                '-' * len(section),
                value)
            footer.append(part)

        return '\n'.join(footer)

    def _mk_options(self, parser):

        # this non-obvious maneuver is really necessary!
        formatter = self.__class__(self._prog)

        # positionals, optionals and user-defined groups
        for action_group in parser._action_groups:
            formatter.start_section(None)
            formatter.add_text(None)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(parser.epilog)

        # determine help from format above
        option_sec = formatter.format_help()

        return '\n\nOptions\n-------\n{0}'.format(option_sec)

    def _format_action(self, action):
        # determine the required width and the entry label
        action_header = self._format_action_invocation(action)

        # if there was help for the action, add lines of help text
       # if action.help:
       #     help_text = self._expand_help(action)
       #     help_lines = self._split_lines(help_text, help_width)
       #     parts.append('%*s%s\n' % (indent_first, '', help_lines[0]))
       #     for line in help_lines[1:]:
       #         parts.append('%*s%s\n' % (help_position, '', line))

        if action.help:
            help_text = self._expand_help(action)
            help_lines = self._split_lines(help_text, 80)
            help = ' '.join(help_lines)
        else:
            help = ''

        # return a single string
        from datalad.interface.base import dedent_docstring
        return '{0}\n{1}\n{2}\n\n'.format(
            action_header,
            '~' * len(action_header),
            help)
        #' '.join([dedent_docstring(s) for s in action.help.split('\n')]) \
         #       if action.help else '')
#

from distutils.command.build_py import build_py

class my_build(build_py):
    def run(self):
        self.run_command('build_manpage')
        build_py.run(self)

cmdclass={
    'build_manpage': BuildManPage,
    'build_py': my_build
}

setup(
    name="datalad",
    author="The DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=version,
    description="data distribution geared toward scientific datasets",
    packages=datalad_pkgs,
    install_requires=requires['core'] + requires['downloaders'],
    extras_require=requires,
    entry_points={
        'console_scripts': [
            'datalad=datalad.cmdline.main:main',
            'git-annex-remote-datalad-archives=datalad.customremotes.archives:main',
            'git-annex-remote-datalad=datalad.customremotes.datalad:main',
        ],
    },
    cmdclass=cmdclass,
    package_data={
        'datalad': [
            'resources/git_ssh.sh',
            'resources/sshserver_cleanup_after_publish.sh',
            'resources/sshserver_prepare_for_publish.sh',
        ] +
        [p.split(pathsep, 1)[1] for p in glob('datalad/downloaders/configs/*.cfg')]
    }
)
