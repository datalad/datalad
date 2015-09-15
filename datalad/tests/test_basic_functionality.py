# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for functionality of basic datalad commands"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in, \
    assert_not_in, assert_is_instance
from six import iterkeys

from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.collection import Collection, MetaCollection
from ..support.metadatahandler import PlainTextImporter, PAV, PROV, DCTERMS, \
    DCTYPES, DLNS, DCAT, FOAF, EMP, Literal, URIRef
from ..tests.utils import ok_clean_git, ok_clean_git_annex_proxy, \
    with_tempfile, ok_, with_tree
from ..utils import get_local_file_url, rmtree

from .utils import skip_if_no_network

# Note: For the actual commands use the following to determine paths to
# the local master collection, configs, etc.:
# from appdirs import AppDirs
# dirs = AppDirs("datalad", "datalad.org")
# path_to_local_master = os.path.join(dirs.user_data_dir, 'localcollection')


@with_tempfile
def test_local_master(m_path):

    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    assert_equal(m_path, local_master.path)
    ok_clean_git(m_path, annex=False)
    ok_(os.path.exists(opj(m_path, 'datalad.ttl')))
    ok_(os.path.exists(opj(m_path, 'config.ttl')))
    assert_equal(local_master.get_handle_list(), [])


@skip_if_no_network
@with_tempfile
def test_register_collection(m_path):
    # TODO: redo using locally established collection
    test_url = "https://github.com/bpoldrack/ExampleCollection.git"
    test_name = test_url.split('/')[-1].rstrip('.git')
    assert_equal(test_name, 'ExampleCollection')

    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    local_master.git_remote_add(test_name, test_url)
    local_master.git_fetch(test_name)

    assert_equal(local_master.git_get_remotes(), [test_name])
    assert_equal(set(local_master.git_get_files(test_name + '/master')),
                 {'config.ttl', 'datalad.ttl'})
    ok_clean_git(m_path, annex=False)


@with_tempfile
@with_tempfile
def test_create_collection(m_path, c_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    # create the collection:
    new_collection = CollectionRepo(c_path, name='new_collection')
    assert_equal(new_collection.name, 'new_collection')

    # register with local master:
    local_master.git_remote_add(new_collection.name, new_collection.path)
    local_master.git_fetch(new_collection.name)

    assert_equal(local_master.git_get_remotes(), [new_collection.name])
    ok_clean_git(m_path, annex=False)
    ok_clean_git(c_path, annex=False)
    assert_equal(set(local_master.git_get_files(new_collection.name +
                                                '/master')),
                 {'config.ttl', 'datalad.ttl'})


@with_tempfile
@with_tempfile
def test_create_handle(m_path, h_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    # create the handle repository:
    handle = HandleRepo(h_path, name="MyHandleDefaultName")

    if handle.is_direct_mode():
        ok_clean_git_annex_proxy(h_path)
    else:
        ok_clean_git(h_path, annex=True)
    ok_(os.path.exists(opj(h_path, '.datalad')))
    ok_(os.path.isdir(opj(h_path, '.datalad')))
    ok_(os.path.exists(opj(h_path, '.datalad', 'datalad.ttl')))
    ok_(os.path.exists(opj(h_path, '.datalad', 'config.ttl')))

    # add it to the local master collection:
    local_master.add_handle(handle, name="MyHandle")

    ok_clean_git(local_master.path, annex=False)
    assert_equal(local_master.get_handle_list(), ["MyHandle"])


@with_tempfile
@with_tempfile
@with_tempfile
def test_add_handle_to_collection(m_path, c_path, h_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    # create collection:
    collection = CollectionRepo(c_path, name="MyCollection")
    # register collection:
    local_master.git_remote_add(collection.name, c_path)
    local_master.git_fetch(collection.name)
    # create handle:
    handle = HandleRepo(h_path, name="MyHandle")
    # add to master:
    local_master.add_handle(handle, handle.name)
    # add to collection:
    collection.add_handle(handle, handle.name)
    # update knowledge about the collection in local master:
    local_master.git_fetch(collection.name)

    ok_clean_git(local_master.path, annex=False)
    ok_clean_git(collection.path, annex=False)
    if handle.is_direct_mode():
        ok_clean_git_annex_proxy(handle.path)
    else:
        ok_clean_git(handle.path, annex=True)
    assert_equal(collection.get_handle_list(), ["MyHandle"])
    assert_equal(local_master.get_handle_list(), ["MyHandle"])
    assert_equal(set(local_master.git_get_files(collection.name + '/master')),
                 {'MyHandle/config.ttl', 'MyHandle/datalad.ttl',
                  'config.ttl', 'datalad.ttl'})
    assert_equal(set(collection.git_get_files()),
                 {'MyHandle/config.ttl', 'MyHandle/datalad.ttl',
                  'config.ttl', 'datalad.ttl'})


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_install_handle(m_path, c_path, h_path, install_path):
    handle_by_name = "MyCollection/MyHandle"

    # setup:
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    collection = CollectionRepo(c_path, name="MyCollection")
    handle = HandleRepo(h_path, name="MyHandle")
    collection.add_handle(handle, handle.name)
    local_master.git_remote_add(collection.name, collection.path)
    local_master.git_fetch(collection.name)

    # retrieve handle's url:
    q_col = handle_by_name.split('/')[0]
    q_hdl = handle_by_name.split('/')[1]

    handle_backend = CollectionRepoHandleBackend(repo=local_master, key=q_hdl,
                                                 branch=q_col + '/master')
    assert_equal(handle_backend.url, get_local_file_url(h_path))

    # install the handle:
    installed_handle = HandleRepo(install_path, handle_backend.url)
    local_master.add_handle(installed_handle, name=handle_by_name)

    if installed_handle.is_direct_mode():
        ok_clean_git_annex_proxy(install_path)
    else:
        ok_clean_git(install_path, annex=True)
    ok_clean_git(local_master.path, annex=False)
    assert_equal(set(installed_handle.git_get_files()),
                 {opj('.datalad', 'datalad.ttl'),
                  opj('.datalad', 'config.ttl')})
    assert_equal(installed_handle.git_get_remotes(), ['origin'])
    assert_equal(local_master.get_handle_list(), [handle_by_name])
    assert_equal(installed_handle.name, "MyHandle")


@skip_if_no_network
@with_tempfile
def test_unregister_collection(m_path):
    # TODO: redo using locally established collection
    # setup:
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    collection_url = "https://github.com/bpoldrack/ExampleCollection.git"
    local_master.git_remote_add(name="MyCollection", url=collection_url)
    local_master.git_fetch("MyCollection")

    # unregister:
    local_master.git_remote_remove("MyCollection")

    ok_clean_git(local_master.path, annex=False)
    assert_equal(local_master.git_get_remotes(), [])


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_uninstall_handle(m_path, c_path, h_path, install_path):

    # setup (install the handle to be uninstalled):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    collection = CollectionRepo(c_path, name="MyCollection")
    handle = HandleRepo(h_path, name="MyHandle")
    collection.add_handle(handle, handle.name)
    local_master.git_remote_add(collection.name, collection.path)
    local_master.git_fetch(collection.name)
    installed_handle = HandleRepo(install_path, h_path)
    local_master.add_handle(installed_handle, name="MyCollection/MyHandle")

    # test setup:
    ok_clean_git(local_master.path, annex=False)
    ok_clean_git(collection.path, annex=False)
    if handle.is_direct_mode():
        ok_clean_git_annex_proxy(handle.path)
    else:
        ok_clean_git(handle.path, annex=True)
    assert_equal(collection.get_handle_list(), ["MyHandle"])
    assert_equal(local_master.get_handle_list(), ["MyCollection/MyHandle"])


    # retrieve path of handle:

    q_col = local_master.get_handle_list()[0].split('/')[0]
    q_hdl = local_master.get_handle_list()[0].split('/')[1]

    handle_backend = CollectionRepoHandleBackend(repo=local_master, key=q_hdl,
                                                 branch=q_col + '/master')
    assert_equal(handle_backend.url, get_local_file_url(h_path))

    # uninstall handle:
    local_master.remove_handle("MyCollection/MyHandle")
    rmtree(h_path)

    ok_clean_git(local_master.path, annex=False)
    assert_equal(local_master.get_handle_list(), [])
    ok_(not os.path.exists(h_path))


@with_tempfile
@with_tempfile
@with_tree([
    ('AUTHORS', "Benjamin Poldrack <benjaminpoldrack@gmail.com>\n#\n# \n# "
                "bla, bla\n<justanemail@address.tl>\nsomeone else\n"
                "digital native <https://www.myfancypage.com/digital>"),
    ('LICENSE', "This is a license file\n with several lines."),
    ('README', "Read this to have a clue what the repository is about.\n"
               "This is metadata on a collection.")
    ])
def test_query_collection(c_path, h_path, md_hdl):

    # setup the collection to be queried:
    h_repo = HandleRepo(h_path)
    c_repo = CollectionRepo(c_path, name="MyCollection")
    c_repo.add_handle(h_repo, "MyHandle")
    c_repo.add_metadata_src_to_handle(PlainTextImporter, "MyHandle", md_hdl)
    collection = Collection(CollectionRepoBackend(c_repo))

    # TODO: Bindings should be done in collection class:
    # collection.conjunctive_graph.bind('prov', PROV)
    # collection.conjunctive_graph.bind('dcat', DCAT)
    # collection.conjunctive_graph.bind('dctypes', DCTYPES)
    # collection.conjunctive_graph.bind('dct', DCTERMS)
    # collection.conjunctive_graph.bind('pav', PAV)
    # collection.conjunctive_graph.bind('foaf', FOAF)
    # collection.conjunctive_graph.bind('dlns', DLNS)
    # collection.conjunctive_graph.bind('', EMP)
    collection.conjunctive_graph.namespace_manager = collection.meta.namespace_manager

    # query for a handle, which is authored by a person named
    # "Benjamin Poldrack":
    query_handle_certain_author = \
        """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                   ?r pav:createdBy ?p .
                                 ?p foaf:name "Benjamin Poldrack" .}}"""
    # same query, but "Benjamin Poldrack" authored SOMETHING in the handle,
    # not just the handle itself:
    alt_query_1 = \
        """SELECT ?g ?r {GRAPH ?g {?r pav:createdBy ?p .
                                   ?p foaf:name "Benjamin Poldrack" .}}"""

    # now just look for handles or direct child entities (handle content):
    alt_query_2 = \
        """SELECT ?g ?r {{GRAPH ?g {?r rdf:type dlns:Handle .
                                   ?r pav:createdBy ?p .
                                   ?p foaf:name "Benjamin Poldrack" .}}
                            UNION {GRAPH ?g {?r rdf:type dlns:Handle .
                                   ?r dct:hasPart ?c .
                                   ?c pav:createdBy ?p .
                                   ?p foaf:name "Benjamin Poldrack" .}}}"""

    results = collection.conjunctive_graph.query(query_handle_certain_author)
    # should result in the handle "MyHandle" and its location:
    assert_in((Literal("MyHandle"), URIRef(get_local_file_url(h_path))),
              results)
    assert_equal(len(results), 1)

    results2 = collection.conjunctive_graph.query(alt_query_1)
    # 2 results, one per each entity authored by "Benjamin Poldrack".
    # Both results contain the handle's name, but only one its location
    # (which is its uri). The uri of the content entity is artificial and of
    # no use here.
    # Note: This uri construction has to change.
    import os
    content_uri = URIRef(get_local_file_url(os.getcwd() + '/#content'))

    assert_equal(len(results2), 2)
    assert_in((Literal("MyHandle"), URIRef(get_local_file_url(h_path))),
              results2)
    assert_in((Literal("MyHandle"), content_uri), results2)

    results3 = collection.conjunctive_graph.query(alt_query_2)
    # 2 results, one resulting from the entity 'handle' itself
    # and one from the content of this handle. The select returns name and
    # location of the handle in both cases.
    assert_equal(len(results2), 2)
    assert_equal(set(results3),
                 {(Literal("MyHandle"), URIRef(get_local_file_url(h_path)))})


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
@with_tree([
    ('AUTHORS', "Benjamin Poldrack <benjaminpoldrack@gmail.com>\n#\n# \n# "
                "bla, bla\n<justanemail@address.tl>\nsomeone else\n"
                "digital native <https://www.myfancypage.com/digital>"),
    ('LICENSE', "This is a license file\n with several lines."),
    ('README', "Read this to have a clue what the repository is about.\n"
               "This is metadata on a collection.")
    ])
@with_tree([
    ('CONTRIBUTORS', "Benjamin Poldrack <benjaminpoldrack@gmail.com>\n#\n# \n"
                     "# bla, bla\n<justanemail@address.tl>\nanother one\n"
                     "digital native <https://www.myfancypage.com/digital>"),
    ('LICENSE', "http://example.com/license"),
    ('README', "Read this to have a clue what the repository is about. "
               "This is metadata on a handle.")
    ])
def test_query_metacollection(m_path, c_path1, c_path2, h_path1, h_path2,
                              md1, md2):

    # create the master collection; register two collections, each containing
    # one handle and metadata:
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    c_repo1 = CollectionRepo(c_path1, name="collection1")
    c_repo2 = CollectionRepo(c_path2, name="collection2")
    h_repo1 = HandleRepo(h_path1)
    h_repo2 = HandleRepo(h_path2)
    c_repo1.add_handle(h_repo1, name="handle1")
    c_repo2.add_handle(h_repo2, name="handle2")
    c_repo1.add_metadata_src_to_handle(PlainTextImporter, "handle1", md1)
    c_repo2.add_metadata_src_to_handle(PlainTextImporter, "handle2", md2)
    local_master.git_remote_add("collection1", c_path1)
    local_master.git_fetch("collection1")
    local_master.git_remote_add("collection2", c_path2)
    local_master.git_fetch("collection2")

    # now, retrieve the metacollection to be queried (all known collections):
    collections = [local_master.get_backend_from_branch(remote + "/master")
                   for remote in local_master.git_get_remotes()]
    collections.append(local_master.get_backend_from_branch())

    metacollection = MetaCollection(collections)

    assert_equal(set(iterkeys(metacollection)),
                 {"collection1", "collection2", "local"})
    [assert_is_instance(metacollection[key], Collection)
     for key in iterkeys(metacollection)]

    # TODO: prefix bindings! see test above
    metacollection.conjunctive_graph.namespace_manager = \
        Collection(CollectionRepoBackend(c_repo1)).meta.namespace_manager

    # query it:
    # query for a handle, which is authored by a person named
    # "Benjamin Poldrack":
    query_handle_certain_author1 = \
        """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                   ?r pav:createdBy ?p .
                                   ?p foaf:name "Benjamin Poldrack" .}}"""
    results = \
        metacollection.conjunctive_graph.query(query_handle_certain_author1)
    # returns both handles and their locations:
    assert_equal(len(results), 2)
    assert_in((Literal("handle1"), URIRef(get_local_file_url(h_path1))),
              results)
    assert_in((Literal("handle2"), URIRef(get_local_file_url(h_path2))),
              results)

    # query for author "another one" should return handle2 only:
    query_handle_certain_author2 = \
        """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                   ?r pav:createdBy ?p .
                                   ?p foaf:name "another one" .}}"""
    results2 = \
        metacollection.conjunctive_graph.query(query_handle_certain_author2)
    # returns handle2 and its location:
    assert_equal(len(results2), 1)
    assert_in((Literal("handle2"), URIRef(get_local_file_url(h_path2))),
              results2)

    # query for handle with any appearance of a string "Benjamin Poldrack":
    uni_query_1 = """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                             ?s ?p ?o .
                                             FILTER regex(?o, "Benjamin Poldrack", "i")}}"""

    results3 = metacollection.conjunctive_graph.query(uni_query_1)
    # returns both handles and their locations:
    assert_equal(len(results3), 2)
    assert_in((Literal("handle1"), URIRef(get_local_file_url(h_path1))),
              results3)
    assert_in((Literal("handle2"), URIRef(get_local_file_url(h_path2))),
              results3)

    # query for handle with any appearance of a string "This is a license file"
    uni_query_2 = """SELECT ?g ?r {GRAPH ?g {?r rdf:type dlns:Handle .
                                             ?s ?p ?o .
                                             FILTER regex(?o, "This is a license file", "i")}}"""
    results4 = metacollection.conjunctive_graph.query(uni_query_2)
    # returns handle1 and its location:
    assert_equal(len(results4), 1)
    assert_in((Literal("handle1"), URIRef(get_local_file_url(h_path1))),
              results4)
