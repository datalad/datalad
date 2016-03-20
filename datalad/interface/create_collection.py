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


from os import curdir
from os.path import join as opj, abspath, expandvars, expanduser
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone


class CreateCollection(Interface):
    """Create a new collection.

    Creates an empty collection repository and registers it with datalad.
    You can give it name to be used by datalad to address that collection.
    Otherwise the base directory's name of the repository is used.
    Either way, it's not possible to use the same name twice.

    Example:

        $ datalad create-collection /some/where/my_collection MyFirstCollection
    """
    _params_ = dict(
        path=Parameter(
            args=('path',),
            nargs='?',
            doc="path where to create the collection",
            constraints=EnsureStr()),
        name=Parameter(
            args=('name',),
            nargs='?',
            doc="name of the collection; if no name is given the name of the "
                "destination directory is used.",
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    def __call__(path=curdir, name=None):
        # TODO: Collection => graph => lazy
        """
        Returns
        -------
        Collection
        """

        from datalad.support.collectionrepo import CollectionRepo
        from datalad.support.collection_backends import CollectionRepoBackend
        from datalad.cmdline.helpers import get_datalad_master

        local_master = get_datalad_master()

        # create the collection:
        new_collection = CollectionRepo(abspath(expandvars(expanduser(path))),
                                        name=name, create=True)
        # TODO: Move the abspath conversion to a constraint!
        # Additionally (or instead?) check for validity: existing directory or
        # just non-existing.

        # register with local master:
        local_master.git_remote_add(new_collection.name, new_collection.path)
        local_master.git_fetch(new_collection.name)

        return CollectionRepoBackend(new_collection)
