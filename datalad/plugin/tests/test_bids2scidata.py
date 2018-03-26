# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test BIDS to ISATAB"""

from os.path import join as opj

from datalad.api import Dataset
from datalad.utils import chpwd

from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import with_tree
from datalad.tests.utils import assert_true, assert_not_equal, assert_raises, \
    assert_false, assert_equal
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_in
from datalad.tests.utils import with_tempfile

from datalad.support.exceptions import IncompleteResultsError

from datalad.tests.utils import skip_if_no_module
skip_if_no_module('pandas')


_dummy_template = {
    'ds': {
        'file_up': 'some_content',
        'dir': {
            'file1_down': 'one',
            'file2_down': 'two'}}}

_bids_template = {
    'ds': {
        '.datalad': {
            'config': '''\
[datalad "metadata"]
        nativetype = nifti1
        nativetype = bids
'''},
        'participants.tsv': '''\
participant_id\tgender\tage\thandedness
sub-01\tm\t30\tr
sub-15\tf\t35\tl
''',
        'dataset_description.json': '''\
{
    "Name": "demo_ds",
    "BIDSVersion": "1.0.0",
    "Description": "this is for play",
    "License": "PDDL",
    "Authors": [
        "Betty",
        "Tom"
    ]
}
''',
        'sub-01': {
            'anat': {
                'sub-01_T1w.nii.gz': ''}},
        'sub-15': {
            'func': {
                'sub-15_task-nix_run-1_bold.nii.gz': ''}}}}


@with_tree(_dummy_template)
@with_tempfile(mkdir=True)
def test_noop(path, outdir):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    ds.add('.')
    assert_raises(
        TypeError,
        ds.bids2scidata,
    )
    with chpwd(outdir):  # to not pollute cwd
        assert_raises(
            IncompleteResultsError,
            ds.bids2scidata,
            repo_name="dummy",
            repo_accession='ds1',
            repo_url='http://example.com',
        )


@with_tree(_bids_template)
def test_minimal(path):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    ds.add('.')
    ok_clean_git(ds.path)
    # make sure essential metadata files are annex for this test
    # we won't to drop them later and still do the conversion
    assert_true(ds.repo.is_under_annex(
        ['participants.tsv', 'dataset_description.json']))
    ds.aggregate_metadata()
    ok_clean_git(ds.path)
    # do conversion
    # where output should appear by default
    with chpwd(path):
        res = ds.bids2scidata(
            repo_name="dummy",
            repo_accession='ds1',
            repo_url='http://example.com',
        )
        assert_status('ok', res)
        target_path = res[0]['path']
    # just a few basic sanity tests that info ends up in the right places
    # a proper test should be a full regression test on a real dataset
    # with hand-validated exported metadata

    # investigator info
    invest = open(opj(target_path, 'i_Investigation.txt')).read()
    assert_in('Betty\tTom', invest)
    assert_in('Study Assay File Name\ta_mri_t1w.txt\ta_mri_bold.txt', invest)
    assert_in(
        'Comment[Data Repository]\tdummy\nComment[Data Record Accession]\tds1\nComment[Data Record URI]\thttp://example.com',
        invest)

    # study table
    assert_equal(
        """\
Source Name\tCharacteristics[organism]\tCharacteristics[organism part]\tProtocol REF\tSample Name\tCharacteristics[age at scan]\tCharacteristics[handedness]\tCharacteristics[sex]
01\thomo sapiens\tbrain\tParticipant recruitment\t01\t30\tr\tmale
15\thomo sapiens\tbrain\tParticipant recruitment\t15\t35\tl\tfemale
""",
        open(opj(target_path, 's_study.txt')).read())

    # assay tables
    assert_equal(
        """\
Sample Name\tProtocol REF\tParameter Value[modality]\tAssay Name\tRaw Data File\tComment[Data Repository]\tComment[Data Record Accession]\tComment[Data Record URI]\tFactor Value[task]
15\tMagnetic Resonance Imaging\tbold\tsub-15_task-nix_run-1\tsub-15/func/sub-15_task-nix_run-1_bold.nii.gz\tdummy\tds1\thttp://example.com\tnix
""",
        open(opj(target_path, 'a_mri_bold.txt')).read())

    assert_equal(
        """\
Sample Name\tProtocol REF\tParameter Value[modality]\tAssay Name\tRaw Data File\tComment[Data Repository]\tComment[Data Record Accession]\tComment[Data Record URI]
01\tMagnetic Resonance Imaging\tT1w\tsub-01\tsub-01/anat/sub-01_T1w.nii.gz\tdummy\tds1\thttp://example.com
""",
        open(opj(target_path, 'a_mri_t1w.txt')).read())


# TODO implement a regression test on one of our datasets, once we have
# new aggregated metadata in any of them
