# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil; coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS metadata parser """

from os.path import join as opj
from simplejson import dumps
from datalad.api import Dataset
from datalad.metadata.parsers.bids import MetadataParser
from nose.tools import assert_equal
from datalad.tests.utils import with_tree
from datalad.tests.utils import assert_in


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
""",
    'participants.tsv': """\
participant_id\tgender\tage\thandedness\thearing_problems_current
sub-01\tm\t30-35\tr\tn
sub-03\tf\t20-25\tr\tn
""",
    'sub-01': {'func': {'sub-01_task-some_bold.nii.gz': ''}}})
def test_get_metadata(path):

    ds = Dataset(path).create(force=True)
    meta = MetadataParser(ds, []).get_metadata(True, False)[0]
    del meta['@context']
    dump = dumps(meta, sort_keys=True, indent=2, ensure_ascii=False)
    assert_equal(
        dump,
        """\
{
  "author": [
    "Mike One",
    "Anna Two"
  ],
  "citation": [
    "http://studyforrest.org"
  ],
  "comment<BIDSVersion>": "1.0.0-rc3",
  "conformsto": "http://bids.neuroimaging.io/bids_spec1.0.0-rc3.pdf",
  "description": "Some description",
  "fundedby": "We got money from collecting plastic bottles",
  "license": "PDDL",
  "name": "studyforrest_phase2"
}""")

    test_fname = opj('sub-01', 'func', 'sub-01_task-some_bold.nii.gz')
    cmeta = list(MetadataParser(
        ds,
        [opj('sub-01', 'func', 'sub-01_task-some_bold.nii.gz')]
    ).get_metadata(False, True)[1])
    assert_equal(len(cmeta), 1)
    assert_equal(cmeta[0][0], test_fname)
    assert_in('comment<handedness>', cmeta[0][1])


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

    ds = Dataset(path).create(force=True)
    meta = MetadataParser(ds, []).get_metadata(True, False)[0]
    del meta['@context']
    dump = dumps(meta, sort_keys=True, indent=2, ensure_ascii=False)
    assert_equal(
        dump,
        """\
{
  "conformsto": "http://bids.neuroimaging.io",
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
    ds = Dataset(path).create(force=True)
    meta = MetadataParser(ds, []).get_metadata(True, False)[0]
    del meta['@context']
    dump = dumps(meta, sort_keys=True, indent=2, ensure_ascii=False)
    assert_equal(
        dump,
        u"""\
{
  "conformsto": "http://bids.neuroimaging.io",
  "description": "A very detailed\\ndescription с юникодом",
  "name": "test"
}""")
