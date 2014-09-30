#!/usr/bin/env python

# Minimalistic setup.py for now

from setuptools import setup

import datalad.version

setup(
    name="datalad",
    author="Yaroslav Halchenko",
    author_email="debian@onerussian.com",
    version=datalad.version.__version__,
    description="get data from the web under control of git and git-annex",
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

