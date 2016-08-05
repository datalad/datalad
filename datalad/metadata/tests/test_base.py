# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test GNU-style meta data parser """

from datalad.api import Dataset
from datalad.metadata import get_metadata_type, get_metadata
from nose.tools import assert_true, assert_equal
from datalad.tests.utils import with_tree, with_tempfile
import os
from os.path import join as opj


@with_tempfile(mkdir=True)
def test_get_metadata_type(path):
    # nothing set, nothing found
    assert_equal(get_metadata_type(Dataset(path)), None)
    os.makedirs(opj(path, '.datalad'))
    # got section, but no setting
    open(opj(path, '.datalad', 'config'), 'w').write('[metadata]\n')
    assert_equal(get_metadata_type(Dataset(path)), None)
    # minimal setting
    open(opj(path, '.datalad', 'config'), 'w+').write('[metadata]\nnativetype = mamboschwambo\n')
    assert_equal(get_metadata_type(Dataset(path)), 'mamboschwambo')


@with_tree(tree={
    'README': 'some description',
    'COPYING': 'some license',
    'AUTHOR': 'some authors'})
def test_guess_metadata(path):
    assert_equal(get_metadata_type(Dataset(path), guess=False), None)
    assert_true(get_metadata_type(Dataset(path), guess=True), 'gnu')


@with_tempfile(mkdir=True)
def test_basic_metadata(path):
    ds = Dataset(path)
    assert_equal(get_metadata(ds), [])
    ds.create()
    print(get_metadata(ds))
