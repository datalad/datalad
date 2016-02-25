# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of classes RuntimeCollection and MetaCollection
"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_false, assert_in, eq_, assert_is_instance, assert_is
from rdflib import Graph, Literal, URIRef, RDFS
from six import iterkeys

from ..support.handlerepo import HandleRepo
from datalad.support.handle_backends import HandleRepoBackend, RuntimeHandle
from ..support.handle import Handle
from ..support.collectionrepo import CollectionRepo
from datalad.support.exceptions import ReadOnlyBackendError
from datalad.support.collection_backends import CollectionRepoBackend, RuntimeCollection
from ..support.collection import Collection, MetaCollection, DLNS, RDF, DCTERMS
from ..tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    on_windows, ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, \
    with_tree, get_most_obscure_supported_name, ok_clean_git, ok_
from ..support.exceptions import CollectionBrokenError
from ..utils import get_local_file_url


# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


def test_RuntimeCollection_constructor():

    name = "MyCollection"
    collection = RuntimeCollection(name)

    assert_is_instance(collection, Collection)
    # TODO: if laziness works:
    # eq_(len(list(collection.store.contexts())), 0)
    assert_is_instance(collection.meta, Graph)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), collection.meta)
    assert_in((DLNS.this, RDFS.label, Literal(name)), collection.meta)
    eq_(len(list(collection.store.contexts())), 1)
    eq_(collection.meta.identifier, Literal(name))
    eq_(collection.name, name)
    eq_(collection.url, None)
    eq_("<Collection name=%s (%s), handles=%s>" %
        (name, type(collection), []), collection.__repr__())
    eq_(set(iterkeys(collection)), set([]))


@with_testrepos('.*handle.*', flavors=['local'])
def test_RuntimeCollection_modify(path):

    col_name = "MyCollection"
    collection = RuntimeCollection(col_name)

    # Add a RuntimeHandle:
    hdl_name = "MyHandle"
    handle1 = RuntimeHandle(hdl_name)
    # Currently a RuntimeHandle has URI DLNS.this and therefore can't be added
    # to a collection (it's not a valid identifier in this context). Since it
    # also has no URL, an URI can't be derived.
    with assert_raises(ValueError) as cm:
        collection[hdl_name] = handle1
    eq_("Handle '%s' has neither a valid URI (%s) nor an URL." % (hdl_name,
                                                                  DLNS.this),
        str(cm.exception))

    # Add an existing handle:
    handle2 = HandleRepoBackend(HandleRepo(path, create=False))
    collection.register_handle(handle2)

    eq_(set(iterkeys(collection)), {handle2.name})
    assert_in((DLNS.this, DCTERMS.hasPart, URIRef(get_local_file_url(path))),
              collection.meta)

    # TODO: if laziness works:
    # eq_(len(list(collection.store.contexts())), 1)
    # collection.update_graph_store()
    eq_(len(list(collection.store.contexts())), 2)

    with assert_raises(ReadOnlyBackendError) as cm:
        collection.commit()
    eq_("Can't commit RuntimeHandle.", str(cm.exception))

# TODO: more on setitem, delitem, commit, commit_metadata, update_graph_store, ...






# @with_tempfile
# @with_tempfile
# def test_Collection_constructor(path, h_path):
#     repo = CollectionRepo(path)
#     handle = HandleRepo(h_path)
#     repo.add_handle(handle, "handle1")
#
#     collection = Collection(CollectionRepoBackend(repo))
#     eq_(collection.name, repo.name)
#     eq_(collection.meta.identifier, Literal(repo.name))
#     eq_(set(iterkeys(collection)), {"handle1"})
#     eq_(len(list(collection.store.contexts())), 2)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), collection.meta)
#     assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
#               collection["handle1"].meta)
#
#     copy_collection = Collection(collection)
#     eq_(copy_collection.name, collection.name)
#     eq_(copy_collection.meta.identifier, Literal(repo.name))
#     eq_(set(iterkeys(copy_collection)), {"handle1"})
#     eq_(len(list(copy_collection.store.contexts())), 2)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), copy_collection.meta)
#     assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
#               copy_collection["handle1"].meta)
#
#     empty_collection = Collection(name="empty")
#     eq_(empty_collection.name, "empty")
#     eq_(empty_collection.meta.identifier, Literal("empty"))
#     eq_(set(iterkeys(empty_collection)), set([]))
#     eq_(len(list(empty_collection.store.contexts())), 1)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), empty_collection.meta)
#     # test _reload() separately?


# @with_tempfile
# def test_Collection_setitem(path):
#     collection = Collection(name="new_collection")
#     handle1 = HandleRepoBackend(HandleRepo(path, name="handle1"))
#
#     collection["handle1"] = handle1
#     eq_(set(iterkeys(collection)), {"handle1"})
#     eq_(collection["handle1"], handle1)
#     eq_(len(collection.meta), 2)



    # TODO: Wrong! handle uri needs to be changed. Is still "this"!
    # Note: Actually that's not wrong, since we don't "import" the handles, but
    # set the entries manually. So, we need to adapt them manually, too.



    # assert_in((URIRef(get_local_file_url(path)), RDF.type, DLNS.Handle),
    #           collection["handle1"].meta)
    #




    #ok_(False, collection.meta.serialize(format="turtle"))

    #assert_in((DLNS.this, DCTERMS.hasPart, )

    #    collection.meta

#
# @with_tempfile
# def test_Collection_delitem(path):
#     collection = Collection(name="new_collection")
#     handle1 = HandleRepoBackend(HandleRepo(path, name="handle1"))
#     collection["handle1"] = handle1
#     del collection["handle1"]
#
#     eq_(set(iterkeys(collection)), set([]))
#     eq_(len(list(collection.meta.objects(subject=DLNS.this,
#                                                   predicate=DCTERMS.hasPart))),
#                  0)
#
#     # TODO: pop doesn't call __delitem__. So we need to override this one, too.
#     # collection.pop("handle1")


@with_tempfile
def test_Collection_commit(path):
    raise SkipTest

# testing MetaCollection:


@with_testrepos('collection', flavors=['local'])
@with_testrepos('.*basic.*collection.*', flavors=['local'])
def test_MetaCollection_constructor(path1, path2):

    # MetaCollection (empty):
    metacollection_empty = MetaCollection(name="metacollection_empty")
    eq_(set(iterkeys(metacollection_empty)), set([]))
    eq_(len(list(metacollection_empty.store.contexts())), 0)

    # setup two collections:
    repo1 = CollectionRepo(path1, create=False)
    repo2 = CollectionRepo(path2, create=False)

    clt1 = CollectionRepoBackend(repo1)
    clt2 = CollectionRepoBackend(repo2)

    # create the very same meta collection three different ways:
    # 1. MetaCollection from list of collections:
    metacollection = MetaCollection([clt1, clt2], name="metacollection")
    # put something invalid in that list:
    with swallow_logs():
        assert_raises(AttributeError, MetaCollection, [clt1, "invalid"])
    # 2. MetaCollection from dict:
    d = {repo1.name: clt1, repo2.name: clt2}
    metacollection_dict = MetaCollection(d, name="metacollection_dict")
    # 3. copy constructor:
    metacollection_copy = MetaCollection(metacollection, name="metacollection_copy")

    # test these three instances:
    for m_col in [metacollection, metacollection_copy, metacollection_dict]:
        eq_(set(iterkeys(m_col)), {repo1.name, repo2.name})
        # lazy loading of metadata, so the store should be empty at this point:
        eq_(len(list(m_col.store.contexts())), 0)

    # trigger update of a handle:
    clt1["BasicHandle"].update_metadata()
    # now all metacollections linked to that handle should be updated:
    for m_col in [metacollection, metacollection_copy, metacollection_dict]:
        eq_(len(list(m_col.store.contexts())), 1)
        assert_in(clt1["BasicHandle"].meta, m_col.store.contexts())

    # trigger update of a collection's graph:
    clt2.update_metadata()
    # now all metacollections linked to that collection should have that graph
    # in their stores, too:
    for m_col in [metacollection, metacollection_copy, metacollection_dict]:
        eq_(len(list(m_col.store.contexts())), 2)
        assert_in(clt2.meta, m_col.store.contexts())

    # full update:
    metacollection.update_graph_store()
    # recursively triggers all the updates, so that the other metacollections
    # are affected, too:
    for m_col in [metacollection, metacollection_copy, metacollection_dict]:
        eq_(len(list(m_col.store.contexts())), 4)
        assert_in(clt1["BasicHandle"].meta, m_col.store.contexts())
        assert_in(clt1["MetadataHandle"].meta, m_col.store.contexts())
        assert_in(clt1.meta, m_col.store.contexts())
        assert_in(clt2.meta, m_col.store.contexts())


@with_testrepos('.*collection.*', flavors=['local'])
def test_MetaCollection_setitem(path):
    cr = CollectionRepo(path, create=False)
    clt = CollectionRepoBackend(cr)
    m_clt = MetaCollection()

    # add a collection by assignment:
    m_clt[clt.name] = clt

    eq_(set(iterkeys(m_clt)), {clt.name})
    # graphs are lazy now, so no meta in the m_clt.store
    eq_(len(list(m_clt.store.contexts())), 0)
    # test actual assignment
    assert_is(m_clt[clt.name], clt)


@with_testrepos('collection', flavors=['local'])
def test_MetaCollection_delitem(path):
    cr = CollectionRepo(path, create=False)
    clt = CollectionRepoBackend(cr)
    m_clt = MetaCollection()
    m_clt[clt.name] = clt
    m_clt.update_graph_store()
    eq_(len(list(m_clt.store.contexts())), 3)

    del m_clt[clt.name]
    eq_(set(iterkeys(m_clt)), set([]))
    eq_(len(list(m_clt.store.contexts())), 0)


def test_MetaCollection_pop():
    raise SkipTest


def test_MetaCollection_query():
    raise SkipTest
