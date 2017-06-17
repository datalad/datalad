# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test meta data manipulation"""


from os.path import join as opj

from datalad.api import metadata
from datalad.distribution.dataset import Dataset
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from datalad.utils import chpwd

from datalad.tests.utils import create_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git


@with_tempfile(mkdir=True)
def test_basic(path):
    with chpwd(path):
        # no repo -> error
        assert_status('error', metadata(on_failure='ignore'))
        # some repo, no error on query of pwd
        GitRepo('.', create=True)
        eq_([], metadata())
        # impossible when making explicit query
        assert_status('impossible', metadata('.', on_failure='ignore'))
        # fine with annex
        AnnexRepo('.', create=True)
        eq_([], metadata())
        eq_([], metadata('.'))

    # create playing field
    create_tree(path, {'somefile': 'content', 'dir': {'deepfile': 'othercontent'}})
    ds = Dataset(path)
    ds.add('.')
    ok_clean_git(path)
    # full query -> 2 files
    res = ds.metadata()
    assert_result_count(res, 2)
    assert_result_count(res, 2, type='file', metadata={})

    #
    # tags: just a special case of a metadata key without a value
    #
    # tag one file
    target_file = opj('dir', 'deepfile')
    # needs a sequence or dict
    assert_raises(ValueError, ds.metadata, target_file, add='mytag')
    # like this
    res = ds.metadata(target_file, add=['mytag'])
    assert_result_count(res, 1)
    assert_result_count(
        res, 1, type='file', path=opj(ds.path, target_file),
        metadata={'tag': ['mytag']})
    # now init tag for all files that don't have one yet
    res = ds.metadata(init=['rest'])
    assert_result_count(res, 2)
    # from before
    assert_result_count(
        res, 1, type='file', path=opj(ds.path, target_file),
        metadata={'tag': ['mytag']})
    # and the other one
    assert_result_count(
        res, 1, type='file', path=opj(ds.path, 'somefile'),
        metadata={'tag': ['rest']})
    # add two more different tags
    res = ds.metadata(add=['other1', 'other2', 'other3'])
    assert_result_count(res, 2)
    for r in res:
        assert_in('other1', r['metadata']['tag'])
        assert_in('other2', r['metadata']['tag'])
        assert_in('other3', r['metadata']['tag'])

    # now remove two specifics tag from all files that exists in all files
    res = ds.metadata(remove=['other1', 'other3'])
    assert_result_count(res, 2)
    for r in res:
        assert_not_in('other1', r['metadata']['tag'])
        assert_in('other2', r['metadata']['tag'])

    # and now one that only exists in one file
    res = ds.metadata(remove=['rest'])
    # we still get 2 results, because we still touch all files
    assert_result_count(res, 2)
    # however there is no modification to files that don't have the tag
    assert_result_count(
        res, 1, type='file', path=opj(ds.path, 'somefile'),
        metadata={'tag': ['other2']})
    assert_result_count(
        res, 1, type='file', path=opj(ds.path, target_file),
        metadata={'tag': ['mytag', 'other2']})

    # and finally kill the tags
    res = ds.metadata(target_file, reset=['tag'])
    assert_result_count(res, 1)
    assert_result_count(res, 1, type='file', metadata={},
                        path=opj(ds.path, target_file))
    # no change to the other one
    assert_result_count(
        ds.metadata('somefile'), 1,
        type='file', path=opj(ds.path, 'somefile'),
        metadata={'tag': ['other2']})
    # kill all tags everywhere
    res = ds.metadata(reset=['tag'])
    assert_result_count(res, 2)
    assert_result_count(res, 2, type='file', metadata={})

    #
    # key: value mapping
    #
    res = ds.metadata('somefile', add=dict(new=('v1', 'v2')))
    assert_result_count(res, 1, metadata={'new': ['v1', 'v2']})
    # same as this, which exits to support the way things come
    # in from the cmdline
    res = ds.metadata(target_file, add=[['new', 'v1', 'v2']])
    assert_result_count(res, 1, metadata={'new': ['v1', 'v2']})
    # other file got the exact same metadata now
    assert_result_count(
        ds.metadata(), 2, metadata={'new': ['v1', 'v2']})
    # reset with just a key removes the entire mapping
    res = ds.metadata(target_file, reset=['new'])
    assert_result_count(res, 1, metadata={})
    # reset with a mapping, overrides the old one
    res = ds.metadata('somefile', reset=dict(new='george', more='yeah'))
    assert_result_count(res, 1, metadata=dict(new=['george'], more=['yeah']))
    # remove single value from mapping, last value to go removes the key
    res = ds.metadata('somefile', remove=dict(more='yeah'))
    assert_result_count(res, 1, metadata=dict(new=['george']))
    # and finally init keys
    res = ds.metadata(init=dict(new=['two', 'three'], super='fresh'))
    assert_result_count(res, 2)
    assert_result_count(
        res, 1, path=opj(ds.path, target_file),
        # order of values is not maintained
        metadata=dict(new=['three', 'two'], super=['fresh']))
    assert_result_count(
        res, 1, path=opj(ds.path, 'somefile'),
        # order of values is not maintained
        metadata=dict(new=['george'], super=['fresh']))

