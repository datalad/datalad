#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import platform

from glob import glob
from os.path import sep as pathsep, join as opj, dirname

from setuptools import setup, find_packages

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
dist = platform.dist()
keyring_requires = ['keyring<8.0'] \
    if dist[0] == 'debian' and dist[1].split('.', 1)[0] == '7' \
    else ['keyring>=8.0', 'keyrings.alt']

requires = {
    'core': [
        'appdirs',
        'GitPython>=2.0',
        'humanize',
        'mock',  # mock is also used for auto.py, not only for testing
        'patool>=1.7',
        'progressbar',
        'six>=1.8.0',
    ],
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

setup(
    name="datalad",
    author="DataLad Team and Contributors",
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
    package_data={
        'datalad': [
            'resources/git_ssh.sh',
            'resources/sshserver_cleanup_after_publish.sh',
            'resources/sshserver_prepare_for_publish.sh',
        ] +
        [p.split(pathsep, 1)[1] for p in glob('datalad/downloaders/configs/*.cfg')]
    }
)
