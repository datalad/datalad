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
from datalad.metadata import get_dataset_identifier, format_ntriples, get_metadata
from datalad.metadata.parsers.bids import has_metadata
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
    assert_equal(get_metadata(ds, guess_type=True), [])


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
def test_get_metadata(path):

    ds = Dataset(path)
    dsid = get_dataset_identifier(ds)
    triples = get_metadata(ds, guess_type=True)
    assert_equal(
        format_ntriples(triples),
        """\
{dsid} <http://xmlns.com/foaf/spec/#term_name> "studyforrest_phase2" .
{dsid} <http://purl.org/dc/terms/license> "PDDL" .
{dsid} <http://xmlns.com/foaf/spec/#term_fundedBy> "We got money from collecting plastic bottles" .
{dsid} <http://purl.org/dc/elements/1.1/description> "Some description" .
{dsid} <http://purl.org/dc/terms/conformsTo> "BIDS 1.0.0-rc3" .
{dsid} <http://purl.org/dc/elements/1.1/contributor> "Mike One" .
{dsid} <http://purl.org/dc/elements/1.1/contributor> "Anna Two" .
{dsid} <http://purl.org/dc/terms/bibliographicCitation> <http://studyforrest.org> .""".format(dsid=dsid))

