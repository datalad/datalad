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

import sys
from os.path import lexists, dirname, join as opj, curdir

# Hard coded version, to be done by release process,
# it is also "parsed" (not imported) by setup.py, that is why assigned as
# __hardcoded_version__ later and not vise versa
__version__ = '0.12.0rc4'
__hardcoded_version__ = __version__
__full_version__ = __version__

# NOTE: might cause problems with "python setup.py develop" deployments
#  so I have even changed buildbot to use  pip install -e .
moddir = dirname(__file__)
projdir = curdir if moddir == 'datalad' else dirname(moddir)
if lexists(opj(projdir, '.git')):
    # If under git -- attempt to deduce a better "dynamic" version following git
    try:
        from subprocess import Popen, PIPE
        # Note: Popen does not support `with` way correctly in 2.7
        #
        git = Popen(
            ['git', 'describe', '--abbrev=4', '--dirty', '--match', '[0-9]*\.*'],
            stdout=PIPE, stderr=PIPE,
            cwd=projdir
        )
        if git.wait() != 0:
            raise OSError("Could not run git describe")
        line = git.stdout.readlines()[0]
        _ = git.stderr.readlines()
        # Just take describe and replace initial '-' with .dev to be more "pythonish"
        # Encoding simply because distutils' LooseVersion compares only StringType
        # and thus misses in __cmp__ necessary wrapping for unicode strings
        __full_version__ = line.strip().decode('ascii').replace('-', '.dev', 1).encode()
        # To follow PEP440 we can't have all the git fanciness
        __version__ = __full_version__.split(b'-')[0]
        # awkward version specific handling :-/
        if sys.version_info[0] >= 3:
            __version__ = __version__.decode()
    except (SyntaxError, AttributeError, IndexError):
        raise
    except:
        # just stick to the hard-coded
        pass
