# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for updating knowledge about remote repositories
"""

__docformat__ = 'restructuredtext'


from os import curdir
from os.path import exists, join as opj
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureBool, EnsureNone
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.handlerepo import HandleRepo
from ..cmdline.helpers import get_repo_instance
from ..log import lgr
from appdirs import AppDirs

dirs = AppDirs("datalad", "datalad.org")


class Update(Interface):
    """Update information from a remote repository.

    Examples:

    Updating registered collections:
    $ datalad update

    Updating a local handle:
    ~/MyHandle/$ datalad update
    or
    $ datalad update MyHandle

    Updating a local collection:
    ~/MyCollection/$ datalad update
    or
    $ datalad update MyCollection
    """
    _params_ = dict(
        key=Parameter(
            args=('key',),
            nargs='?',
            doc="name of or path to the repository to be updated",
            constraints=EnsureStr() | EnsureNone()))

    def __call__(self, key=curdir):

        local_master = CollectionRepo(opj(dirs.user_data_dir,
                                      'localcollection'))

        if key == curdir:
            try:
                repo = get_repo_instance()
            except RuntimeError as e:
                # Not inside repo => update master
                repo = local_master
        elif exists(key):
            try:
                repo = get_repo_instance(path=key)
            except RuntimeError as e:
                # No valid repository at given path
                lgr.error(str(e))
                return -1
        else:
            # if it's not an existing path, try treating it as a name:

            if key in local_master.git_get_remotes():
                # it's a registered collection's name:
                path = CollectionRepoBackend(local_master, key).url
                if exists(path):
                    try:
                        repo = CollectionRepo(path)
                    except RuntimeError as e:
                        # Collection found by it's name, but invalid repository
                        lgr.error("Collection '%s': %s" % (key, str(e)))
                        return -1
                else:
                    lgr.error("Collection '%s': path %s doesn't exist." %
                              (key, path))
                    return -1
            elif key in local_master.get_handle_list():
                # it's a handle's name:
                path = CollectionRepoHandleBackend(local_master, key).url
                if exists(path):
                    try:
                        repo = HandleRepo(path)
                    except RuntimeError as e:
                        # Collection found by it's name, but invalid repository
                        lgr.error("Handle '%s': %s" % (key, str(e)))
                        return -1
                else:
                    lgr.error("Handle '%s': path %s doesn't exist." %
                              (key, path))
                    return -1

            else:
                lgr.error("'%s' is neither a known collection nor a known "
                          "handle." % key)
                return -1

        # We have a repo instance from above: update!
        for remote in repo.git_get_remotes():
            repo.git_fetch(remote)