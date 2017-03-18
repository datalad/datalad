# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


import os
import platform
import sys
from genericpath import exists
from os import linesep, makedirs
from os.path import dirname, join as opj

from distutils.core import Command
from distutils.errors import DistutilsOptionError
import datetime
import formatters as fmt


def _path_rel2file(p):
    return opj(dirname(__file__), p)


def get_version():
    """Load version of datalad from version.py without entailing any imports
    """
    # This might entail lots of imports which might not yet be available
    # so let's do ad-hoc parsing of the version.py
    with open(opj(dirname(__file__), 'datalad', 'version.py')) as f:
        version_lines = list(filter(lambda x: x.startswith('__version__'), f))
    assert (len(version_lines) == 1)
    return version_lines[0].split('=')[1].strip(" '\"\t\n")


class BuildManPage(Command):
    # The BuildManPage code was originally distributed
    # under the same License of Python
    # Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>

    description = 'Generate man page from an ArgumentParser instance.'

    user_options = [
        ('manpath=', None, 'output path for manpages'),
        ('rstpath=', None, 'output path for RST files'),
        ('parser=', None, 'module path to an ArgumentParser instance'
         '(e.g. mymod:func, where func is a method or function which return'
         'a dict with one or more arparse.ArgumentParser instances.'),
    ]

    def initialize_options(self):
        self.manpath = opj('build', 'man')
        self.rstpath = opj('docs', 'source', 'generated', 'man')
        self.parser = 'datalad.cmdline.main:setup_parser'

    def finalize_options(self):
        if self.manpath is None:
            raise DistutilsOptionError('\'manpath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        if self.parser is None:
            raise DistutilsOptionError('\'parser\' option is required')
        self.manpath = _path_rel2file(self.manpath)
        self.rstpath = _path_rel2file(self.rstpath)
        mod_name, func_name = self.parser.split(':')
        fromlist = mod_name.split('.')
        try:
            mod = __import__(mod_name, fromlist=fromlist)
            self._parser = getattr(mod, func_name)(
                formatter_class=fmt.ManPageFormatter,
                return_subparsers=True)

        except ImportError as err:
            raise err

        self.announce('Writing man page(s) to %s' % self.manpath)
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
        for cls, opath, ext in ((fmt.ManPageFormatter, self.manpath, '1'),
                                (fmt.RSTManPageFormatter, self.rstpath, 'rst')):
            if not os.path.exists(opath):
                os.makedirs(opath)
            for cmdname in self._parser:
                p = self._parser[cmdname]
                cmdname = "{0}{1}".format(
                    'datalad-' if cmdname != 'datalad' else '',
                    cmdname)
                format = cls(cmdname, ext_sections=sections, version=get_version())
                formatted = format.format_man_page(p)
                with open(opj(opath, '{0}.{1}'.format(
                        cmdname,
                        ext)),
                        'w') as f:
                    f.write(formatted)


class BuildRSTExamplesFromScripts(Command):
    description = 'Generate RST variants of example shell scripts.'

    user_options = [
        ('expath=', None, 'path to look for example scripts'),
        ('rstpath=', None, 'output path for RST files'),
    ]

    def initialize_options(self):
        self.expath = opj('docs', 'examples')
        self.rstpath = opj('docs', 'source', 'generated', 'examples')

    def finalize_options(self):
        if self.expath is None:
            raise DistutilsOptionError('\'expath\' option is required')
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        self.expath = _path_rel2file(self.expath)
        self.rstpath = _path_rel2file(self.rstpath)
        self.announce('Converting example scripts')

    def run(self):
        opath = self.rstpath
        if not os.path.exists(opath):
            os.makedirs(opath)

        from glob import glob
        for example in glob(opj(self.expath, '*.sh')):
            exname = os.path.basename(example)[:-3]
            with open(opj(opath, '{0}.rst'.format(exname)), 'w') as out:
                fmt.cmdline_example_to_rst(
                    open(example),
                    out=out,
                    ref='_example_{0}'.format(exname))


class BuildConfigInfo(Command):
    description = 'Generate RST documentation for all config items.'

    user_options = [
        ('rstpath=', None, 'output path for RST file'),
    ]

    def initialize_options(self):
        self.rstpath = opj('docs', 'source', 'generated', 'cfginfo')

    def finalize_options(self):
        if self.rstpath is None:
            raise DistutilsOptionError('\'rstpath\' option is required')
        self.rstpath = _path_rel2file(self.rstpath)
        self.announce('Generating configuration documentation')

    def run(self):
        opath = self.rstpath
        if not os.path.exists(opath):
            os.makedirs(opath)

        from datalad.interface.common_cfg import definitions as cfgdefs
        from datalad.dochelpers import _indent

        categories = {
            'global': {},
            'local': {},
            'dataset': {},
            'misc': {}
        }
        for term, v in cfgdefs.items():
            categories[v.get('destination', 'misc')][term] = v

        for cat in categories:
            with open(opj(opath, '{}.rst'.format(cat)), 'w') as rst:
                rst.write('.. glossary::\n')
                for term, v in sorted(categories[cat].items(), key=lambda x: x[0]):
                    rst.write(_indent(term, '\n  '))
                    qtype, docs = v.get('ui', (None, {}))
                    desc_tmpl = '\n'
                    if 'title' in docs:
                        desc_tmpl += '{title}:\n'
                    if 'text' in docs:
                        desc_tmpl += '{text}\n'
                    if 'default' in v:
                        default = v['default']
                        if hasattr(default, 'replace'):
                            # protect against leaking specific home dirs
                            v['default'] = default.replace(os.path.expanduser('~'), '~')
                        desc_tmpl += 'Default: {default}\n'
                    if 'type' in v:
                        type_ = v['type']
                        if hasattr(type_, 'long_description'):
                            type_ = type_.long_description()
                        else:
                            type_ = type_.__name__
                        desc_tmpl += '\n[{type}]\n'
                        v['type'] = type_
                    if desc_tmpl == '\n':
                        # we need something to avoid joining terms
                        desc_tmpl += 'undocumented\n'
                    v.update(docs)
                    rst.write(_indent(desc_tmpl.format(**v), '    '))


def setup_entry_points(entry_points):
    """Sneaky monkey patching could be fixed only via even sneakier monkey patching

    It will never break, I promise!
    """

    def get_script_content(script_name, shebang="#!/usr/bin/env python"):
        return linesep.join([
            shebang,
            "#",
            "# Custom simplistic runner for DataLad. Assumes datalad module",
            "# being available.  Generated by monkey patching monkey patched",
            "# setuptools.",
            "#",
            "from %s import main" % entry_points[script_name],
            "main()",
            ""]).encode()

    def patch_write_script(mod):
        """Patches write_script of the module with our shim to provide
        lightweight invocation script
        """

        orig_meth = getattr(mod, 'write_script')

        def _provide_lean_script_contents(
                self, script_name, contents, mode="t", *ignored):
            # could be a script from another module -- let it be as is
            if script_name in entry_points:
                # keep shebang
                contents = get_script_content(
                    script_name,
                    contents.splitlines()[0].decode())
            return orig_meth(self, script_name, contents, mode=mode)

        setattr(mod, 'write_script', _provide_lean_script_contents)

    # We still need this one so that setuptools known about the scripts
    # So we generate some bogus ones, and provide a list of them ;)
    # pre-generate paths so we could give them to setuptools
    scripts_build_dir = opj('build', 'scripts_generated')
    scripts = [opj(scripts_build_dir, x) for x in entry_points]

    if 'clean' not in sys.argv:
        if not exists(scripts_build_dir):
            makedirs(scripts_build_dir)
        for s, mod in entry_points.items():
            with open(opj(scripts_build_dir, s), 'wb') as f:
                f.write(get_script_content(s))

    platform_system = platform.system().lower()
    setup_kwargs = {}

    if platform_system == 'windows':
        # TODO: investigate https://github.com/matthew-brett/myscripter,
        # nibabel/nixext approach to support similar setup on Windows
        setup_kwargs['entry_points'] = {
            'console_scripts': ['%s=%s:main' % i for i in entry_points.items()]
        }
    else:
        # Damn you sharktopus!
        from setuptools.command.install_scripts import \
            install_scripts as stinstall_scripts
        from setuptools.command.easy_install import easy_install

        patch_write_script(stinstall_scripts)
        patch_write_script(easy_install)

        setup_kwargs['scripts'] = scripts

    return setup_kwargs