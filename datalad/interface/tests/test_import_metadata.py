# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for import-metadata command

"""

__docformat__ = 'restructuredtext'

from os.path import basename, exists, isdir, join as opj
from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...api import import_metadata, install_handle, create_collection, \
    add_handle
from ...utils import swallow_logs, getpwd, chpwd
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.metadatahandler import DLNS, PAV, DCTERMS, URIRef, RDF, FOAF, \
    PROV, Literal, Graph
from ...support.handlerepo import HandleRepo
from ...support.collectionrepo import CollectionRepo
from datalad.support.collection import Collection
from datalad.support.collection_backends import CollectionRepoBackend
from ...consts import REPO_CONFIG_FILE, REPO_STD_META_FILE, HANDLE_META_DIR


@assert_cwd_unchanged
@with_testrepos('meta_pt_annex_handle', flavors=['clone'])
@with_tempfile
@with_tempfile(mkdir=True)
def test_import_meta_handle(hurl, hpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        install_handle(hurl, hpath)
        current_dir = getpwd()
        chpwd(hpath)

        handle = import_metadata(format="plain-text", path=hpath)
        chpwd(current_dir)

        assert_is_instance(handle, Handle)

        # test the metadata in returned Handle instance as well as the
        # metadata, that is actually stored in the repository:

        # TODO: Care for empty prefix, which causes several issues.
        # Note: Previously parsed stored graph the following way:
        # stored_graph = Graph().parse(
        #     opj(hpath, HANDLE_META_DIR, REPO_STD_META_FILE), format="turtle")
        # This fails, due to the 'empty' prefix in graphs, which is converted
        # by rdflib to the file's path in case we parse a file and to cwd in
        # case we parse a string (as we do when getting the file's content
        # from git instead of getting it from the file directly). Need to find
        # a better solution to replace that prefix anyway. Therefore: delay.
        #
        # For now, get the stored graph the same way for comparison:
        repo = HandleRepo(hpath, create=False)
        stored_graph = Graph().parse(data='\n'.join(repo.git_get_file_content(
            opj(HANDLE_META_DIR, REPO_STD_META_FILE))), format="turtle")

        # test license:
        assert_in((DLNS.this, DCTERMS.license,
                   Literal("A license, allowing for several things to do "
                           "with\nthe content, provided by this handle.")),
                  handle.meta)
        assert_in((DLNS.this, DCTERMS.license,
                   Literal("A license, allowing for several things to do "
                           "with\nthe content, provided by this handle.")),
                  stored_graph)

        # test description
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This is a handle description\n"
                           "with multiple lines.\n")),
                  handle.meta)
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This is a handle description\n"
                           "with multiple lines.\n")),
                  stored_graph)

        # authors:
        author_ben = URIRef("mailto:benjaminpoldrack@gmail.com")
        author_just = URIRef("mailto:justanemail@address.tl")
        author_digital = URIRef("https://www.myfancypage.com/digital")
        author_1 = URIRef("file://" + getpwd() + "/#author1")
        # Note: author_1 was:
        # URIRef("file://" + opj(hpath, HANDLE_META_DIR, REPO_STD_META_FILE)
        #        + "#author1")
        # TODO: To be reconsidered when parsing issue regarding empty
        # prefix is solved.
        author_list = {author_ben, author_just, author_digital, author_1}

        eq_(author_list, set(handle.meta.objects(subject=DLNS.this,
                                                 predicate=PAV.createdBy)))
        eq_(author_list, set(stored_graph.objects(subject=DLNS.this,
                                                  predicate=PAV.createdBy)))
        for author in author_list:
            assert_in((author, RDF.type, PROV.Person), handle.meta)
            assert_in((author, RDF.type, PROV.Person), stored_graph)

        assert_in((author_ben,
                   FOAF.name,
                   Literal("Benjamin Poldrack")), handle.meta)
        assert_in((author_ben,
                   FOAF.name,
                   Literal("Benjamin Poldrack")), stored_graph)
        assert_in((author_1,
                   FOAF.name,
                   Literal("someone else")), handle.meta)
        assert_in((author_1,
                   FOAF.name,
                   Literal("someone else")), stored_graph)
        assert_in((author_digital,
                   FOAF.name,
                   Literal("digital native")),
                  handle.meta)
        assert_in((author_digital,
                   FOAF.name,
                   Literal("digital native")),
                  stored_graph)


@assert_cwd_unchanged
@with_testrepos('meta_pt_annex_handle', flavors=['clone'])
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_import_meta_collection_handle(hurl, hpath, cpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        handle = install_handle(hurl, hpath)
        create_collection(cpath)
        add_handle(hpath, cpath)

        current_dir = getpwd()
        chpwd(cpath)

        collection = import_metadata(format="plain-text", path=hpath,
                                     handle=handle.name)
        chpwd(current_dir)

        assert_is_instance(collection, Collection)

        # test the metadata in returned Handle instance as well as the
        # metadata, that is actually stored in the repository:
        stored_graph = Graph().parse(
            opj(cpath, handle.name, REPO_STD_META_FILE), format="turtle")
        handle_graph = collection[handle.name].meta

        # test handle URI:
        handle_uri = handle_graph.value(predicate=RDF.type,
                                        object=DLNS.Handle)
        eq_(handle_uri, URIRef("file://" + hpath))
        assert_in((handle_uri, RDF.type, DLNS.Handle), stored_graph)

        # test license:
        assert_in((handle_uri, DCTERMS.license,
                   Literal("A license, allowing for several things to do "
                           "with\nthe content, provided by this handle.")),

                  handle_graph)
        assert_in((handle_uri, DCTERMS.license,
                   Literal("A license, allowing for several things to do "
                           "with\nthe content, provided by this handle.")),
                  stored_graph)

        # test description
        assert_in((handle_uri, DCTERMS.description,
                   Literal("This is a handle description\n"
                           "with multiple lines.\n")),
                  handle_graph)
        assert_in((handle_uri, DCTERMS.description,
                   Literal("This is a handle description\n"
                           "with multiple lines.\n")),
                  stored_graph)

        # authors:
        author_list = {URIRef("mailto:benjaminpoldrack@gmail.com"),
                       URIRef("mailto:justanemail@address.tl"),
                       URIRef("https://www.myfancypage.com/digital")}

        #               URIRef("file://" + opj(cpath, handle.name,
        #                                      REPO_STD_META_FILE)
        #                      + "/#author1")}
        # TODO: check!
        # Note: See test_import_meta_handle!
        #
        # Currently the prefix (EMP) expands differently in both graphs.
        # Why is this?
        # eq_(author_list, set(handle_graph.objects(subject=handle_uri,
        #                                           predicate=PAV.createdBy)))

        # eq_(author_list, set(stored_graph.objects(subject=handle_uri,
        #                                           predicate=PAV.createdBy)))

        for author in author_list:
            assert_in((author, RDF.type, PROV.Person), handle_graph)
            assert_in((author, RDF.type, PROV.Person), stored_graph)

        assert_in((URIRef("mailto:benjaminpoldrack@gmail.com"),
                   FOAF.name,
                   Literal("Benjamin Poldrack")), handle_graph)
        assert_in((URIRef("mailto:benjaminpoldrack@gmail.com"),
                   FOAF.name,
                   Literal("Benjamin Poldrack")), stored_graph)
        # TODO: See above.
        # assert_in((URIRef("file://" + opj(hpath, HANDLE_META_DIR,
        #                                   REPO_STD_META_FILE)
        #                   + "#author1"),
        #            FOAF.name,
        #            Literal("someone else")), handle_graph)
        # assert_in((URIRef("file://" + opj(hpath, HANDLE_META_DIR,
        #                                   REPO_STD_META_FILE)
        #                   + "#author1"),
        #            FOAF.name,
        #            Literal("someone else")), stored_graph)
        assert_in((URIRef("https://www.myfancypage.com/digital"),
                   FOAF.name,
                   Literal("digital native")),
                  handle_graph)
        assert_in((URIRef("https://www.myfancypage.com/digital"),
                   FOAF.name,
                   Literal("digital native")),
                  stored_graph)