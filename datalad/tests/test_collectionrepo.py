# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of classes CollectionRepo, CollectionRepoBackend
"""

import os
from git.exc import NoSuchPathError, InvalidGitRepositoryError
from os.path import join as opj, exists

from nose import SkipTest
from nose.tools import assert_raises, assert_false, assert_in
from rdflib import Graph, Literal, URIRef
from rdflib.plugins.parsers.notation3 import BadSyntax
from six import iterkeys

from datalad.support.collection_backends import CollectionRepoBackend
from ..consts import REPO_CONFIG_FILE, REPO_STD_META_FILE
from ..support.collectionrepo import CollectionRepo
from ..support.exceptions import CollectionBrokenError
from ..support.gitrepo import GitRepo
from ..support.handlerepo import HandleRepo
from ..support.metadatahandler import DLNS, RDF, RDFS, DCTERMS
from ..tests.utils import with_tempfile, with_testrepos, \
    on_windows, get_most_obscure_supported_name, ok_clean_git, ok_, eq_, \
    ok_startswith
from ..utils import get_local_file_url

# For now (at least) we would need to clone from the network
# since there are troubles with submodules on Windows.
# See: https://github.com/datalad/datalad/issues/44
local_flavors = ['network-clone' if on_windows else 'local']


@with_tempfile
@with_tempfile
@with_tempfile
def test_CollectionRepo_constructor(clean_path, clean_path2, clean_path3):
    # Just a brand new CollectionRepo:
    clt = CollectionRepo(clean_path)
    clt2 = CollectionRepo(clean_path2, name='different')

    ok_clean_git(clean_path, annex=False)
    ok_clean_git(clean_path2, annex=False)

    # test collection's name:
    eq_(os.path.basename(os.path.normpath(clean_path)),
                 clt.name)
    eq_('different', clt2.name)

    # basic files created?
    ok_(os.path.exists(opj(clt.path, REPO_STD_META_FILE)), "Missing '%s'." %
        REPO_STD_META_FILE)
    ok_(os.path.exists(opj(clt.path, REPO_CONFIG_FILE)), "Missing '%s'." %
        REPO_CONFIG_FILE)

    # testing the actual statements stored in these files:
    # TODO: Keep this test up to date!
    # datalad.ttl
    g_datalad = Graph().parse(opj(clean_path, REPO_STD_META_FILE),
                              format="turtle")
    eq_(len(g_datalad), 1)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), g_datalad,
              "Missing DLNS.Collection statement.")

    # config.ttl
    g_config = Graph().parse(opj(clean_path, REPO_CONFIG_FILE),
                             format="turtle")
    eq_(len(g_config), 2,
                 "Unexpected number of statements in %s." % REPO_CONFIG_FILE)
    assert_in((DLNS.this, RDF.type, DLNS.Collection), g_config,
              "Missing DLNS.Collection statement.")
    assert_in((DLNS.this, RDFS.label, Literal(clt.name)), g_config,
              "Missing RDFS.label.")

    # now, test Exceptions:
    assert_raises(NoSuchPathError, CollectionRepo, clean_path3, create=False)
    os.mkdir(clean_path3)
    assert_raises(InvalidGitRepositoryError, CollectionRepo, clean_path3,
                  create=False)
    gr = GitRepo(clean_path3)
    ok_(os.path.exists(opj(clean_path3, '.git')))
    assert_raises(CollectionBrokenError, CollectionRepo, clean_path3,
                  create=False)
    with open(opj(clean_path3, REPO_CONFIG_FILE), 'w') as f:
        f.write("invalid %s" % REPO_CONFIG_FILE)
    gr.git_add(REPO_CONFIG_FILE)
    gr.git_commit("setup invalid %s" % REPO_CONFIG_FILE)
    assert_raises(BadSyntax, CollectionRepo, clean_path3,
                  create=False)
    # TODO: Provide broken testrepos for better testing;
    # not just collection repos


@with_tempfile
def test_CollectionRepo_name(path):
    # tests get_name and set_name
    clt = CollectionRepo(path)
    eq_(clt.name,
                 os.path.basename(path))
    clt.name = "new_name"
    eq_(Graph().parse(opj(path, REPO_CONFIG_FILE),
                               format="turtle").value(subject=DLNS.this,
                                                      predicate=RDFS.label),
                 Literal("new_name"))
    eq_(clt.name, "new_name")


@with_tempfile
def test_CollectionRepo_filename2key(path):
    # conversion of a handle's key to the name of the directory it's metadata
    # is stored in, and vice versa.
    clt = CollectionRepo(path, name="collectionname")

    # test _filename2key:
    # currently does nothing than return the input:
    input = get_most_obscure_supported_name()
    eq_(input, clt._filename2key(input))
    eq_("some/thing", clt._filename2key("some--thing"))

    # test _key2filename:
    eq_("handlename", clt._key2filename("collectionname/handlename"))
    eq_("what--ever", clt._key2filename("what/ever"))
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
    ok_(os.path.exists(opj(clt.path, "first_handle", REPO_STD_META_FILE)))
    ok_(os.path.exists(opj(clt.path, "first_handle", REPO_CONFIG_FILE)))

    # test statements:
    # 1. within collection level metadata:
    g_datalad = Graph().parse(opj(clt.path, REPO_STD_META_FILE),
                              format="turtle")

    handle_uri = g_datalad.value(subject=DLNS.this, predicate=DCTERMS.hasPart)
    eq_(handle_uri, URIRef(get_local_file_url(handle.path)))
    # TODO: one says "file:///..." and the other just "/..."
    # Note: Use datalad/utils.py:60:def get_local_file_url(fname)

    # 2. handle's metadata:
    g_config = Graph().parse(opj(clt.path, 'first_handle', REPO_CONFIG_FILE),
                             format="turtle")
    eq_(g_config.value(subject=handle_uri, predicate=RDFS.label),
                 Literal('first_handle'))
    eq_(g_config.value(subject=handle_uri,
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
    g_datalad = Graph().parse(opj(clt.path, REPO_STD_META_FILE),
                              format="turtle")

    eq_(len(list(g_datalad.objects(subject=DLNS.this,
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
    eq_({"handle1", "handle2"}, set(clt.get_handle_list()))

    # todo: query non-active (remote) branch


@with_tempfile
def test_CollectionRepo_get_backend(path):
    clt = CollectionRepo(path)
    backend = clt.get_backend_from_branch()
    backend2 = CollectionRepoBackend(clt)
    eq_(backend.branch, backend2.branch)
    eq_(backend.is_read_only, backend2.is_read_only)
    eq_(backend.repo, backend2.repo)
    eq_(backend.url, backend2.url)
    eq_(set(iterkeys(backend)), set(iterkeys(backend2)))
    eq_(backend.meta, backend2.meta)


@with_tempfile
def test_CollectionRepo_get_collection_graphs(path):

    repo = CollectionRepo(path, create=True)

    # default
    graphs = repo.get_collection_graphs()
    eq_(len(graphs), 2)  # just datalad.ttl and config.ttl
    assert_in(REPO_CONFIG_FILE[:-4], graphs)
    assert_in(REPO_STD_META_FILE[:-4], graphs)
    assert_in((DLNS.this, RDF.type, DLNS.Collection),
              graphs[REPO_STD_META_FILE[:-4]])
    assert_in((DLNS.this, RDFS.label, Literal(repo.name)),
              graphs[REPO_CONFIG_FILE[:-4]])

    # TODO: Use several metadata files (partially). See Handle.
    #       Also for handles in collections!


@with_tempfile
def test_CollectionRepo_set_collection_graphs(path):

    repo = CollectionRepo(path, create=True)
    
    metadata = dict()
    metadata['graph1'] = Graph()
    metadata['graph1'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.FakeTerm))

    repo.set_collection_graphs(metadata)
    ok_clean_git(path, annex=False)
    target_file_1 = opj(path, "graph1.ttl")
    ok_(exists(target_file_1))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))

    # not existing branch:
    with assert_raises(ValueError) as cm:
        repo.set_collection_graphs(metadata, branch="notexisting")
    ok_startswith(str(cm.exception), "Unknown branch")

    # create new branch and switch back:
    repo.git_checkout("new_branch", "-b")
    repo.git_checkout("master")

    # store metadata to not checked-out branch:
    metadata['graph2'] = Graph()
    metadata['graph2'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.AnotherFakeTerm))
    target_file_2 = opj(path, "graph2.ttl")
    repo.set_collection_graphs(metadata, branch="new_branch")

    ok_clean_git(path, annex=False)
    eq_(repo.git_get_active_branch(), "master")
    ok_(not exists(target_file_2))

    repo.git_checkout("new_branch")
    ok_(exists(target_file_1))
    ok_(exists(target_file_2))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))
    eq_(set(iter(metadata['graph2'])),
        set(iter(Graph().parse(target_file_2, format="turtle"))))

    # element of wrong type:
    metadata['second'] = list()
    with assert_raises(TypeError) as cm:
        repo.set_collection_graphs(metadata)
    ok_startswith(str(cm.exception),
                  "Wrong type of graphs['second'] (%s)" % list)

    # parameter of wrong type:
    with assert_raises(TypeError) as cm:
        repo.set_collection_graphs([1, 2])
    ok_startswith(str(cm.exception),
                  "Unexpected type of parameter 'graphs' (%s)" % list)


@with_testrepos('collection', flavors=['local'])
def test_CollectionRepo_get_handle_graphs(cpath):

    repo = CollectionRepo(cpath, create=False)

    # default
    graphs = repo.get_handle_graphs('BasicHandle')
    eq_(len(graphs), 2)  # just datalad.ttl and config.ttl
    assert_in(REPO_CONFIG_FILE[:-4], graphs)
    assert_in(REPO_STD_META_FILE[:-4], graphs)
    h_uri = graphs[REPO_STD_META_FILE[:-4]].value(predicate=RDF.type,
                                                  object=DLNS.Handle)
    ok_(h_uri is not None)
    ok_startswith(h_uri, "file://")
    assert_in((h_uri, RDFS.label, Literal('BasicHandle')),
              graphs[REPO_CONFIG_FILE[:-4]])

    # TODO: remote branch, not checked out branch, etc.
    # needs more test repos


@with_testrepos('collection', flavors=['clone'])
@with_tempfile
def test_CollectionRepo_set_handle_graphs(curl, cpath):
    repo = CollectionRepo(cpath, curl, create=True)

    metadata = dict()
    metadata['graph1'] = Graph()
    metadata['graph1'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.FakeTerm))

    repo.store_handle_graphs(metadata, 'BasicHandle')

    ok_clean_git(cpath, annex=False)
    target_file_1 = opj(cpath, repo._key2filename('BasicHandle'), "graph1.ttl")
    ok_(exists(target_file_1))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))

    # not existing branch:
    with assert_raises(ValueError) as cm:
        repo.store_handle_graphs(metadata, 'BasicHandle', branch="notexisting")
    ok_startswith(str(cm.exception), "Unknown branch")

    # create new branch and switch back:
    repo.git_checkout("new_branch", "-b")
    repo.git_checkout("master")

    # store metadata to not checked-out branch:
    metadata['graph2'] = Graph()
    metadata['graph2'].add((URIRef("http://example.org"),
                            RDF.type,
                            DLNS.AnotherFakeTerm))
    target_file_2 = opj(cpath, repo._key2filename('BasicHandle'), "graph2.ttl")
    repo.store_handle_graphs(metadata, 'BasicHandle', branch="new_branch")

    ok_clean_git(cpath, annex=False)
    eq_(repo.git_get_active_branch(), "master")
    ok_(not exists(target_file_2))

    repo.git_checkout("new_branch")
    ok_(exists(target_file_1))
    ok_(exists(target_file_2))
    eq_(set(iter(metadata['graph1'])),
        set(iter(Graph().parse(target_file_1, format="turtle"))))
    eq_(set(iter(metadata['graph2'])),
        set(iter(Graph().parse(target_file_2, format="turtle"))))

    # element of wrong type:
    metadata['second'] = list()
    with assert_raises(TypeError) as cm:
        repo.store_handle_graphs(metadata, 'BasicHandle')
    ok_startswith(str(cm.exception),
                  "Wrong type of graphs['second'] (%s)" % list)

    # parameter of wrong type:
    with assert_raises(TypeError) as cm:
        repo.store_handle_graphs([1, 2], 'BasicHandle')
    ok_startswith(str(cm.exception),
                  "Unexpected type of parameter 'graphs' (%s)" % list)


def test_CollectionRepo_metadata_handle():
    """tests method add_metadata_src_to_handle"""
    raise SkipTest
