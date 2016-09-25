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
from nose.tools import assert_true, assert_not_equal, assert_raises, \
    assert_false, assert_equal
from datalad.tests.utils import with_tree
from datalad.utils import chpwd
from datalad.utils import md5sum
import os
import time
from os.path import join as opj
import tarfile


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
    ds.save(auto_add_changes=True)
    with chpwd(path):
        ds.export('tarball')
    default_outname = opj(path, 'datalad_{}.tar.gz'.format(ds.id))
    assert_true(os.path.exists(default_outname))
    custom_outname = opj(path, 'myexport.tar.gz')
    # feed in without extension
    ds.export('tarball', output=custom_outname[:-7])
    assert_true(os.path.exists(custom_outname))
    custom1_md5 = md5sum(custom_outname)
    # encodes the original tarball filename -> different checksum, despit
    # same content
    assert_not_equal(md5sum(default_outname), custom1_md5)
    time.sleep(1.1)
    ds.export('tarball', output=custom_outname)
    # encodes mtime -> different checksum, despit same content and name
    assert_not_equal(md5sum(custom_outname), custom1_md5)
    # check content
    with tarfile.open(default_outname) as tf:
        nfiles = 0
        for ti in tf:
            # any annex links resolved
            assert_false(ti.issym())
            if not '.datalad' in ti.name:
                # ignore any files in .datalad for this test to not be
                # susceptible to changes in how much we generate a meta info
                nfiles += 1
        # we have exactly three files, and expect no content for any directory
        assert_equal(nfiles, 3)
