# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for installing a handler
"""

__docformat__ = 'restructuredtext'


from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr


class Install(Interface):
    """Install a handle from a given URL to a given directory

    Examples:

    $ datalad install http://psydata.ovgu.de/forrest_gump/.git /foo/bar
    """

    _params_ = dict(
        source=Parameter(
            doc="url to git repository",
            constraints=EnsureStr(),  # XXX should be EnsureURL
            metavar='url'),
        destination=Parameter(
            doc="path where to store the retrieved dataset",
            constraints=EnsureStr(),
            metavar='dir'),
        direct=Parameter(
            doc="Flag whether to force git-annex to use direct mode",
            action="store_true"))

    def __call__(source, destination, direct=False):
        import os
        from datalad.api import Handle

        path = os.path.expandvars(os.path.expanduser(destination))
        return Handle, (path, source), dict(direct=direct)
