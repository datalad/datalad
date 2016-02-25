#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# Minimalistic setup.py for now

from glob import glob
from os.path import sep as pathsep

from setuptools import setup, find_packages

import datalad.version

# Only recentish versions of find_packages support include
# datalad_pkgs = find_packages('.', include=['datalad*'])
# so we will filter manually for maximal compatibility
datalad_pkgs = [pkg for pkg in find_packages('.') if pkg.startswith('datalad')]

setup(
    name="datalad",
    author="DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=datalad.version.__version__,
    description="data distribution geared toward scientific datasets",
    packages=datalad_pkgs,
    install_requires=[
        "GitPython",  # 'git://github.com/gitpython-developers/GitPython'
        "rdflib",
        ],
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
        ] + \
        [p.split(pathsep, 1)[1] for p in glob('datalad/downloaders/configs/*.cfg')]
    }
)
