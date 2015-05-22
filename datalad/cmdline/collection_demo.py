# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Collections - Proof of concept
"""
# ###########
# Test the handling of base classes before
# implementing it into the actual commands
# ############

from os.path import join as opj, expanduser, basename

from ..support.collectionrepo import Collection, CollectionRepo, \
    CollectionBrokenError
from ..support.handlerepo import HandleRepo


def get_local_collection():
    # May be this location my change.
    # So, we need a ~/.datalad or sth.
    repo = CollectionRepo(expanduser(opj('~', '.datalad', 'localcollection')))
    return Collection(repo, load_remotes=True), repo


def register_collection(url, name):
    # Is there a default name of a collection?
    # derived from url?

    # add as remote to the local one:
    local_col, local_col_repo = get_local_collection()
    local_col_repo.git_remote_add(name, url)
    local_col._load_remotes()
    # => TODO: add method to Collection. (And load single remotes)


def install_collection(name, dst):
    # How to check whether it is installed already?
    # cloning the remote 'name' of local collection to dst.
    local_col, local_col_repo = get_local_collection()
    url = local_col_repo.git_get_remote_url(name)
    installed_clone = CollectionRepo(dst, url, name=name)
    return Collection(installed_clone,
                      branch=installed_clone.git_get_active_branch()), \
           installed_clone


def new_collection(path, name):
    # create a new collection
    clt_repo = CollectionRepo(path, name=name)

    # if this is a new collection, we want to register it in the
    # local collection as a remote, do we?
    loc_col, loc_col_repo = get_local_collection()
    loc_col_repo.git_remote_add(name, path)

    return Collection(clt_repo, branch=clt_repo.git_get_active_branch())


def install_handle(dest, col_name=None, handle_name=None, url=None):
    # (identified what way? => collectionName/handleName?, url?)
    # For now:
    #   1. specify col_name, handle_name, dest OR
    #   2. specify url, dest and optional handle_name
    #
    #   later on, there should be some default location
    #   in the collection, so dst eventually will become optional.

    loc_col, loc_col_repo = get_local_collection()

    if col_name and handle_name and dest:
        url = loc_col.remote_collections[col_name]['HEAD'][handle_name][1]

    elif url and dest:
        pass

    else:
        raise ValueError(
            "Unexpected argument values:\ndest:\t%s\ncol_name:\t%s\n"
            "handle_name:\t%s\nurl:\t%s" % (dest, col_name, handle_name, url))

    handle = HandleRepo(dest, url)
    loc_col_repo.add_handle(handle, handle_name
                            if handle_name else basename(handle.path))


def publish(src, target):
        # Q: Is this even a class method or just a datalad command?

        # TODO: lintian check for all handles and may be the collection itself,

        # TODO: Figure out uploading procedure
        #   => target should be some Uploader-Interface and (may be) an url, ...

        # especially cross-platform checks
        # first (try to) upload handles
        # check all is fine
        # update location for uploaded handles
        # upload collection itself
        pass