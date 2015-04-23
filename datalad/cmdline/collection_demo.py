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

from ..support.collection import Collection, CollectionBrokenError
from ..support.handle import Handle


def get_local_collection():
    # May be this location my change.
    # So, we need a ~/.datalad or sth.

    return Collection(expanduser(opj('~', '.datalad', 'localcollection')))


def register_collection(url, name):
    # Is there a default name of a collection?
    # derived from url?

    # add as remote to the local one:
    local_collection = get_local_collection()
    local_collection.git_remote_add(name, url)


def install_collection(name, dst):
    # How to check whether it is installed already?
    # cloning the remote 'name' of local collection to dst.
    local_collection = get_local_collection()
    url = local_collection.git_get_remote_url(name)
    return Collection(dst, url, name=name)


def new_collection(path, name):
    # create a new collection
    clt = Collection(path, name=name)

    # if this is a new collection, we want to register it in the
    # local collection as a remote, do we?
    get_local_collection().git_remote_add(name, path)

    return clt


def install_handle(dest, col_name=None, handle_name=None, url=None):
    # (identified what way? => collectionName/handleName?, url?)
    # For now:
    #   1. specify col_name, handle_name, dest OR
    #   2. specify url, dest and optional handle_name
    #
    #   later on, there should be some default location
    #   in the collection, so dst eventually will become optional.

    local = get_local_collection()

    if col_name and handle_name and dest:
        # TODO: There has to be a better way than checkout:
        # may be via: local.git_get_remote_url(col_name)
        # Check GitPython!

        local.git_checkout('%s/master' % col_name)
        local._update_handle_data()
        for h_ in local.handles:
            if h_[0] == handle_name:
                url = h_[2].rstrip()
        local.git_checkout('master')
        local._update_handle_data()

    elif url and dest:
        pass

    else:
        raise ValueError(
            "Unexpected argument values:\ndest:\t%s\ncol_name:\t%s\n"
            "handle_name:\t%s\nurl:\t%s" % (dest, col_name, handle_name, url))

    handle = Handle(dest, url)
    get_local_collection().add_handle(handle, handle_name if handle_name
                                      else basename(handle.path))
