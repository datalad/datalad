# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS metadata extractor """

from simplejson import dumps

from datalad.distribution.dataset import Dataset
from datalad.metadata.extractors.datalad_rfc822 import MetadataExtractor
from datalad.tests.utils_pytest import (
    assert_equal,
    with_tree,
)


@with_tree(tree={'.datalad': {'meta.rfc822': """\
Name: studyforrest_phase2
Version: 1.0.0-rc3
Description: Basic summary
 A text with arbitrary length and content that can span multiple
 .
 paragraphs (this is a new one)
License: CC0-1.0
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
def test_get_metadata(path=None):

    ds = Dataset(path).create(force=True)
    ds.save()
    meta = MetadataExtractor(ds, [])._get_dataset_metadata()
    assert_equal(
        dumps(meta, sort_keys=True, indent=2),
        """\
{
  "citation": "Cool (2016)",
  "conformsto": "http://docs.datalad.org/metadata.html#v0-1",
  "description": "A text with arbitrary length and content that can span multiple\\nparagraphs (this is a new one)",
  "fundedby": "BMBFGQ1411, NSF 1429999",
  "homepage": "http://studyforrest.org",
  "issuetracker": "https://github.com/psychoinformatics-de/studyforrest-data-phase2/issues",
  "license": [
    "CC0-1.0",
    "The person who associated a work with this deed has dedicated the work to the public domain by waiving all of his or her rights to the work worldwide under copyright law, including all related and neighboring rights, to the extent allowed by law.\\nYou can copy, modify, distribute and perform the work, even for commercial purposes, all without asking permission."
  ],
  "maintainer": [
    "Mike One <mike@example.com>",
    "Anna Two <anna@example.com>"
  ],
  "name": "studyforrest_phase2",
  "sameas": "http://dx.doi.org/10.5281/zenodo.48421",
  "shortdescription": "Basic summary",
  "version": "1.0.0-rc3"
}""")
