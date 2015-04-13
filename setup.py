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

setup(
    name="datalad",
    author="DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=datalad.version.__version__,
    description="git-annex based data distribution geared toward scientific datasets",
    py_modules=['datalad'],
    packages=find_packages('.', include=['datalad*']),
    install_requires=[
        "GitPython", # 'git://github.com/gitpython-developers/GitPython'
        ],
    entry_points={
        'console_scripts' : [
            'datalad=datalad.cmdline.main:main',
            'git-annex-remote-dl+archive=datalad.customremotes.archive:main'],
    }
)

