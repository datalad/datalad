# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata extraction"""

from os.path import join as opj
from os.path import dirname

from shutil import copy

from datalad.coreapi import Dataset
from datalad.api import extract_metadata
from datalad.utils import chpwd

from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_in

from datalad.support.exceptions import IncompleteResultsError


testpath = opj(dirname(dirname(dirname(__file__))), 'metadata', 'tests', 'data', 'xmp.pdf')


@with_tempfile(mkdir=True)
def test_error(path):
    # go into virgin dir to avoid detection of any dataset
    with chpwd(path):
        assert_raises(ValueError, extract_metadata, types=['bogus__'], files=[testpath])


@with_tempfile(mkdir=True)
def test_ds_extraction(path):
    from datalad.tests.utils import SkipTest
    try:
        import libxmp
    except ImportError:
        raise SkipTest

    ds = Dataset(path).create()
    copy(testpath, path)
    ds.add('.')
    ok_clean_git(ds.path)

    res = extract_metadata(
        types=['xmp'],
        dataset=ds,
        # artificially disable extraction from any file in the dataset
        files=[])
    assert_result_count(
        res, 1,
        type='dataset', status='ok', action='metadata', path=path, refds=ds.path)
    assert_in('xmp', res[0]['metadata'])

    # now the more useful case: getting everthing for xmp from a dataset
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


@with_tempfile(mkdir=True)
def test_file_extraction(path):
    from datalad.tests.utils import SkipTest
    try:
        import libxmp
    except ImportError:
        raise SkipTest

    # go into virgin dir to avoid detection of any dataset
    with chpwd(path):
        res = extract_metadata(
            types=['xmp'],
            files=[testpath])
        assert_result_count(res, 1, type='file', status='ok', action='metadata', path=testpath)
        assert_in('xmp', res[0]['metadata'])
