# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for handle creation

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expandvars, expanduser
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handlerepo import HandleRepo
from datalad.support.handle_backends import HandleRepoBackend
from datalad.support.handle import Handle
from datalad.cmdline.helpers import get_datalad_master


class CreateHandle(Interface):
    """Create a new handle.

    Creates an empty handle repository and registers it with datalad.
    You can give it a name to be used by datalad to address that handle.
    Otherwise the base directory's name of the repository is used.
    Either way, it's not possible to use the same name twice.

    Example:

        $ datalad create-handle /some/where/first_handle MyFirstHandle
    """
    _params_ = dict(
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="path where to create the handle",
            constraints=EnsureStr()),
        name=Parameter(
            args=('name',),
            nargs='?',
            doc="name of the handle; if no name is given the name of the "
                "destination directory is used.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, path=curdir, name=None):
        """
        Returns
        -------
        Handle
        """

        local_master = get_datalad_master()

        new_handle = HandleRepo(abspath(expandvars(expanduser(path))),
                                name=name, create=True)
        local_master.add_handle(new_handle, name=name)
        # TODO: get metadata, in case there is some already.
        # This implicates the option to use create-handle on an existing annex.

        if not self.cmdline:
            return HandleRepoBackend(new_handle)
