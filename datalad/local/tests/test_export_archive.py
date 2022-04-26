# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test archive exporter"""

import os
import tarfile
import time
from os.path import isabs
from os.path import join as opj

from datalad.api import (
    Dataset,
    export_archive,
)
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_not_equal,
    assert_raises,
    assert_result_count,
    assert_status,
    assert_true,
    ok_startswith,
    with_tree,
)
from datalad.utils import (
    chpwd,
    md5sum,
)

_dataset_template = {
    'ds': {
        'file_up': 'some_content',
        'dir': {
            'file1_down': 'one',
            'file2_down': 'two'}}}


@with_tree(_dataset_template)
def test_failure(path=None):
    # non-existing dataset
    with assert_raises(ValueError):
        export_archive(dataset=Dataset('nowhere'))


@with_tree(_dataset_template)
def test_archive(path=None):
    ds = Dataset(opj(path, 'ds')).create(force=True)
    ds.save()
    committed_date = ds.repo.get_commit_date()
    default_outname = opj(path, 'datalad_{}.tar.gz'.format(ds.id))
    with chpwd(path):
        res = list(ds.export_archive())
        assert_status('ok', res)
        assert_result_count(res, 1)
        assert(isabs(res[0]['path']))
    assert_true(os.path.exists(default_outname))
    custom_outname = opj(path, 'myexport.tar.gz')
    # feed in without extension
    ds.export_archive(filename=custom_outname[:-7])
    assert_true(os.path.exists(custom_outname))
    custom1_md5 = md5sum(custom_outname)
    # encodes the original archive filename -> different checksum, despit
    # same content
    assert_not_equal(md5sum(default_outname), custom1_md5)
    # should really sleep so if they stop using time.time - we know
    time.sleep(1.1)
    ds.export_archive(filename=custom_outname)
    # should not encode mtime, so should be identical
    assert_equal(md5sum(custom_outname), custom1_md5)

    def check_contents(outname, prefix):
        with tarfile.open(outname) as tf:
            nfiles = 0
            for ti in tf:
                # any annex links resolved
                assert_false(ti.issym())
                ok_startswith(ti.name, prefix + '/')
                assert_equal(ti.mtime, committed_date)
                if '.datalad' not in ti.name:
                    # ignore any files in .datalad for this test to not be
                    # susceptible to changes in how much we generate a meta info
                    nfiles += 1
            # we have exactly four files (includes .gitattributes for default
            # MD5E backend), and expect no content for any directory
            assert_equal(nfiles, 4)
    check_contents(default_outname, 'datalad_%s' % ds.id)
    check_contents(custom_outname, 'myexport')

    # now loose some content
    ds.drop('file_up', reckless='kill')
    assert_raises(IOError, ds.export_archive, filename=opj(path, 'my'))
    ds.export_archive(filename=opj(path, 'partial'), missing_content='ignore')
    assert_true(os.path.exists(opj(path, 'partial.tar.gz')))


@with_tree(_dataset_template)
def test_zip_archive(path=None):
    ds = Dataset(opj(path, 'ds')).create(force=True, annex=False)
    ds.save()
    with chpwd(path):
        ds.export_archive(filename='my', archivetype='zip')
        assert_true(os.path.exists('my.zip'))
        custom1_md5 = md5sum('my.zip')
        time.sleep(1.1)
        ds.export_archive(filename='my', archivetype='zip')
        assert_equal(md5sum('my.zip'), custom1_md5)

    # should be able to export without us cd'ing to that ds directory
    ds.export_archive(filename=ds.path, archivetype='zip')
    default_name = 'datalad_{}.zip'.format(ds.id)
    assert_true(os.path.exists(os.path.join(ds.path, default_name)))
