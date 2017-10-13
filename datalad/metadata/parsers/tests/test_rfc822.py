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
from datalad.metadata.parsers.datalad_rfc822 import MetadataParser
from nose.tools import assert_true, assert_false, assert_equal
from datalad.tests.utils import with_tree, with_tempfile


@with_tree(tree={'.datalad': {'meta.rfc822': ''}})
def test_has_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_true(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(),
                 [opj(path, '.datalad', 'meta.rfc822')])


@with_tempfile(mkdir=True)
def test_has_no_metadata(path):
    ds = Dataset(path)
    p = MetadataParser(ds)
    assert_false(p.has_metadata())
    assert_equal(p.get_core_metadata_filenames(), [])


@with_tree(tree={'.datalad': {'meta.rfc822': """\
Name: studyforrest_phase2
Version: 1.0.0-rc3
Description: Basic summary
 A text with arbitrary length and content that can span multiple
 .
 paragraphs (this is a new one)
License: CC0
 The person who associated a work with this deed has dedicated the work to the
 public domain by waiving all of his or her rights to the work worldwide under
 copyright law, including all related and neighboring rights, to the extent
 allowed by law.
 .
 You can copy, modify, distribute and perform the work, even for commercial
 purposes, all without asking permission.
Maintainer: Mike One <mike@example.com>,
            Anna Two <anna@example.com>,
Homepage: http://studyforrest.org
Funding: BMBFGQ1411, NSF 1429999
Issue-Tracker: https://github.com/psychoinformatics-de/studyforrest-data-phase2/issues
Cite-As: Cool (2016)
DOI: 10.5281/zenodo.48421

"""}})
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
  "bug-database": "https://github.com/psychoinformatics-de/studyforrest-data-phase2/issues",
  "citation": "Cool (2016)",
  "dcterms:conformsTo": "http://docs.datalad.org/metadata.html#v0-1",
  "description": "A text with arbitrary length and content that can span multiple\\nparagraphs (this is a new one)",
  "doap:Version": "1.0.0-rc3",
  "doap:homepage": "http://studyforrest.org",
  "doap:maintainer": [
    "Mike One <mike@example.com>",
    "Anna Two <anna@example.com>"
  ],
  "doap:shortdesc": "Basic summary",
  "foaf:fundedBy": "BMBFGQ1411, NSF 1429999",
  "license": [
    "CC0",
    "The person who associated a work with this deed has dedicated the work to the public domain by waiving all of his or her rights to the work worldwide under copyright law, including all related and neighboring rights, to the extent allowed by law.\\nYou can copy, modify, distribute and perform the work, even for commercial purposes, all without asking permission."
  ],
  "name": "studyforrest_phase2",
  "sameAs": "http://dx.doi.org/10.5281/zenodo.48421"
}""")
