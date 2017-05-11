# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test subdataset command"""

import os
from os.path import join as opj
from os.path import relpath

from ..dataset import Dataset
from datalad.api import subdatasets

from nose.tools import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_status


@with_testrepos('.*nested_submodule.*', flavors=['clone'])
def test_get_subdatasets(path):
    ds = Dataset(path)
    eq_(subdatasets(ds, recursive=True, fulfilled=False, result_xfm='relpaths'), [
        'sub dataset1'
    ])
    ds.get('sub dataset1')
    eq_(subdatasets(ds, recursive=True, fulfilled=False, result_xfm='relpaths'), [
        'sub dataset1/sub sub dataset1',
        'sub dataset1/subm 1',
        'sub dataset1/subm 2',
    ])
    # obtain key subdataset, so all leave subdatasets are discoverable
    ds.get(opj('sub dataset1', 'sub sub dataset1'))
    eq_(ds.subdatasets(result_xfm='relpaths'), ['sub dataset1'])
    eq_([(r['parentds'], r['path']) for r in ds.subdatasets()],
        [(path, opj(path, 'sub dataset1'))])
    eq_(subdatasets(ds, recursive=True, result_xfm='relpaths'), [
        'sub dataset1',
        'sub dataset1/sub sub dataset1',
        'sub dataset1/sub sub dataset1/subm 1',
        'sub dataset1/sub sub dataset1/subm 2',
        'sub dataset1/subm 1',
        'sub dataset1/subm 2',
    ])
    # uses slow, flexible query
    eq_(subdatasets(ds, recursive=True, bottomup=True, result_xfm='relpaths'), [
        'sub dataset1/sub sub dataset1/subm 1',
        'sub dataset1/sub sub dataset1/subm 2',
        'sub dataset1/sub sub dataset1',
        'sub dataset1/subm 1',
        'sub dataset1/subm 2',
        'sub dataset1',
    ])
    eq_(subdatasets(ds, recursive=True, fulfilled=True, result_xfm='relpaths'), [
        'sub dataset1',
        'sub dataset1/sub sub dataset1',
    ])
    eq_([(relpath(r['parentds'], start=ds.path), relpath(r['path'], start=ds.path))
         for r in ds.subdatasets(recursive=True)], [
        (os.curdir, 'sub dataset1'),
        ('sub dataset1', 'sub dataset1/sub sub dataset1'),
        ('sub dataset1/sub sub dataset1', 'sub dataset1/sub sub dataset1/subm 1'),
        ('sub dataset1/sub sub dataset1', 'sub dataset1/sub sub dataset1/subm 2'),
        ('sub dataset1', 'sub dataset1/subm 1'),
        ('sub dataset1', 'sub dataset1/subm 2'),
    ])
    # uses slow, flexible query
    eq_(subdatasets(ds, recursive=True, recursion_limit=0),
        [])
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, recursion_limit=1, result_xfm='relpaths'),
        ['sub dataset1'])
    # uses slow, flexible query
    eq_(ds.subdatasets(recursive=True, recursion_limit=2, result_xfm='relpaths'),
        [
        'sub dataset1',
        'sub dataset1/sub sub dataset1',
        'sub dataset1/subm 1',
        'sub dataset1/subm 2',
    ])
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        for prop in ('url', 'state', 'reccommit', 'subds_name'):
            assert_in(prop, r)
