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

# manpage build imports
from distutils.command.build_py import build_py
from distutils.core import Command
from distutils.errors import DistutilsOptionError
import datetime
from formatters import ManPageFormatter, RSTManPageFormatter

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


class BuildManPage(Command):
    # The BuildManPage code was originally distributed
    # under the same License of Python
    # Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>

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


# configure additional command for custom build steps
class DataladBuild(build_py):
    def run(self):
        self.run_command('build_manpage')
        build_py.run(self)

cmdclass = {
    'build_manpage': BuildManPage,
    'build_py': DataladBuild
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
