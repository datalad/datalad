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

from nose.tools import assert_raises, assert_equal, assert_false, assert_in
from rdflib import Graph, Literal
from rdflib.namespace import FOAF

from ..support.gitrepo import GitRepo
from ..support.handlerepo import HandleRepo
from ..support.collection import CollectionRepo, Collection
from ..tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    on_windows, ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, \
    with_tree, get_most_obscure_supported_name, ok_clean_git
from ..support.exceptions import CollectionBrokenError

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepo_constructor(clean_path, clean_path2, broken_path):
    # Just a brand new CollectionRepo:
    clt = CollectionRepo(clean_path)
    # ok_clean_git(clean_path, annex=False)
    # TODO: ok_clean_git doesn't work on empty repo, due to
    # repo.head.is_valid() returns False
    assert_equal(os.path.basename(os.path.normpath(clean_path)),
                 clt.name)

    clt2 = CollectionRepo(clean_path2, name='different')
    assert_equal('different', clt2.name)
    with open(opj(clean_path2, 'collection'), 'r') as f:
        assert_equal(f.readline(), "New collection: different")

    # Now, there's something in git, but it's not a collection:
    git = GitRepo(broken_path)
    filename = get_most_obscure_supported_name()
    with open(opj(broken_path, filename), 'w') as f:
        f.write("something")
    git.git_add(filename)
    git.git_commit("add a file")
    assert_raises(CollectionBrokenError, CollectionRepo, broken_path)

    # TODO: provide a minimal test collection, that contains something valid


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepo_get_handles(annex_path, handle_path,
                                handle_path2, clt_path):

    handle1 = HandleRepo(handle_path, annex_path)
    handle2 = HandleRepo(handle_path2, annex_path)
    col_repo = CollectionRepo(clt_path)
    col_repo.add_handle(handle1, "FirstHandle")
    col_repo.add_handle(handle2, "SecondHandle")
    collection = Collection(col_repo)

    # get a single handle instance:
    t_handle = col_repo.get_handle("SecondHandle")

    assert_equal(collection["SecondHandle"][0], t_handle.datalad_id())
    assert_equal(collection["SecondHandle"][1], t_handle.path)
    assert_equal(set(Graph().parse(data=collection["SecondHandle"][2])),
                 set(t_handle.get_metadata()))

    assert_equal(t_handle.path, handle_path2)
    assert_equal(t_handle.datalad_id(), handle2.datalad_id())
    assert_equal(set(t_handle.get_metadata()), set(handle2.get_metadata()))

    # now get a list:
    t_list = col_repo.get_handles()
    assert_equal(len(t_list), 2)
    assert handle1 == t_list[0] or handle1 == t_list[1]
    assert handle2 == t_list[0] or handle2 == t_list[1]


@with_tempfile
@with_tempfile
def test_CollectionRepo_metadata_cache(h_path, c_path):
    handle = HandleRepo(h_path)
    col_repo = CollectionRepo(c_path)
    col_repo.add_handle(handle, "MyHandle")
    col = Collection(col_repo)

    # initial metadata:
    meta_initial = handle.get_metadata()
    assert_equal(set(Graph().parse(data=col['MyHandle'][2])), set(meta_initial))

    # edit handle's metadata:
    meta_new = handle.get_metadata()
    list_ = list(meta_new.subject_objects(FOAF.name))
    assert_equal(len(list_), 1)
    s = list_[0][0]
    o = list_[0][1]
    tuple_ = (s, FOAF.name, Literal("New Name"))
    meta_new.remove((s, FOAF.name, o))
    meta_new.add(tuple_)
    handle.set_metadata(meta_new)
    assert_equal(set(handle.get_metadata()), set(meta_new))
    # without updating the cache, collection still has initial metadata:
    assert_equal(set(Graph().parse(data=col['MyHandle'][2])), set(meta_initial))
    # TODO: Update cache from HandleRepo! (not just from file of course!)
    # assert_equal(col["MyHandle"][2], "['Fresh Metadata.']", "collection:\n%s" % col)


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_CollectionRepo_add_handle(annex_path, clone_path, clt_path):

    handle = HandleRepo(clone_path, annex_path)
    clt = CollectionRepo(clt_path)
    clt.add_handle(handle, "first_handle")
    ok_clean_git(clt_path, annex=False)
    os.path.exists(opj(clt_path, "first_handle"))
    assert_in("first_handle", clt.get_indexed_files())
    with open(opj(clt_path, "first_handle"), 'r') as f:
        assert_equal(f.readline().rstrip(), "handle_id = %s" %
                                            handle.datalad_id())
        assert_equal(f.readline().rstrip(), "last_seen = %s" % handle.path)
        assert_equal(
            set(Graph().parse(data=''.join(f.readlines()).lstrip(
                "metadata = "))),
            set(handle.get_metadata()))
    col_dict = Collection(clt)
    assert_equal(col_dict["first_handle"][0], handle.datalad_id())
    assert_equal(col_dict["first_handle"][1], handle.path)
    assert_equal(set(Graph().parse(data=col_dict["first_handle"][2])),
                 set(handle.get_metadata()))


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_CollectionRepo_remove_handle(annex_path, handle_path, clt_path):

    handle = HandleRepo(handle_path, annex_path)
    collection = CollectionRepo(clt_path)
    collection.add_handle(handle, "MyHandle")
    collection.remove_handle("MyHandle")
    ok_clean_git(clt_path, annex=False)
    assert_false(os.path.exists(opj(clt_path, "MyHandle")))
    assert_equal(collection.get_handles_data(), dict())
    # reminder:
    # last statemant means: instance lost any knowledge of
    # handle's name, id, path, metadata


@with_tempfile
def test_Collection_constructor(path):

    col_repo = CollectionRepo(path)
    col = Collection(col_repo)
    assert_equal(col.keys(), [])

    col2 = Collection()
    assert_equal(col.keys(), [])

    col_dict = {'handle1': (1, '/some/where', 'some data'),
                'handle2': (2, 'prot://far/away', 'other data')}
    col2.update(col_dict)
    assert_equal(col2.keys(), ['handle1', 'handle2'])
    assert_equal(col2['handle1'], (1, '/some/where', 'some data'))
    assert_equal(col2['handle2'], (2, 'prot://far/away', 'other data'))

    col = Collection(col2)
    assert_equal(col.keys(), ['handle1', 'handle2'])
    assert_equal(col['handle1'], (1, '/some/where', 'some data'))
    assert_equal(col['handle2'], (2, 'prot://far/away', 'other data'))
    assert_equal(col, col2)

    assert_raises(TypeError, Collection, 1)


@with_tempfile
def test_Collection_commit(path):

    col_repo = CollectionRepo(path)
    col = Collection(col_repo)

    col.update({'handle1': (1, '/some/where', 'some data'),
                'handle2': (2, 'prot://far/away', 'other data')})
    col.commit(msg="Save test collection")
    assert_equal({'collection', 'handle1', 'handle2'},
                 set(col_repo.get_indexed_files()))

    col_repo2 = CollectionRepo(path)
    col2 = Collection(col_repo2)
    # TODO: data format is differing (see below)
    # Pay attention when rdf thing is implemented.
    assert_equal(col2['handle1'], ('1', '/some/where', 'some data'))
    assert_equal(col2['handle2'], ('2', 'prot://far/away', 'other data'))