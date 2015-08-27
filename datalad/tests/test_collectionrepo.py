# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of classes CollectionRepo, CollectionRepoBackend and
CollectionRepoHandleBackend.
"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in, \
    assert_not_in
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import FOAF

from ..support.gitrepo import GitRepo
from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.metadatahandler import DLNS, RDF, RDFS, DCTERMS
from ..tests.utils import with_tempfile, with_testrepos, \
    assert_cwd_unchanged, on_windows, on_linux, ok_clean_git_annex_proxy, \
    swallow_logs, swallow_outputs, in_, with_tree, \
    get_most_obscure_supported_name, ok_clean_git, ok_
from ..support.exceptions import CollectionBrokenError
from ..utils import get_local_file_url

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']

# TODO: provide a minimal test collection, that contains something valid

@with_tempfile
@with_tempfile
def test_CollectionRepo_constructor(clean_path, clean_path2):
    # Just a brand new CollectionRepo:
    clt = CollectionRepo(clean_path)
    clt2 = CollectionRepo(clean_path2, name='different')

    ok_clean_git(clean_path, annex=False)
    ok_clean_git(clean_path2, annex=False)
    # TODO: ok_clean_git doesn't work on empty repo, due to
    # repo.head.is_valid() returns False

    # test collection's name:
    assert_equal(os.path.basename(os.path.normpath(clean_path)),
                 clt.name)
    assert_equal('different', clt2.name)

    # basic files created?
    ok_(os.path.exists(opj(clt.path, 'datalad.ttl')), "Missing 'datalad.ttl'.")
    ok_(os.path.exists(opj(clt.path, 'config.ttl')), "Missing 'config.ttl'.")

    # testing the actual statements stored in these files:
    # TODO: Keep this test up to date!
    # datalad.ttl
    g_datalad = Graph().parse(opj(clean_path, 'datalad.ttl'), format="turtle")
    assert_equal(len(g_datalad), 1)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), g_datalad,
              "Missing DLNS.Collection statement.")

    # config.ttl
    g_config = Graph().parse(opj(clean_path, 'config.ttl'), format="turtle")
    assert_equal(len(g_config), 2,
                 "Unexpected number of statements in config.ttl.")
    assert_in((DLNS.this, RDF.type, DLNS.Collection), g_config,
              "Missing DLNS.Collection statement.")
    assert_in((DLNS.this, RDFS.label, Literal(clt.name)), g_config,
              "Missing RDFS.label.")


@with_tempfile
def test_CollectionRepo_name(path):
    # tests get_name and set_name
    clt = CollectionRepo(path)
    assert_equal(clt.name,
                 os.path.basename(path))
    clt.name = "new_name"
    assert_equal(Graph().parse(opj(path, 'config.ttl'),
                               format="turtle").value(subject=DLNS.this,
                                                      predicate=RDFS.label),
                 Literal("new_name"))
    assert_equal(clt.name, "new_name")


@with_tempfile
def test_CollectionRepo_filename2key(path):
    # conversion of a handle's key to the name of the directory it's metadata
    # is stored in, and vice versa.
    clt = CollectionRepo(path, name="collectionname")

    # test _filename2key:
    # currently does nothing than return the input:
    input = get_most_obscure_supported_name()
    assert_equal(input, clt._filename2key(input))
    assert_equal("some/thing", clt._filename2key("some--thing"))

    # test _key2filename:
    assert_equal("handlename", clt._key2filename("collectionname/handlename"))
    assert_equal("what--ever", clt._key2filename("what/ever"))
    assert_raises(ValueError, clt._key2filename, "dsf\\dsfg")



@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_CollectionRepo_add_handle(annex_path, clone_path, clt_path):

    # Note: for now just tests to add a HandleRepo instance.
    # todo: different types!

    handle = HandleRepo(clone_path, annex_path)
    clt = CollectionRepo(clt_path)
    clt.add_handle(handle, "first_handle")
    ok_clean_git(clt_path, annex=False)

    # test file layout:
    ok_(os.path.exists(opj(clt.path, "first_handle")))
    ok_(os.path.isdir(opj(clt.path, "first_handle")))
    ok_(os.path.exists(opj(clt.path, "first_handle", "datalad.ttl")))
    ok_(os.path.exists(opj(clt.path, "first_handle", "config.ttl")))

    # test statements:
    # 1. within collection level metadata:
    g_datalad = Graph().parse(opj(clt.path, 'datalad.ttl'), format="turtle")

    handle_uri = g_datalad.value(subject=DLNS.this, predicate=DCTERMS.hasPart)
    assert_equal(handle_uri, URIRef(get_local_file_url(handle.path)))
    # TODO: one says "file:///..." and the other just "/..."
    # Note: Use datalad/utils.py:60:def get_local_file_url(fname)

    # 2. handle's metadata:
    g_config = Graph().parse(opj(clt.path, 'first_handle', 'config.ttl'),
                             format="turtle")
    assert_equal(g_config.value(subject=handle_uri, predicate=RDFS.label),
                 Literal('first_handle'))
    assert_equal(g_config.value(subject=handle_uri,
                                predicate=DLNS.defaultTarget),
                 Literal('first_handle'))


@with_testrepos(flavors=local_flavors)
@with_tempfile
@with_tempfile
def test_CollectionRepo_remove_handle(annex_path, handle_path, clt_path):

    # TODO: See add_handle. Test other types than just HandleRepo

    handle = HandleRepo(handle_path, annex_path)
    clt = CollectionRepo(clt_path)
    clt.add_handle(handle, "MyHandle")
    clt.remove_handle("MyHandle")
    ok_clean_git(clt_path, annex=False)

    # test files:
    assert_false(os.path.exists(opj(clt_path, "MyHandle")))

    # test statements in collection's graph
    g_datalad = Graph().parse(opj(clt.path, 'datalad.ttl'), format="turtle")

    assert_equal(len(list(g_datalad.objects(subject=DLNS.this,
                                            predicate=DCTERMS.hasPart))),
                 0, "Collection's graph still contains handle(s).")

@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepo_get_handle_list(clt_path, h1_path, h2_path):

    clt = CollectionRepo(clt_path)
    h1 = HandleRepo(h1_path)
    h2 = HandleRepo(h2_path)

    clt.add_handle(h1, "handle1")
    clt.add_handle(h2, "handle2")
    assert_equal({"handle1", "handle2"}, set(clt.get_handle_list()))

    # todo: query non-active (remote) branch


@with_tempfile
def test_CollectionRepo_get_backend(path):
    clt = CollectionRepo(path)
    backend = clt.get_backend_from_branch()
    backend2 = CollectionRepoBackend(clt)
    assert_equal(backend.branch, backend2.branch)
    assert_equal(backend.is_read_only, backend2.is_read_only)
    assert_equal(backend.repo, backend2.repo)
    assert_equal(backend.url, backend2.url)
    assert_equal(backend.get_handles(), backend2.get_handles())
    assert_equal(backend.get_collection(), backend2.get_collection())


def test_CollectionRepo_metadata_handle():
    """tests method add_metadata_src_to_handle"""
    raise SkipTest

# testing CollectionRepoBackend:


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
    assert_in((DLNS.this, DCTERMS.hasPart, URIRef(get_local_file_url(h1_path))),
              collection)
    assert_in((DLNS.this, DCTERMS.hasPart, URIRef(get_local_file_url(h2_path))),
              collection)
    assert_equal(len(collection), 3)


def test_CollectionRepoBackend_commit_collection():
    raise SkipTest

# testing CollectionRepoHandleBackend:


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepoHandleBackend_constructor(path1, path2, h1_path, h2_path):

    # setup
    clt = CollectionRepo(path1, name='testcollection')
    clt2 = CollectionRepo(path2, name='testcollection2')
    h1 = HandleRepo(h1_path)
    h2 = HandleRepo(h2_path)
    clt.add_handle(h1, "handle1")
    clt2.add_handle(h2, "handle2")
    clt.git_remote_add("remoterepo", path2)
    clt.git_fetch("remoterepo")

    # constructors to test:
    be1 = CollectionRepoHandleBackend(clt, "handle1")
    be2 = CollectionRepoHandleBackend(clt, "master/handle1")
    be3 = CollectionRepoHandleBackend(clt, "handle1", "master")
    be4 = CollectionRepoHandleBackend(clt, "handle2", "remoterepo/master")
    be5 = CollectionRepoHandleBackend(clt, "handle2", "remoterepo")
    # TODO: Should also be possible: key="remoterepo/handle2" with no branch passed.

    assert_raises(RuntimeError, CollectionRepoHandleBackend,
                  clt, "notexisting")

    # tests:
    assert_equal(be1._path, "handle1")
    assert_equal(be2._path, "handle1")
    assert_equal(be3._path, "handle1")
    assert_equal(be4._path, "handle2")
    assert_equal(be5._path, "handle2")

    assert_false(be1.is_read_only)
    assert_false(be2.is_read_only)
    assert_false(be3.is_read_only)
    ok_(be4.is_read_only)
    ok_(be5.is_read_only)

    assert_equal(be1.url, get_local_file_url(h1_path))
    assert_equal(be2.url, get_local_file_url(h1_path))
    assert_equal(be3.url, get_local_file_url(h1_path))
    assert_equal(be4.url, get_local_file_url(h2_path))
    assert_equal(be5.url, get_local_file_url(h2_path))


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepoHandleBackend_get_metadata(path1, path2, h1_path,
                                                  h2_path):
    # setup
    clt = CollectionRepo(path1, name='testcollection')
    clt2 = CollectionRepo(path2, name='testcollection2')
    h1 = HandleRepo(h1_path)
    h2 = HandleRepo(h2_path)
    clt.add_handle(h1, "handle1")
    clt2.add_handle(h2, "handle2")
    clt.git_remote_add("remoterepo", path2)
    clt.git_fetch("remoterepo")

    # backends:
    be1 = CollectionRepoHandleBackend(clt, "handle1")
    be2 = CollectionRepoHandleBackend(clt, "handle2", "remoterepo")

    # metadata:
    meta1 = be1.get_metadata()
    meta2 = be2.get_metadata()

    # tests:
    assert_equal(meta1.identifier, Literal("handle1"))
    assert_equal(meta2.identifier, Literal("handle2"))
    assert_equal(len(meta1), 1)
    assert_equal(len(meta2), 1)
    assert_in((URIRef(get_local_file_url(h1_path)), RDF.type, DLNS.Handle),
              meta1)
    assert_in((URIRef(get_local_file_url(h2_path)), RDF.type, DLNS.Handle),
              meta2)


def test_CollectionRepoHandleBackend_set_metadata():
    raise SkipTest
