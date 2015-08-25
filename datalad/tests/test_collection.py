# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class Collection
"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in
from rdflib import Graph, Literal, URIRef
from six import iterkeys

from ..support.handlerepo import HandleRepo, HandleRepoBackend
from ..support.handle import Handle
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend
from ..support.collection import Collection, DLNS, RDF, DCTERMS
from ..tests.utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    on_windows, ok_clean_git_annex_proxy, swallow_logs, swallow_outputs, in_, \
    with_tree, get_most_obscure_supported_name, ok_clean_git, ok_
from ..support.exceptions import CollectionBrokenError
from ..utils import get_local_file_url

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@with_tempfile
@with_tempfile
def test_Collection_constructor(path, h_path):
    repo = CollectionRepo(path)
    handle = HandleRepo(h_path)
    repo.add_handle(handle, "handle1")

    collection = Collection(CollectionRepoBackend(repo))
    assert_equal(collection.name, repo.name)
    assert_equal(collection.meta.identifier, Literal(repo.name))
    assert_equal(set(iterkeys(collection)), {"handle1"})
    assert_equal(len(list(collection.store.contexts())), 2)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), collection.meta)
    assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
              collection["handle1"].meta)

    copy_collection = Collection(collection)
    assert_equal(copy_collection.name, collection.name)
    assert_equal(copy_collection.meta.identifier, Literal(repo.name))
    assert_equal(set(iterkeys(copy_collection)), {"handle1"})
    assert_equal(len(list(copy_collection.store.contexts())), 2)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), copy_collection.meta)
    assert_in((URIRef(get_local_file_url(h_path)), RDF.type, DLNS.Handle),
              copy_collection["handle1"].meta)

    empty_collection = Collection(name="empty")
    assert_equal(empty_collection.name, "empty")
    assert_equal(empty_collection.meta.identifier, Literal("empty"))
    assert_equal(set(iterkeys(empty_collection)), set([]))
    assert_equal(len(list(empty_collection.store.contexts())), 1)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), empty_collection.meta)
    # test _reload() separately?


@with_tempfile
def test_Collection_setitem(path):
    collection = Collection(name="new_collection")
    handle1 = Handle(HandleRepoBackend(HandleRepo(path, name="handle1")))
    handle2 = Handle(name="handle2")

    collection["handle1"] = handle1
    assert_equal(set(iterkeys(collection)), {"handle1"})
    assert_equal(collection["handle1"], handle1)
    assert_equal(len(collection.meta), 2)



    # TODO: Wrong! handle uri needs to be changed. Is still "this"!



    # assert_in((URIRef(get_local_file_url(path)), RDF.type, DLNS.Handle),
    #           collection["handle1"].meta)
    # assert_in((DLNS.this, DCTERMS.hasPart, URIRef(get_local_file_url(path))),
    #           collection.meta)


    collection["handle2"] = handle2

    #ok_(False, collection.meta.serialize(format="turtle"))

    #assert_in((DLNS.this, DCTERMS.hasPart, )

    #    collection.meta


@with_tempfile
def test_Collection_delitem(path):
    collection = Collection(name="new_collection")
    handle1 = Handle(HandleRepoBackend(HandleRepo(path, name="handle1")))
    collection["handle1"] = handle1
    del collection["handle1"]

    assert_equal(set(iterkeys(collection)), set([]))
    assert_equal(len(list(collection.meta.objects(subject=DLNS.this,
                                                  predicate=DCTERMS.hasPart))),
                 0)

    # TODO: pop doesn't call __delitem__. So we need to override this one, too.
    # collection.pop("handle1")


@with_tempfile
def test_Collection_commit(path):
    raise SkipTest