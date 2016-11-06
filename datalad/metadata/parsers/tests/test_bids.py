# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS meta data parser """

from os.path import join as opj
from simplejson import dumps
from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.metadata.parsers.bids import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal
from datalad.tests.utils import with_tree, with_tempfile


@with_tree(tree={'dataset_description.json': '{}'})
def test_has_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_true(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(),
                 [opj(path, 'dataset_description.json')])


@with_tempfile(mkdir=True)
def test_has_no_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(), [])


@with_tree(tree={
    'dataset_description.json': """
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
""",
    'sub-16': {'anat': {'sub-16_T1w.nii.gz': "empty"}},
    'sub-34': {'anat': {'sub-16_T2w.nii.gz': "empty2"}}})
def test_get_metadata(path):

    ds = Dataset(path).create(force=True)
    ds.save(auto_add_changes=True)
    meta = MetadataParser(ds).get_metadata('ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
[
  {
    "@context": "http://schema.datalad.org/",
    "@id": "ID",
    "Author": [
      "Mike One",
      "Anna Two"
    ],
    "Citation": [
      "http://studyforrest.org"
    ],
    "Description": "Some description",
    "Keywords": [
      "T1-weighted MRI 3D image",
      "T2-weighted MRI 3D image"
    ],
    "License": "PDDL",
    "Name": "studyforrest_phase2",
    "conformsTo": [
      "http://docs.datalad.org/metadata.html#v0-2",
      "http://bids.neuroimaging.io/bids_spec1.0.0-rc3.pdf"
    ],
    "describedby": {
      "@id": "%s"
    },
    "fundedBy": "We got money from collecting plastic bottles",
    "hasParts": [
      {
        "@id": "MD5E-s5--a2e4822a98337283e39f7b60acf85ec9.nii.gz"
      },
      {
        "@id": "MD5E-s6--085724c672c3bc054d1c266613d17803.nii.gz"
      }
    ]
  },
  {
    "@context": "http://schema.datalad.org/",
    "@id": "MD5E-s5--a2e4822a98337283e39f7b60acf85ec9.nii.gz",
    "ShortDescription": "T1-weighted MRI 3D image",
    "conformsTo": "http://docs.datalad.org/metadata.html#v0-2",
    "contentType": {
      "@id": "neurolex:nlx_156813"
    },
    "describedby": {
      "@id": "%s"
    }
  },
  {
    "@context": "http://schema.datalad.org/",
    "@id": "MD5E-s6--085724c672c3bc054d1c266613d17803.nii.gz",
    "ShortDescription": "T2-weighted MRI 3D image",
    "conformsTo": "http://docs.datalad.org/metadata.html#v0-2",
    "contentType": {
      "@id": "neurolex:nlx_156812"
    },
    "describedby": {
      "@id": "%s"
    }
  }
]""" % (MetadataParser.get_parser_id(),
        MetadataParser.get_parser_id(),
        MetadataParser.get_parser_id()))
