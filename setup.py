#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from setuptools import setup

import versioneer
from _datalad_build_support.setup import (
    BuildConfigInfo,
    BuildManPage,
)

<<<<<<< HEAD
=======
requires = {
    'core': [
        'platformdirs',
        'chardet>=3.0.4',      # rarely used but small/omnipresent
        'colorama; platform_system=="Windows"',
        'distro',
        'importlib-metadata >=3.6; python_version < "3.10"',
        'iso8601',
        'humanize',
        'fasteners>=0.14',
        'packaging',
        'patool>=1.7',
        'tqdm>=4.32.0',
        'typing_extensions>=4.0.0; python_version < "3.11"',
        'annexremote',
        'looseversion',
        "giturlparse",
    ],
    'downloaders': [
        'boto3',
        'keyring>=20.0,!=23.9.0',
        'keyrings.alt',
        'msgpack',
        'requests>=1.2',
    ],
    'downloaders-extra': [
        'requests_ftp',
    ],
    'publish': [
        'python-gitlab',     # required for create-sibling-gitlab
    ],
    'misc': [
        'argcomplete>=1.12.3',  # optional CLI completion
        'pyperclip',         # clipboard manipulations
        'python-dateutil',   # add support for more date formats to check_dates
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.9.4',  # Introduced py 3.6 support
        'mypy',
        'pytest>=7.0',  # https://github.com/datalad/datalad/issues/7555
        'pytest-cov',
        'pytest-fail-slow~=0.2',
        'types-python-dateutil',
        'types-requests',
        'vcrpy',
    ],
    'duecredit': [
        'duecredit',  # needs >= 0.6.6 to be usable, but should be "safe" with prior ones
    ],
}

requires['full'] = sum(list(requires.values()), [])

# Now add additional ones useful for development
requires.update({
    'devel-docs': [
        # used for converting README.md -> .rst for long_description
        'pypandoc',
        # Documentation
        'sphinx>=4.3.0',
        'sphinx-autodoc-typehints',
        'sphinx-rtd-theme>=0.5.1',
    ],
    'devel-utils': [
        'asv',        # benchmarks
        'coverage!=7.6.5',
        'gprof2dot',  # rendering cProfile output as a graph image
        'psutil',
        'pytest-xdist',  # parallelize pytest runs etc
        # disable for now, as it pulls in ipython 6, which is PY3 only
        #'line-profiler',
        # necessary for accessing SecretStorage keyring (system wide Gnome
        # keyring)  but not installable on travis, IIRC since it needs connectivity
        # to the dbus whenever installed or smth like that, thus disabled here
        # but you might need it
        # 'dbus-python',
        'scriv',  # changelog
    ],
})
requires['devel'] = sum(list(requires.values()), [])


# let's not build manpages and examples automatically (gh-896)
# configure additional command for custom build steps
#class DataladBuild(build_py):
#    def run(self):
#        self.run_command('build_manpage')
#        self.run_command('build_examples')
#        build_py.run(self)

>>>>>>> 7318b57fd (add submodule URL candidates by URL-rewrite to match parent protocol)
cmdclass = {
    "build_manpage": BuildManPage,
    # 'build_examples': BuildRSTExamplesFromScripts,
    "build_cfginfo": BuildConfigInfo,
    # 'build_py': DataladBuild
}
cmdclass = versioneer.get_cmdclass(cmdclass)

setup(cmdclass=cmdclass)
