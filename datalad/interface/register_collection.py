# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for collection registration

"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, isdir
from .base import Interface
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.collectionrepo import CollectionRepo, \
    CollectionRepoBackend
from datalad.support.collection import Collection
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class RegisterCollection(Interface):
    """Registers a collection with datalad.

    Registering a remote collection with datalad allows for including their
    metadata in searches, installing handles they contain and so on.
    Once registered you can keep track of the current state of the remote
    collection.

    Example:
        $ datalad register-collection \
        http://collections.datalad.org/demo/DATALAD_COL_demo_collection
    """
    _params_ = dict(
        url=Parameter(
            doc="url of the collection",
            constraints=EnsureStr()),
        name=Parameter(
            args=('name',),
            nargs='?',
            doc="name, the collection is registered with; if no name is given "
                "the name is derived from the url.",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, url, name=None):
        """
        Returns
        -------
        Collection
        """

        # check whether url is a local path:
        if isdir(abspath(expandvars(expanduser(url)))):
            url = abspath(expandvars(expanduser(url)))
            # raise exception, if it's not a valid collection:
            repo = CollectionRepo(url, create=False)
            if name is None:
                name = repo.name

        else:
            # assume it's a git url:
            if name is None:
                # derive name from url:
                parts = url.split('/')
                parts.reverse()
                catch_next = False
                for part in parts:
                    if catch_next:
                        name = part
                        break
                    elif part == '.git':
                        catch_next = True
                    elif part.endswith('.git'):
                        name = part[0:-4]
                        break
                    else:
                        pass

        if name is None:  # still no name?
            raise RuntimeError("Couldn't derive a name from %s" % url)

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))
        local_master.git_remote_add(name, url)
        local_master.git_fetch(name)

        return Collection(CollectionRepoBackend(local_master,
                                                name + "/master"))