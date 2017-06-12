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
from os.path import pardir

from ..dataset import Dataset
from datalad.api import subdatasets

from nose.tools import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
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
        for prop in ('gitmodule_url', 'state', 'revision', 'gitmodule_name'):
            assert_in(prop, r)
        # random property is unknown
        assert_not_in('mike', r)

    # now add info to all datasets
    res = ds.subdatasets(
        recursive=True,
        set_property=[('mike', 'slow'),
                      ('expansion', '<{refds_relname}>')])
    assert_status('ok', res)
    for r in res:
        eq_(r['gitmodule_mike'], 'slow')
        eq_(r['gitmodule_expansion'], relpath(r['path'], r['refds']).replace(os.sep, '-'))
    # plain query again to see if it got into the files
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        eq_(r['gitmodule_mike'], 'slow')
        eq_(r['gitmodule_expansion'], relpath(r['path'], r['refds']).replace(os.sep, '-'))

    # and remove again
    res = ds.subdatasets(recursive=True, delete_property=('mike', 'something'))
    assert_status('ok', res)
    for r in res:
        for prop in ('gitmodule_mike', 'gitmodule_something'):
            assert_not_in(prop, r)
    # and again, because above yields on the fly edit
    res = ds.subdatasets(recursive=True)
    assert_status('ok', res)
    for r in res:
        for prop in ('gitmodule_mike', 'gitmodule_something'):
            assert_not_in(prop, r)

    #
    # test --contains
    #
    target_sub = 'sub dataset1/sub sub dataset1/subm 1'
    # give the closest direct subdataset
    eq_(ds.subdatasets(contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1'])
    # should find the actual subdataset trail
    eq_(ds.subdatasets(recursive=True,
                       contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1',
         'sub dataset1/sub sub dataset1',
         'sub dataset1/sub sub dataset1/subm 1'])
    # doesn't affect recursion limit
    eq_(ds.subdatasets(recursive=True, recursion_limit=2,
                       contains=opj(target_sub, 'something_inside'),
                       result_xfm='relpaths'),
        ['sub dataset1',
         'sub dataset1/sub sub dataset1'])
    # for a direct dataset path match, return the matching dataset
    eq_(ds.subdatasets(recursive=True,
                       contains=target_sub,
                       result_xfm='relpaths'),
        ['sub dataset1',
         'sub dataset1/sub sub dataset1',
         'sub dataset1/sub sub dataset1/subm 1'])
    # but it has to be a subdataset, otherwise no match
    eq_(ds.subdatasets(contains=ds.path), [])
    # which is what get_containing_subdataset() does
    eq_(ds.subdatasets(recursive=True,
                       contains=target_sub,
                       result_xfm='paths')[-1],
        ds.get_containing_subdataset(target_sub).path)
    # no error if contains is bullshit
    eq_(ds.subdatasets(recursive=True,
                       contains='errrr_nope',
                       result_xfm='paths'),
        [])
    # TODO maybe at a courtesy bullshit detector some day
    eq_(ds.subdatasets(recursive=True,
                       contains=opj(pardir, 'errrr_nope'),
                       result_xfm='paths'),
        [])

