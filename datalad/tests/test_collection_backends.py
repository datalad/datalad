# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class CollectionRepoBackend.
"""

from unittest import SkipTest
from nose.tools import eq_, assert_in, ok_, assert_is_instance, assert_raises, assert_is
from rdflib import URIRef, RDF, Literal
from rdflib.namespace import DCTERMS
from six import iterkeys

from datalad.support.collection_backends import CollectionRepoBackend
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.collection import Collection
from datalad.support.handlerepo import HandleRepo
from datalad.support.metadatahandler import DLNS, Graph
from datalad.tests.utils import with_tempfile, with_testrepos
from datalad.utils import get_local_file_url


@with_testrepos('collection', flavors=['local'])
@with_tempfile
def test_CollectionRepoBackend_constructor(path1, path2):

    # set up collection repo:
    remote_repo = CollectionRepo(path1, create=False)
    repo = CollectionRepo(path2, create=True)
    # create a second branch:
    repo.git_checkout("another-branch", options="-b")
    # add a remote collection:
    repo.git_remote_add("remoterepo", path1)
    repo.git_fetch("remoterepo")

    # constructor from existing CollectionRepo instance:
    collection = CollectionRepoBackend(repo)

    assert_is_instance(collection, Collection)
    eq_(set(iterkeys(collection)), set([]))
    eq_(collection.branch, "another-branch")
    eq_(collection.repo, repo)
    eq_(collection.is_read_only, False)
    eq_(collection.remote, None)
    eq_(collection.name, repo.name)
    eq_(collection.url, get_local_file_url(repo.path))

    collection = CollectionRepoBackend(repo, "master")

    assert_is_instance(collection, Collection)
    eq_(set(iterkeys(collection)), set([]))
    eq_(collection.branch, "master")
    eq_(collection.repo, repo)
    eq_(collection.is_read_only, False)
    eq_(collection.remote, None)
    # TODO: repo probably returns name from active branch instead!
    #eq_(collection.name, repo.name)
    eq_(collection.url, get_local_file_url(repo.path))


    collection = CollectionRepoBackend(repo, "remoterepo/master")

    assert_is_instance(collection, Collection)
    eq_(set(iterkeys(collection)), {'BasicHandle', 'MetadataHandle'})
    eq_(collection.branch, "remoterepo/master")
    eq_(collection.repo, repo)
    eq_(collection.is_read_only, True)
    eq_(collection.remote, "remoterepo")
    # TODO: repo probably returns name from active branch instead!
    #eq_(collection.name, remote_repo.name)
    eq_(collection.url, repo.git_get_remote_url("remoterepo"))

    # constructor from path to collection repo:
    collection = CollectionRepoBackend(path2)

    assert_is_instance(collection, Collection)
    eq_(set(iterkeys(collection)), set([]))
    eq_(collection.branch, "another-branch")
    eq_(collection.repo, repo)
    eq_(collection.is_read_only, False)
    eq_(collection.remote, None)
    eq_(collection.name, repo.name)
    eq_(collection.url, get_local_file_url(path2))

    # test readonly properties:
    with assert_raises(AttributeError) as cm:
        collection.name = "new name"

    with assert_raises(AttributeError) as cm:
        collection.branch = "new branch"

    with assert_raises(AttributeError) as cm:
        collection.remote = "new remote"

    with assert_raises(AttributeError) as cm:
        collection.url = "http://example.org"


# TODO: test reload()!

@with_testrepos('.*collection.*', flavors=['clone'])
@with_tempfile
def test_CollectionRepoBackend_meta(url, path):
    raise SkipTest


def test_CollectionRepoBackend_commit():
    raise SkipTest


@with_testrepos('.*collection.*', flavors=['local'])
def test_CollectionRepoBackend_handle_update_listener(path):

    repo = CollectionRepo(path, create=False)

    # skip testrepos with no handles:
    # Note: Can't be done with raise SkipTest, since then the following
    # collections will be ignored, too.
    if not repo.get_handle_list():
        return

    collection = CollectionRepoBackend(repo)
    # empty store at the beginning:
    ok_(not set(collection.store.contexts()))

    # now trigger update on a handle within the collection:
    collection[repo.get_handle_list()[0]].update_metadata()
    eq_(len(list(collection.store.contexts())), 1)
    eq_(repo.get_handle_list()[0],
        str(list(collection.store.contexts())[0].identifier))
    assert_in(collection[repo.get_handle_list()[0]].meta,
              collection.store.contexts())


@with_testrepos('.*collection.*', flavors=['local'])
def test_CollectionRepoBackend_update_signal(path):

    class TestListener:

        def __init__(self):
            self.received = list()

        def listener_callable(self, collection, graph):
            assert_is_instance(collection, CollectionRepoBackend)
            assert_is_instance(graph, Graph)
            self.received.append(graph)

        def reset(self):
            self.received = list()

    listener = TestListener()
    repo = CollectionRepo(path, create=False)
    collection = CollectionRepoBackend(repo)
    collection.register_update_listener(listener.listener_callable)

    # Due to collection's laziness, the first access to 'meta' should
    # trigger an update:
    g = collection.meta
    eq_(len(listener.received), 1)
    assert_in(collection.meta, listener.received)
    listener.reset()

    # explicit update of collection level metadata:
    collection.update_metadata()
    eq_(len(listener.received), 1)
    assert_in(collection.meta, listener.received)
    listener.reset()

    # modifying the collection level metadata directly:
    collection.meta = {'some_subgraph': Graph()}
    eq_(len(listener.received), 1)
    assert_in(collection.meta, listener.received)
    listener.reset()

    # explicit update of the graph store:
    collection.update_graph_store()
    eq_(len(listener.received), len(collection) + 1)
    assert_in(collection.meta, listener.received)
    for handle in collection:
        assert_in(collection[handle].meta, listener.received)
    listener.reset()

    # update a handle, that is contained in the collection;
    # skip testrepos with no handles:
    if len(repo.get_handle_list()) > 0:
        collection[repo.get_handle_list()[0]].update_metadata()
        eq_(len(listener.received), 1)
        assert_in(collection[repo.get_handle_list()[0]].meta, listener.received)
        listener.reset()

    # remove the listener:
    collection.remove_update_listener(listener.listener_callable)
    eq_(collection._update_listeners, [])
    collection.update_graph_store()
    eq_(len(listener.received), 0)

# @with_tempfile
# @with_tempfile
# @with_tempfile
# def test_CollectionRepoBackend_get_handles(clt_path, h1_path, h2_path):
#
#     clt = CollectionRepo(clt_path)
#     h1 = HandleRepo(h1_path)
#     h2 = HandleRepo(h2_path)
#     clt.add_handle(h1, "handle1")
#     clt.add_handle(h2, "handle2")
#
#     backend = CollectionRepoBackend(clt)
#     #handles = backend.get_handles()
#
#     assert_equal(set(backend.keys()), {"handle1", "handle2"})
#     assert_in((URIRef(get_local_file_url(h1_path)), RDF.type, DLNS.Handle),
#               backend["handle1"].meta)
#     assert_equal(len(backend["handle1"].meta), 1)
#     assert_in((URIRef(get_local_file_url(h2_path)), RDF.type, DLNS.Handle),
#               backend["handle2"].meta)
#     assert_equal(len(backend["handle2"].meta), 1)
#     assert_equal(backend["handle1"].meta.identifier, Literal("handle1"))
#     assert_equal(backend["handle2"].meta.identifier, Literal("handle2"))
#
#     # TODO: Currently, CollectionRepoHandleBackend doesn't read config.ttl
#     # Not sure yet whether this is desirable behaviour, but should be
#     # consistent across classes.
#
#
# @with_tempfile
# @with_tempfile
# @with_tempfile
# def test_CollectionRepoBackend_get_collection(path, h1_path, h2_path):
#     clt = CollectionRepo(path)
#     h1 = HandleRepo(h1_path)
#     h2 = HandleRepo(h2_path)
#     clt.add_handle(h1, "handle1")
#     clt.add_handle(h2, "handle2")
#     backend = CollectionRepoBackend(clt)
#     collection = backend.meta
#
#     assert_equal(collection.identifier, Literal(clt.name))
#     assert_in((DLNS.this, RDF.type, DLNS.Collection), collection)
#     assert_in((DLNS.this, DCTERMS.hasPart,
#                URIRef(get_local_file_url(h1_path))), collection)
#     assert_in((DLNS.this, DCTERMS.hasPart,
#                URIRef(get_local_file_url(h2_path))), collection)
#     assert_equal(len(collection), 3)

