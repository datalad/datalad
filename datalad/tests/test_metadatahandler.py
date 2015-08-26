# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of Metadata Importers.
"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in, \
    assert_not_in
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import FOAF
from six import iterkeys

from ..support.gitrepo import GitRepo
from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo, CollectionRepoBackend, \
    CollectionRepoHandleBackend
from ..support.metadatahandler import DLNS, RDF, RDFS, DCTERMS, PAV, \
    PlainTextImporter, CustomImporter
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


# testing PlainTextImporter:

def test_PlainTextImporter_constructor():

    # initialize metadata about a handle to be stored within that handle and
    # therefore the resource this is about is "DLNS.this":
    importer = PlainTextImporter('Handle', 'Handle', DLNS.this)
    assert_equal(set(iterkeys(importer._graphs)), {'datalad', 'config'})
    assert_in((DLNS.this, RDF.type, DLNS.Handle), importer._graphs['datalad'])
    assert_in((DLNS.this, RDF.type, DLNS.Handle), importer._graphs['config'])
    assert_equal(len(importer._graphs['datalad']), 1)
    assert_equal(len(importer._graphs['config']), 1)

    # again, now handle metadata in a collection and therefore some known path
    # to the handle
    importer = PlainTextImporter('Collection', 'Handle',
                                 URIRef(get_local_file_url('some/path')))
    assert_equal(set(iterkeys(importer._graphs)), {'datalad', 'config'})
    assert_in((URIRef(get_local_file_url('some/path')), RDF.type, DLNS.Handle),
              importer._graphs['datalad'])
    assert_in((URIRef(get_local_file_url('some/path')), RDF.type, DLNS.Handle),
              importer._graphs['config'])
    assert_equal(len(importer._graphs['datalad']), 1)
    assert_equal(len(importer._graphs['config']), 1)


@with_tree([
    ('AUTHORS', "Benjamin Poldrack <benjaminpoldrack@gmail.com>\n#\n# \n# bla, "
                "bla\n<justanemail@address.tl>\nsomeone else\ndigital native "
                "<https://www.myfancypage.com/digital>"),
    ('LICENSE', "This is a license file\n with several lines."),
    ('README', "Read this to have a clue what the repository is about.")
    ])
def test_PlainTextImporter_import_data(path):

    importer = PlainTextImporter('Collection', 'Handle',
                                 URIRef(get_local_file_url(path)))
    # pass a directory:
    importer.import_data(path)
    assert_equal(set(iterkeys(importer._graphs)), {'datalad', 'config'})

    # check listed authors:
    a_nodes = list(importer._graphs['datalad'].objects(
        subject=URIRef(get_local_file_url(path)),
        predicate=PAV.createdBy))

    assert_equal(len(a_nodes), 4)
    a_names = []
    [a_names.extend(importer._graphs['datalad'].objects(subject=a, predicate=FOAF.name)) for a in a_nodes]
    assert_equal(set(a_names), {Literal('Benjamin Poldrack'),
                                Literal('someone else'),
                                Literal('digital native'),
                                Literal('')})

    assert_equal(importer._graphs['datalad'].value(
                                    subject=URIRef(get_local_file_url(path)),
                                    predicate=DCTERMS.description),
                 Literal("Read this to have a clue what the repository "
                         "is about."))

    assert_equal(importer._graphs['datalad'].value(
                                    subject=URIRef(get_local_file_url(path)),
                                    predicate=DCTERMS.license),
                 Literal("This is a license file\n with several lines."))


def test_PlainTextImporter_store_data():
    raise SkipTest