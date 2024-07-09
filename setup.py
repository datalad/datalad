#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import sys
from os.path import dirname
from os.path import join as opj

# This is needed for versioneer to be importable when building with PEP 517.
# See <https://github.com/warner/python-versioneer/issues/193> and links
# therein for more information.
sys.path.append(dirname(__file__))

import versioneer
from _datalad_build_support.setup import (
    BuildConfigInfo,
    BuildManPage,
    datalad_setup,
)

requires = {
    'core': [
        'platformdirs',
        'chardet>=3.0.4',      # rarely used but small/omnipresent
        'colorama; platform_system=="Windows"',
        'distro; python_version >= "3.8"',
        'importlib-metadata >=3.6; python_version < "3.10"',
        'importlib-resources >= 3.0; python_version < "3.9"',
        'iso8601',
        'humanize',
        'fasteners>=0.14',
        'packaging',
        'patool>=1.7',
        'tqdm>=4.32.0',
        'typing_extensions>=4.0.0; python_version < "3.11"',
        'annexremote',
        'looseversion',
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
        'pytest',
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
        'coverage',
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

cmdclass = {
    'build_manpage': BuildManPage,
    # 'build_examples': BuildRSTExamplesFromScripts,
    'build_cfginfo': BuildConfigInfo,
    # 'build_py': DataladBuild
}

setup_kwargs = {}

# normal entrypoints for the rest
# a bit of a dance needed, as on windows the situation is different
entry_points = {
    'console_scripts': [
        'datalad=datalad.cli.main:main',
        'git-annex-remote-datalad-archives=datalad.customremotes.archives:main',
        'git-annex-remote-datalad=datalad.customremotes.datalad:main',
        'git-annex-remote-ria=datalad.customremotes.ria_remote:main',
        'git-annex-remote-ora=datalad.distributed.ora_remote:main',
        'git-credential-datalad=datalad.local.gitcredential_datalad:git_credential_datalad',
    ],
}
setup_kwargs['entry_points'] = entry_points

classifiers = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'Intended Audience :: Education',
    'Intended Audience :: End Users/Desktop',
    'Intended Audience :: Science/Research',
    'License :: DFSG approved',
    'License :: OSI Approved :: MIT License',
    'Natural Language :: English',
    'Operating System :: POSIX',
    'Programming Language :: Python :: 3 :: Only',
    'Programming Language :: Unix Shell',
    'Topic :: Communications :: File Sharing',
    'Topic :: Education',
    'Topic :: Internet',
    'Topic :: Other/Nonlisted Topic',
    'Topic :: Scientific/Engineering',
    'Topic :: Software Development :: Libraries :: Python Modules',
    'Topic :: Software Development :: Version Control :: Git',
    'Topic :: Utilities',
]
setup_kwargs['classifiers'] = classifiers

setup_kwargs["version"] = versioneer.get_version()
cmdclass.update(versioneer.get_cmdclass())

datalad_setup(
    'datalad',
    description="data distribution geared toward scientific datasets",
    install_requires=
        requires['core'] + requires['downloaders'] +
        requires['publish'],
    python_requires='>=3.8',
    project_urls={'Homepage': 'https://www.datalad.org',
                  'Developer docs': 'https://docs.datalad.org/en/stable',
                  'User handbook': 'https://handbook.datalad.org',
                  'Source': 'https://github.com/datalad/datalad',
                  'Bug Tracker': 'https://github.com/datalad/datalad/issues',
                  'RRID': 'https://identifiers.org/RRID:SCR_003931'},
    extras_require=requires,
    cmdclass=cmdclass,
    include_package_data=True,
    **setup_kwargs
)
