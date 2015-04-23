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

from os.path import join as opj, expanduser

from ..support.collection import Collection, CollectionBrokenError
from ..support.handle import Handle


def get_local_collection():
    # May be this location my change.
    # So, we need a ~/.datalad or sth.

    return Collection(expanduser(opj('~', 'datalad', 'localcollection')))


def register_collection(url, name):
    # Is there a default name of a collection?
    # derived from url?

    # add as remote to the local one:
    local_collection = get_local_collection()
    local_collection.git_remote_add(name, url)


def install_collection(name, dst):
    # cloning the remote 'name' of local collection to dst.
    local_collection = get_local_collection()
    url = local_collection.git_get_remote_url(name)
    return Collection(dst, url, name=name)


def new_collection(path, name=None):
    # create a new collection
    # if this is a new collection, we want to register it in the
    # local collection as a remote, do we?
    pass


def install_handle(whatever):
    # TODO: get a handle
    # (identified what way? => collectionName/handleName?, url?)

    pass

