#!/usr/bin/env python
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# Minimalistic setup.py for now

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
    py_modules=['datalad'],
    packages=datalad_pkgs,
    install_requires=[
        "GitPython", # 'git://github.com/gitpython-developers/GitPython'
        ],
    entry_points={
        'console_scripts' : ['datalad=datalad.cmdline.main:main'],
    }
)

