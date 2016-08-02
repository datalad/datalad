# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS meta data parser """

from datalad.distribution.dataset import Dataset
from datalad.metadata import get_dataset_identifier, format_ntriples
from datalad.metadata.parsers.bids import has_metadata, get_ntriples
from nose.tools import assert_true, assert_false, assert_raises, assert_equal
from datalad.tests.utils import with_tree, with_tempfile


@with_tree(tree={'dataset_description.json': '{}'})
def test_has_metadata(path):
    ds = Dataset(path)
    assert_true(has_metadata(ds))


@with_tempfile(mkdir=True)
def test_has_no_metadata(path):
    ds = Dataset(path)
    assert_false(has_metadata(ds))
    assert_raises(ValueError, get_ntriples, ds)


@with_tree(tree={'dataset_description.json': """
{
    "Name": "studyforrest_phase2",
    "BIDSVersion": "1.0.0-rc3",
    "Description": "Some description",
    "License": "PDDL",
    "Authors": [
        "Mike One",
        "Anna Two"
    ],
    "Funding": "We got money from collecting plastic bottles",
    "ReferencesAndLinks": [
        "http://studyforrest.org"
    ]
}
"""})
def test_get_ntriples(path):

    ds = Dataset(path)
    triples = get_ntriples(ds)
    assert_equal(
        format_ntriples(triples),
        """\
_:dsid_placeholder <http://purl.org/dc/terms/type> <http://purl.org/dc/dcmitype/Dataset> .
_:dsid_placeholder <http://xmlns.com/foaf/spec/#term_name> "studyforrest_phase2" .
_:dsid_placeholder <http://purl.org/dc/terms/license> "PDDL" .
_:dsid_placeholder <http://xmlns.com/foaf/spec/#term_fundedBy> "We got money from collecting plastic bottles" .
_:dsid_placeholder <http://purl.org/dc/elements/1.1/description> "Some description" .
_:dsid_placeholder <http://purl.org/dc/terms/conformsTo> "BIDS 1.0.0-rc3" .
_:dsid_placeholder <http://purl.org/dc/elements/1.1/contributor> "Mike One" .
_:dsid_placeholder <http://purl.org/dc/elements/1.1/contributor> "Anna Two" .
_:dsid_placeholder <http://purl.org/dc/terms/bibliographicCitation> <http://studyforrest.org> .""")

