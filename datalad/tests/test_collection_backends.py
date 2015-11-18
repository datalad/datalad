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

from nose.tools import assert_equal, assert_in
from rdflib import URIRef, RDF, Literal
from rdflib.namespace import DCTERMS

from datalad.support.collection_backends import CollectionRepoBackend
from datalad.support.collectionrepo import CollectionRepo
from datalad.support.handlerepo import HandleRepo
from datalad.support.metadatahandler import DLNS
from datalad.tests.utils import with_tempfile
from datalad.utils import get_local_file_url


@with_tempfile
@with_tempfile
def test_CollectionRepoBackend_constructor(path1, path2):

    # set up collection repo:
    clt = CollectionRepo(path1, name='testcollection')
    clt.git_checkout("another-branch", options="-b")
    clt2 = CollectionRepo(path2, name='testcollection2')
    clt.git_remote_add("remoterepo", path2)

    # constructor from existing CollectionRepo instance:
    clt_be_1 = CollectionRepoBackend(clt)
    assert_equal(clt_be_1.branch, "another-branch")
    assert_equal(clt, clt_be_1.repo)
    assert_equal(clt_be_1.is_read_only, False)
    clt_be_2 = CollectionRepoBackend(clt, "master")
    assert_equal(clt_be_2.branch, "master")
    assert_equal(clt, clt_be_2.repo)
    assert_equal(clt_be_2.is_read_only, False)
    clt_be_3 = CollectionRepoBackend(clt, "remoterepo/master")
    assert_equal(clt_be_3.branch, "remoterepo/master")
    assert_equal(clt, clt_be_3.repo)
    assert_equal(clt_be_3.is_read_only, True)

    # constructor from path to collection repo:
    clt_be_4 = CollectionRepoBackend(path1)
    assert_equal(clt.path, clt_be_4.repo.path)
    assert_equal(clt_be_4.branch, "another-branch")
    assert_equal(clt_be_4.is_read_only, False)


@with_tempfile
@with_tempfile
def test_CollectionRepoBackend_url(path1, path2):

    clt = CollectionRepo(path1, name='testcollection')
    clt2 = CollectionRepo(path2, name='testcollection2')
    clt.git_remote_add("remoterepo", path2)
    clt.git_fetch("remoterepo")

    backend1 = CollectionRepoBackend(clt)
    assert_equal(backend1.url, path1)
    backend2 = CollectionRepoBackend(clt, "remoterepo/master")
    assert_equal(backend2.url, path2)


@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepoBackend_get_handles(clt_path, h1_path, h2_path):

    clt = CollectionRepo(clt_path)
    h1 = HandleRepo(h1_path)
    h2 = HandleRepo(h2_path)
    clt.add_handle(h1, "handle1")
    clt.add_handle(h2, "handle2")

    backend = CollectionRepoBackend(clt)
    handles = backend.get_handles()

    assert_equal(set(handles.keys()), {"handle1", "handle2"})
    assert_in((URIRef(get_local_file_url(h1_path)), RDF.type, DLNS.Handle),
              handles["handle1"].meta)
    assert_equal(len(handles["handle1"].meta), 1)
    assert_in((URIRef(get_local_file_url(h2_path)), RDF.type, DLNS.Handle),
              handles["handle2"].meta)
    assert_equal(len(handles["handle2"].meta), 1)
    assert_equal(handles["handle1"].meta.identifier, Literal("handle1"))
    assert_equal(handles["handle2"].meta.identifier, Literal("handle2"))

    # TODO: Currently, CollectionRepoHandleBackend doesn't read config.ttl
    # Not sure yet whether this is desirable behaviour, but should be
    # consistent across classes.


@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepoBackend_get_collection(path, h1_path, h2_path):
    clt = CollectionRepo(path)
    h1 = HandleRepo(h1_path)
    h2 = HandleRepo(h2_path)
    clt.add_handle(h1, "handle1")
    clt.add_handle(h2, "handle2")
    backend = CollectionRepoBackend(clt)
    collection = backend.get_collection()

    assert_equal(collection.identifier, Literal(clt.name))
    assert_in((DLNS.this, RDF.type, DLNS.Collection), collection)
    assert_in((DLNS.this, DCTERMS.hasPart,
               URIRef(get_local_file_url(h1_path))), collection)
    assert_in((DLNS.this, DCTERMS.hasPart,
               URIRef(get_local_file_url(h2_path))), collection)
    assert_equal(len(collection), 3)


def test_CollectionRepoBackend_commit_collection():
    raise SkipTest