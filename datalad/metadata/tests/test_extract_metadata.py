# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata extraction"""

from os.path import dirname
from os.path import join as opj
from shutil import copy

from datalad.api import extract_metadata
from datalad.coreapi import Dataset
from datalad.tests.utils_pytest import (
    assert_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    known_failure_githubci_win,
    skip_if_no_module,
    with_tempfile,
)
from datalad.utils import chpwd

testpath = opj(dirname(dirname(dirname(__file__))), 'metadata', 'tests', 'data', 'xmp.pdf')


@with_tempfile(mkdir=True)
def test_error(path=None):
    # go into virgin dir to avoid detection of any dataset
    with chpwd(path):
        assert_raises(ValueError, extract_metadata, types=['bogus__'], files=[testpath])


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_ds_extraction(path=None):
    skip_if_no_module('libxmp')

    ds = Dataset(path).create()
    copy(testpath, path)
    ds.save()
    assert_repo_status(ds.path)

    res = extract_metadata(
        types=['xmp'],
        dataset=ds,
        # artificially disable extraction from any file in the dataset
        files=[])
    assert_result_count(
        res, 1,
        type='dataset', status='ok', action='metadata', path=path, refds=ds.path)
    assert_in('xmp', res[0]['metadata'])

    # now the more useful case: getting everything for xmp from a dataset
    res = extract_metadata(
        types=['xmp'],
        dataset=ds)
    assert_result_count(res, 2)
    assert_result_count(
        res, 1,
        type='dataset', status='ok', action='metadata', path=path, refds=ds.path)
    assert_result_count(
        res, 1,
        type='file', status='ok', action='metadata', path=opj(path, 'xmp.pdf'),
        parentds=ds.path)
    for r in res:
        assert_in('xmp', r['metadata'])


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_file_extraction(path=None):
    skip_if_no_module('libxmp')

    # go into virgin dir to avoid detection of any dataset
    with chpwd(path):
        res = extract_metadata(
            types=['xmp'],
            files=[testpath])
        assert_result_count(res, 1, type='file', status='ok', action='metadata', path=testpath)
        assert_in('xmp', res[0]['metadata'])
