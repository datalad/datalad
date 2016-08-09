# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS meta data parser """

from simplejson import dumps
from datalad.distribution.dataset import Dataset
from datalad.metadata.parsers.bids import has_metadata, get_metadata
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
    assert_raises(ValueError, get_metadata, ds, 'ID')


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
    meta = get_metadata(ds, 'ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
{
  "@context": "http://schema.org/",
  "@id": "ID",
  "author": [
    "Mike One",
    "Anna Two"
  ],
  "citation": [
    "http://studyforrest.org"
  ],
  "dcterms:conformsTo": "BIDS 1.0.0-rc3",
  "description": "Some description",
  "foaf:fundedBy": "We got money from collecting plastic bottles",
  "license": "PDDL",
  "name": "studyforrest_phase2"
}""")
