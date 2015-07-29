# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the testkraut package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'

__version__ = "0.0.1+dev"

import os
from .config import ConfigManager

class _SingletonType(type):
    """Simple singleton implementation adjusted from
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/412551
    """
    def __init__(mcs, *args):
        type.__init__(mcs, *args)
        mcs._instances = {}

    def __call__(mcs, sid, instance, *args):
        if not sid in mcs._instances:
            mcs._instances[sid] = instance
        return mcs._instances[sid]

# Awkward way to define Python2 and Python3 compatible use of metaclasses
# Ref: https://wiki.python.org/moin/PortingToPy3k/BilingualQuickRef#metaclasses
__Singleton = _SingletonType(str('__Singleton'), (), {
        '__doc__': "To ensure single instance of a class instantiation (object)"
    })

#
# As the very first step: Setup configuration registry instance and
# read all configuration settings from files and env variables
#
_cfgfile = os.environ.get('TESTKRAUTCONFIG', None)
if _cfgfile:
    # We have to provide a list
    _cfgfile = [_cfgfile]
cfg = __Singleton('cfg', ConfigManager(_cfgfile))


