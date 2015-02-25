#!/usr/bin/env python
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# Minimalistic setup.py for now

from setuptools import setup

import datalad.version

setup(
    name="datalad",
    author="DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=datalad.version.__version__,
    description="git-annex based data distribution geared toward scientific datasets",
    py_modules=['datalad'],
    install_requires=[
        "GitPython", # 'git://github.com/gitpython-developers/GitPython'
        ],
    # TODO: proper setuptools way through entry points
    #entry_points="""
    #    [console_scripts]
    #"""
    scripts = ['bin/datalad'],
)

