# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for collection creation

"""

__docformat__ = 'restructuredtext'

from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr


class CreateCollection(Interface):
    """I am a demo"""
    _params_ = dict(
        path=Parameter(
            doc="path where to create the collection",
            constraints=EnsureStr()))

    def __call__(self, path="here"):
        print 'creating a collection at %s' % path

    def setup_parser(self, parser):
        # XXX make this unnecessary with a smart default implementation
        # in the base class
        parser.add_argument(
            "path", help="path for repo")


