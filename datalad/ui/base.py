# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes for UI

"""

__docformat__ = 'restructuredtext'

from abc import (
    ABCMeta,
    abstractmethod,
)

from ..utils import auto_repr


@auto_repr
class InteractiveUI(object, metaclass=ABCMeta):
    """Semi-abstract class for interfaces to implement interactive UI"""

    @abstractmethod
    def question(self, text,
                 title=None, choices=None,
                 default=None,
                 hidden=False,
                 repeat=None):
        pass

    def yesno(self, *args, **kwargs):
        # Provide some default sugaring
        default = kwargs.pop('default', None)
        if default is not None:
            if default in {True}:
                default = 'yes'
            elif default in {False}:
                default = 'no'
            kwargs['default'] = default
        response = self.question(*args, choices=['yes', 'no'], **kwargs).rstrip('\n')
        assert response in {'yes', 'no'}, "shouldn't happen; question() failed"
        return response == 'yes'
