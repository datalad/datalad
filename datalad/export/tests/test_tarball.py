# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test tarball exporter"""

from datalad.api import Dataset
from datalad.api import export
from nose.tools import assert_true, assert_equal, assert_raises
from datalad.tests.utils import with_tree, with_tempfile
from datalad.utils import chpwd
import os
from os.path import join as opj


_dataset_template = {
    'ds': {
        'file_up': 'some_content',
        'dir': {
            'file1_down': 'one',
            'file2_down': 'two'}}}


@with_tree(_dataset_template)
def test_failure(path):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    # unknown exporter
    assert_raises(ValueError, ds.export, 'nah')
    # non-existing dataset
    assert_raises(ValueError, export, 'tarball', Dataset('nowhere'))


@with_tree(_dataset_template)
def test_tarball(path):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    with chpwd(path):
        ds.export('tarball')
    assert_true(os.path.exists(opj(path, 'datalad_{}.tar.gz'.format(ds.id))))
    ds.export('tarball', output=opj(path, 'myexport'))
    assert_true(os.path.exists(opj(path, 'myexport.tar.gz'.format(ds.id))))
