# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for describe command

"""

__docformat__ = 'restructuredtext'

from os.path import basename, exists, isdir, join as opj

from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...api import describe, create_handle, create_collection
from ...utils import swallow_logs, getpwd, chpwd
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...support.metadatahandler import DLNS, PAV, DCTERMS, URIRef, RDF, FOAF, \
    PROV, Literal, Graph
from ...support.handle import Handle
from ...support.collection import Collection
from ...consts import REPO_STD_META_FILE, HANDLE_META_DIR


@assert_cwd_unchanged
@with_tempfile
@with_tempfile(mkdir=True)
def test_describe_handle_simple(path, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        handle_before = create_handle(path, "TestDescribeHandle")
        # no author entry:
        eq_(len(list(handle_before.meta.objects(subject=DLNS.this,
                                                predicate=PAV.createdBy))),
            0)
        # no license:
        eq_(len(list(handle_before.meta.objects(subject=DLNS.this,
                                                predicate=DCTERMS.license))),
            0)
        # no description:
        eq_(len(list(
            handle_before.meta.objects(subject=DLNS.this,
                                       predicate=DCTERMS.description))),
            0)

        # describe currently has to run within the repository to describe:
        current_dir = getpwd()
        chpwd(path)
        handle_after = describe(author="Some author",
                                author_email="some.author@example.com",
                                author_page="http://example.com/someauthor",
                                license="A license text.",
                                description="This a description.")
        chpwd(current_dir)

        assert_is_instance(handle_after, Handle)

        # test the metadata in returned Handle instance as well as the
        # metadata, that is actually stored in the repository:
        stored_graph = Graph().parse(
            opj(path, HANDLE_META_DIR, REPO_STD_META_FILE), format="turtle")

        # test author node:
        a_node = handle_after.meta.value(subject=DLNS.this,
                                         predicate=PAV.createdBy)
        eq_(a_node, stored_graph.value(subject=DLNS.this,
                                       predicate=PAV.createdBy))
        eq_(a_node, URIRef("mailto:some.author@example.com"))
        assert_in((a_node, RDF.type, PROV.Person), handle_after.meta)
        assert_in((a_node, RDF.type, PROV.Person), stored_graph)
        assert_in((a_node, RDF.type, FOAF.Person), handle_after.meta)
        assert_in((a_node, RDF.type, FOAF.Person), stored_graph)
        assert_in((a_node, FOAF.mbox,
                   URIRef("mailto:some.author@example.com")),
                  handle_after.meta)
        assert_in((a_node, FOAF.mbox,
                   URIRef("mailto:some.author@example.com")),
                  stored_graph)
        assert_in((a_node, FOAF.homepage,
                   URIRef("http://example.com/someauthor")),
                  handle_after.meta)
        assert_in((a_node, FOAF.homepage,
                   URIRef("http://example.com/someauthor")),
                  stored_graph)
        assert_in((a_node, FOAF.name, Literal("Some author")),
                  handle_after.meta)
        assert_in((a_node, FOAF.name, Literal("Some author")),
                  stored_graph)

        # test license:
        assert_in((DLNS.this, DCTERMS.license, Literal("A license text.")),
                  handle_after.meta)
        assert_in((DLNS.this, DCTERMS.license, Literal("A license text.")),
                  stored_graph)

        # test description:
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This a description.")),
                  handle_after.meta)
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This a description.")),
                  stored_graph)


@assert_cwd_unchanged
@with_tempfile
@with_tempfile(mkdir=True)
def test_describe_collection_simple(path, lcpath):
    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        collection_before = create_collection(path, "TestDescribeCollection")
        # no author entry:
        eq_(len(list(
            collection_before.meta.objects(subject=DLNS.this,
                                           predicate=PAV.createdBy))),
            0)
        # no license:
        eq_(len(list(
            collection_before.meta.objects(subject=DLNS.this,
                                           predicate=DCTERMS.license))),
            0)
        # no description:
        eq_(len(list(
            collection_before.meta.objects(subject=DLNS.this,
                                           predicate=DCTERMS.description))),
            0)

        # describe currently has to run within the repository to describe:
        current_dir = getpwd()
        chpwd(path)
        collection_after = describe(author="Some author",
                                    author_email="some.author@example.com",
                                    author_page="http://example.com/someauthor",
                                    license="A license text.",
                                    description="This a description.")
        chpwd(current_dir)

        assert_is_instance(collection_after, Collection)

        # test the metadata in returned Handle instance as well as the
        # metadata, that is actually stored in the repository:
        stored_graph = Graph().parse(opj(path, REPO_STD_META_FILE),
                                     format="turtle")

        # test author node:
        a_node = collection_after.meta.value(subject=DLNS.this,
                                             predicate=PAV.createdBy)
        eq_(a_node, stored_graph.value(subject=DLNS.this,
                                       predicate=PAV.createdBy))
        eq_(a_node, URIRef("mailto:some.author@example.com"))
        assert_in((a_node, RDF.type, PROV.Person), collection_after.meta)
        assert_in((a_node, RDF.type, PROV.Person), stored_graph)
        assert_in((a_node, RDF.type, FOAF.Person), collection_after.meta)
        assert_in((a_node, RDF.type, FOAF.Person), stored_graph)
        assert_in((a_node, FOAF.mbox,
                   URIRef("mailto:some.author@example.com")),
                  collection_after.meta)
        assert_in((a_node, FOAF.mbox,
                   URIRef("mailto:some.author@example.com")),
                  stored_graph)
        assert_in((a_node, FOAF.homepage,
                   URIRef("http://example.com/someauthor")),
                  collection_after.meta)
        assert_in((a_node, FOAF.homepage,
                   URIRef("http://example.com/someauthor")),
                  stored_graph)
        assert_in((a_node, FOAF.name, Literal("Some author")),
                  collection_after.meta)
        assert_in((a_node, FOAF.name, Literal("Some author")),
                  stored_graph)

        # test license:
        assert_in((DLNS.this, DCTERMS.license, Literal("A license text.")),
                  collection_after.meta)
        assert_in((DLNS.this, DCTERMS.license, Literal("A license text.")),
                  stored_graph)

        # test description:
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This a description.")),
                  collection_after.meta)
        assert_in((DLNS.this, DCTERMS.description,
                   Literal("This a description.")),
                  stored_graph)


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_describe_outside_repo(path):

    current_dir = getpwd()
    chpwd(path)
    with assert_raises(RuntimeError) as cm:
        describe(author="Some author")
    eq_(str(cm.exception), "No datalad repository found in %s" % path)
    chpwd(current_dir)


# TODO: sub-entities
# TODO: different combinations of properties.