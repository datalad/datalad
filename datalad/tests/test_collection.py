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
from nose.tools import assert_raises, assert_equal, assert_false, assert_in, eq_, assert_is_instance
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
    # assert_equal(len(list(collection.store.contexts())), 0)
    assert_is_instance(collection.meta, Graph)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), collection.meta)
    assert_in((DLNS.this, RDFS.label, Literal(name)), collection.meta)
    assert_equal(len(list(collection.store.contexts())), 1)
    eq_(collection.meta.identifier, Literal(name))
    eq_(collection.name, name)
    eq_(collection.url, None)
    eq_("<Collection name=%s (%s), handles=%s>" %
        (name, type(collection), []), collection.__repr__())
    assert_equal(set(iterkeys(collection)), set([]))


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
    # assert_equal(len(list(collection.store.contexts())), 1)
    # collection.update_graph_store()
    assert_equal(len(list(collection.store.contexts())), 2)

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
#     assert_equal(collection.name, repo.name)
#     assert_equal(collection.meta.identifier, Literal(repo.name))
#     assert_equal(set(iterkeys(collection)), {"handle1"})
#     assert_equal(len(list(collection.store.contexts())), 2)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), collection.meta)
#     assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
#               collection["handle1"].meta)
#
#     copy_collection = Collection(collection)
#     assert_equal(copy_collection.name, collection.name)
#     assert_equal(copy_collection.meta.identifier, Literal(repo.name))
#     assert_equal(set(iterkeys(copy_collection)), {"handle1"})
#     assert_equal(len(list(copy_collection.store.contexts())), 2)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), copy_collection.meta)
#     assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
#               copy_collection["handle1"].meta)
#
#     empty_collection = Collection(name="empty")
#     assert_equal(empty_collection.name, "empty")
#     assert_equal(empty_collection.meta.identifier, Literal("empty"))
#     assert_equal(set(iterkeys(empty_collection)), set([]))
#     assert_equal(len(list(empty_collection.store.contexts())), 1)
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), empty_collection.meta)
#     # test _reload() separately?


# @with_tempfile
# def test_Collection_setitem(path):
#     collection = Collection(name="new_collection")
#     handle1 = HandleRepoBackend(HandleRepo(path, name="handle1"))
#
#     collection["handle1"] = handle1
#     assert_equal(set(iterkeys(collection)), {"handle1"})
#     assert_equal(collection["handle1"], handle1)
#     assert_equal(len(collection.meta), 2)



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
#     assert_equal(set(iterkeys(collection)), set([]))
#     assert_equal(len(list(collection.meta.objects(subject=DLNS.this,
#                                                   predicate=DCTERMS.hasPart))),
#                  0)
#
#     # TODO: pop doesn't call __delitem__. So we need to override this one, too.
#     # collection.pop("handle1")


@with_tempfile
def test_Collection_commit(path):
    raise SkipTest

# testing MetaCollection:


@with_tempfile
@with_tempfile
@with_tempfile
def test_MetaCollection_constructor(path1, path2, path3):

    # setup two collections:
    repo1 = CollectionRepo(path1)
    repo2 = CollectionRepo(path2)
    handle = HandleRepo(path3)
    repo1.add_handle(handle, "somehandle")

    clt1 = CollectionRepoBackend(repo1)
    clt2 = CollectionRepoBackend(repo2)

    # MetaCollection from list; items are either Collections
    # or CollectionBackends:
    m_clt = MetaCollection([CollectionRepoBackend(repo1),
                            CollectionRepoBackend(repo2)])

    assert_equal(set(iterkeys(m_clt)), {repo1.name, repo2.name})
    # Meta collection asks the metas of the collections
    # TODO: may be make it even more lazy? ;)
    assert_equal(len(list(m_clt.store.contexts())), 2)
    assert_equal(clt1.meta, m_clt[repo1.name].meta)
    assert_equal(clt2.meta, m_clt[repo2.name].meta)
    # we are lazy in adding handle meta, so only 2 for collections
    assert_equal(len(list(m_clt.store.contexts())), 2)
    # Neither of below actions cause any effect on MetaCollection
    # TODO: figure out what we need to TODO about that
    #   _ = handle.meta
    #   clt1.update_graph_store()
    # assert_equal(len(list(m_clt.store.contexts())), 3)
    [assert_in(g.identifier, [Literal(repo1.name), Literal(repo2.name),
                              Literal("somehandle")])
     for g in m_clt.store.contexts()]

    # put something else in that list:
    with swallow_logs():
        assert_raises(TypeError, MetaCollection, [clt1, "invalid"])

    # copy constructor:
    m_clt_2 = MetaCollection(m_clt)
    assert_equal(set(iterkeys(m_clt_2)), {repo1.name, repo2.name})
    assert_equal(m_clt[repo1.name].meta, m_clt_2[repo1.name].meta)
    assert_equal(m_clt[repo2.name].meta, m_clt_2[repo2.name].meta)
    assert_equal(len(list(m_clt_2.store.contexts())), 2)
    [assert_in(g.identifier, [Literal(repo1.name), Literal(repo2.name),
                              Literal("somehandle")])
     for g in m_clt_2.store.contexts()]

    # MetaCollection from dict:
    d = {repo1.name: clt1, repo2.name: clt2}
    m_clt_3 = MetaCollection(d)
    assert_equal(set(iterkeys(m_clt_3)), {repo1.name, repo2.name})
    assert_equal(m_clt[repo1.name].meta, m_clt_3[repo1.name].meta)
    assert_equal(m_clt[repo2.name].meta, m_clt_3[repo2.name].meta)
    assert_equal(len(list(m_clt_3.store.contexts())), 2)
    [assert_in(g.identifier, [Literal(repo1.name), Literal(repo2.name),
                              Literal("somehandle")])
     for g in m_clt_3.store.contexts()]

    # MetaCollection (empty):
    m_clt_4 = MetaCollection()
    assert_equal(set(iterkeys(m_clt_4)), set([]))
    assert_equal(len(list(m_clt_4.store.contexts())), 0)


@with_tempfile
@with_tempfile
def test_MetaCollection_setitem(path1, path2):
    cr = CollectionRepo(path1)
    hr = HandleRepo(path2)
    cr.add_handle(hr, "somehandle")
    clt = CollectionRepoBackend(cr)
    m_clt = MetaCollection()
    m_clt[clt.name] = clt

    assert_equal(set(iterkeys(m_clt)), {clt.name})
    assert_equal(m_clt[clt.name].meta, clt.meta)
    # hr is lazy now, so no meta in the m_clt.store
    assert_equal(len(list(m_clt.store.contexts())), 1)
    assert_equal(m_clt[clt.name].meta.identifier, Literal(clt.name))


@with_tempfile
@with_tempfile
def test_MetaCollection_delitem(path1, path2):
    cr = CollectionRepo(path1)
    hr = HandleRepo(path2)
    cr.add_handle(hr, "somehandle")
    clt = CollectionRepoBackend(cr)
    m_clt = MetaCollection()
    m_clt[clt.name] = clt

    del m_clt[clt.name]
    assert_equal(set(iterkeys(m_clt)), set([]))
    assert_equal(len(list(m_clt.store.contexts())), 0)
