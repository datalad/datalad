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

from os.path import lexists, dirname, join as opj, curdir

# Hard coded version, to be done by release process
__version__ = '0.2'

# NOTE: might cause problems with "python setup.py develop" deployments
#  so I have even changed buildbot to use  pip install -e .
moddir = dirname(__file__)
projdir = curdir if moddir == 'datalad' else dirname(moddir)
if lexists(opj(projdir, '.git')):
    # If under git -- attempt to deduce a better "dynamic" version following git
    try:
        import sys
        from subprocess import Popen, PIPE
        from os.path import dirname
        git = Popen(['git', 'describe', '--abbrev=4', '--dirty', '--match', '[0-9]*\.*'],
                    stdout=PIPE, stderr=PIPE,
                    cwd=projdir)
        if git.wait() != 0:
            raise OSError("Could not run git describe")
        line = git.stdout.readlines()[0]
        _ = git.stderr.readlines()
        # Just take describe and replace initial '-' with .dev to be more "pythonish"
        __full_version__ = line.strip().decode('ascii').replace('-', '.dev', 1)
        # To follow PEP440 we can't have all the git fanciness
        __version__ = __full_version__.split('-')[0]
    except:
        # just stick to the hard-coded
        __full_version__ = __version__
