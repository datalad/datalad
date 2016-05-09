# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Defines version to be imported in the module and obtained from setup.py
"""

from os.path import lexists, dirname, join as opj

# Hard coded version, to be done by release process
__version__ = '0.1.dev0'

# NOTE: might cause problems with "python setup.py develop" deployments
#  so I have even changed buildbot to use  pip install -e .
if lexists(opj(dirname(dirname(__file__)), '.git')):
    # If under git -- attempt to deduce a better "dynamic" version following git
    try:
        import sys
        from subprocess import Popen, PIPE
        from os.path import dirname
        git = Popen(['git', 'describe', '--abbrev=4', '--dirty', '--match', '[0-9]*\.*'],
                    stdout=PIPE, stderr=PIPE,
                    cwd=dirname(dirname(__file__)))
        if git.wait() != 0:
            raise OSError
        line = git.stdout.readlines()[0]
        _ = git.stderr.readlines()
        # Just take describe and replace initial '-' with .dev to be more "pythonish"
        __version__ = line.strip().decode('ascii').replace('-', '.dev', 1)
    except:
        __version__ += ".giterror"

