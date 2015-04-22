# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of collections

"""

import os
from os.path import join as opj
import platform

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_false, assert_in

from ..support.gitrepo import GitRepo
from ..support.handle import Handle
from ..support.collection import Collection
from ..tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, with_tree,\
    get_most_obscure_supported_name, ok_clean_git
from ..support.exceptions import CollectionBrokenError

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']

# ###########
# Test the handling of base classes before
# implementing it into the actual commands
# ############

def get_local_collection():
    # May be this location my change.
    # So, we need a ~/.datalad or sth.

    return Collection(os.path.expanduser(
        os.path.join('~', 'datalad', 'localcollection')))


def register_collection(url, name):
    # Is there a default name of a collection?
    # derived from url?

    # add as remote to the local one:
    localCollection = get_local_collection()
    localCollection.git_remote_add(name, url)



def install_collection(name, dst):
    # cloning the remote 'name' of local collection to dst.
    localCollection = get_local_collection()
    url = localCollection.git_get_remote_url(name)
    return Collection(dst, url)



def install_handle(whatever):
    # TODO: get a handle
    # (identified what way? => collectionName/handleName?, url?)
    pass


def new_collection(handles):
    # create a new collection
    # if this is a new collection, we want to register it in the
    # local collection as a remote, do we?
    pass


# ##########
# Now the actual tests for collection class
# ##########

@with_tempfile
@with_tempfile
def test_Collection_constructor(clean_path, broken_path):
    # Just a brand new collection:
    clt = Collection(clean_path)
    # ok_clean_git(clean_path, annex=False)
    # TODO: ok_clean_git doesn't work on empty repo, due to
    # repo.head.is_valid() returns False

    # Now, there's something in git, but it's not a collection:
    git = GitRepo(broken_path)
    filename = get_most_obscure_supported_name()
    with open(opj(broken_path, filename), 'w') as f:
        f.write("something")
    git.git_add(filename)
    git.git_commit("add a file")
    assert_raises(CollectionBrokenError, Collection, broken_path)

    # TODO: provide a minimal test collection, that contains something valid

@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_Collection_add_handle(annex_path, clone_path, clt_path):

    handle = Handle(clone_path, annex_path)
    clt = Collection(clt_path)
    clt.add_handle(handle, "first handle")
    ok_clean_git(clt_path, annex=False)
    os.path.exists(opj(clt_path, "first handle"))
    assert_in("first handle", clt.get_indexed_files())
    with open(opj(clt_path, "first handle"), 'r') as f:
        assert_equal(f.readline().rstrip(), "handle_id = %s" % handle.get_datalad_id())
        assert_equal(f.readline().rstrip(), "last_seen = %s" % handle.path)
        assert_equal(f.readline().rstrip(), "metadata = %s" % handle.get_metadata())
        assert_equal(f.readline(), "")
    assert_equal(clt.handles, [("first handle", handle.get_datalad_id(),
                                handle.path, handle.get_metadata())])


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_Collection_remove_handle(annex_path, handle_path, clt_path):

    handle = Handle(handle_path, annex_path)
    collection = Collection(clt_path)
    collection.add_handle(handle, "MyHandle")
    collection.remove_handle("MyHandle")
    ok_clean_git(clt_path, annex=False)
    assert_false(os.path.exists(opj(clt_path, "MyHandle")))
    assert_equal(collection.handles, [])
    # reminder:
    # last statemant means: instance lost any knowledge of
    # handle's name, id, path, metadata


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
@with_tempfile
def test_Collection_get_handles(annex_path, handle_path,
                                handle_path2, clt_path):

    handle1 = Handle(handle_path, annex_path)
    handle2 = Handle(handle_path2, annex_path)
    collection = Collection(clt_path)
    collection.add_handle(handle1, "First Handle")
    collection.add_handle(handle2, "Second Handle")

    # get a single handle instance:
    t_handle = collection.get_handle("Second Handle")
    assert_in(("Second Handle", t_handle.get_datalad_id(),
               t_handle.path, t_handle.get_metadata()),
              collection.handles)
    assert_equal(t_handle.path, handle_path2)
    assert_equal(t_handle.get_datalad_id(), handle2.get_datalad_id())
    assert_equal(t_handle.get_metadata(), handle2.get_metadata())

    # now get a list:
    t_list = collection.get_handles()
    assert_equal(len(t_list), 2)
    assert_equal(t_list[0], handle1)
    assert_equal(t_list[1], handle2)



