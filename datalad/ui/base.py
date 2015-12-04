# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes for UI

"""

__docformat__ = 'restructuredtext'

from abc import ABCMeta, abstractmethod

from ..utils import auto_repr

@auto_repr
class InteractiveUI(object):
    """Semi-abstract class for interfaces to implement interactive UI"""

    __metaclass__ = ABCMeta

    @abstractmethod
    def question(self, text,
                 title=None, choices=None,
                 default=None,
                 hidden=False):
        pass

    def yesno(self, *args, **kwargs):
        response = self.question(*args, choices=['yes', 'no'], **kwargs).rstrip('\n')
        if response == 'yes':
            return True
        elif response == 'no':
            return False
        else:
            raise RuntimeError("must not happen but did")
