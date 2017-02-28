# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
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
    meta = MetadataParser(ds).get_metadata('ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
{
  "@context": {
    "@vocab": "http://schema.org/",
    "doap": "http://usefulinc.com/ns/doap#"
  },
  "@id": "ID",
  "author": [
    "Mike One",
    "Anna Two"
  ],
  "citation": [
    "http://studyforrest.org"
  ],
  "dcterms:conformsTo": [
    "http://docs.datalad.org/metadata.html#v0-1",
    "http://bids.neuroimaging.io/bids_spec1.0.0-rc3.pdf"
  ],
  "description": "Some description",
  "foaf:fundedBy": "We got money from collecting plastic bottles",
  "license": "PDDL",
  "name": "studyforrest_phase2"
}""")


@with_tree(tree={'dataset_description.json': """
{
    "Name": "test",
    "Description": "Some description"
}
""",
                 'README': """
A very detailed
description
"""})
def test_get_metadata_with_description_and_README(path):

    ds = Dataset(path)
    meta = MetadataParser(ds).get_metadata('ID')
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
{
  "@context": {
    "@vocab": "http://schema.org/",
    "doap": "http://usefulinc.com/ns/doap#"
  },
  "@id": "ID",
  "dcterms:conformsTo": [
    "http://docs.datalad.org/metadata.html#v0-1",
    "http://bids.neuroimaging.io"
  ],
  "description": "Some description",
  "name": "test"
}""")


# actually does not demonstrate problem with unicode encountered in
# https://github.com/datalad/datalad/issues/1138
@with_tree(tree={'dataset_description.json': """
{
    "Name": "test"
}
""",
                 'README': u"""
A very detailed
description с юникодом
"""})
def test_get_metadata_with_README(path):
    ds = Dataset(path)
    meta = MetadataParser(ds).get_metadata('ID')
    dump = dumps(meta, sort_keys=True, indent=2, ensure_ascii=False)
    assert_equal(
        dump,
        u"""\
{
  "@context": {
    "@vocab": "http://schema.org/",
    "doap": "http://usefulinc.com/ns/doap#"
  },
  "@id": "ID",
  "dcterms:conformsTo": [
    "http://docs.datalad.org/metadata.html#v0-1",
    "http://bids.neuroimaging.io"
  ],
  "description": "A very detailed\\ndescription с юникодом",
  "name": "test"
}""")
