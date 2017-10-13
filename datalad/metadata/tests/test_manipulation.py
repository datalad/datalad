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


from datalad.tests.utils import known_failure_direct_mode

import os
from os.path import join as opj
from os.path import exists

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
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git


@with_tempfile(mkdir=True)
def test_basic_filemeta(path):
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


@with_tempfile(mkdir=True)
def test_basic_dsmeta(path):
    ds = Dataset(path).create()
    ok_clean_git(path)
    # ensure clean slate
    assert_result_count(ds.metadata(), 0)
    # init
    res = ds.metadata(init=['tag1', 'tag2'], dataset_global=True)
    eq_(res[0]['metadata']['tag'], ['tag1', 'tag2'])
    # init again does nothing
    res = ds.metadata(init=['tag3'], dataset_global=True)
    eq_(res[0]['metadata']['tag'], ['tag1', 'tag2'])
    # reset whole key
    res = ds.metadata(reset=['tag'], dataset_global=True)
    assert_result_count(ds.metadata(), 0)
    # add something arbitrary
    res = ds.metadata(add=dict(dtype=['heavy'], readme=['short', 'long']),
                      dataset_global=True)
    eq_(res[0]['metadata']['dtype'], ['heavy'])
    # sorted!
    eq_(res[0]['metadata']['readme'], ['long', 'short'])
    # supply key definitions, no need for dataset_global
    res = ds.metadata(define_key=dict(mykey='truth'))
    eq_(res[0]['metadata']['definition'], {'mykey': u'truth'})
    # re-supply different key definitions -> error
    res = ds.metadata(define_key=dict(mykey='lie'), on_failure='ignore')
    assert_result_count(
        res, 1, status='error',
        message=("conflicting definition for key '%s': '%s' != '%s'",
                 "mykey", "lie", "truth"))
    res = ds.metadata(define_key=dict(otherkey='altfact'))
    assert_dict_equal(
        res[0]['metadata']['definition'],
        {'mykey': u'truth', 'otherkey': 'altfact'})
    # 'definition' is a regular key, we can remove items
    res = ds.metadata(remove=dict(definition=['mykey']), dataset_global=True)
    assert_dict_equal(
        res[0]['metadata']['definition'],
        {'otherkey': u'altfact'})
    res = ds.metadata(remove=dict(definition=['otherkey']), dataset_global=True)
    # when there are no items left, the key vanishes too
    assert('definition' not in res[0]['metadata'])
    # we still have metadata, so there is a DB file
    assert(res[0]['metadata'])
    db_path = opj(ds.path, '.datalad', 'metadata', 'dataset.json')
    assert(exists(db_path))
    ok_clean_git(ds.path)
    # but if we remove it, the file is gone
    res = ds.metadata(reset=['readme', 'dtype'], dataset_global=True)
    eq_(res[0]['metadata'], {})
    assert(not exists(db_path))
    ok_clean_git(ds.path)


@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_mod_hierarchy(path):
    base = Dataset(path).create()
    sub = base.create('sub')
    basedb_path = opj(base.path, '.datalad', 'metadata', 'dataset.json')
    subdb_path = opj(sub.path, '.datalad', 'metadata', 'dataset.json')
    assert(not exists(basedb_path))
    assert(not exists(subdb_path))
    # modify sub through base
    res = base.metadata('sub', init=['tag1'], dataset_global=True)
    # only sub modified
    assert_result_count(res, 3)
    assert_result_count(res, 1, status='ok', action='metadata',
                        metadata={'tag': ['tag1']})
    assert_result_count(res, 2, status='ok', action='save')
    assert(not exists(basedb_path))
    assert(exists(subdb_path))
    # saved all the way up
    ok_clean_git(base.path)
    # now again, different init, sub has tag already, should be spared
    res = base.metadata(init=['tag2'], dataset_global=True)
    assert_result_count(res, 2)
    assert_result_count(res, 1, status='ok', action='metadata',
                        metadata={'tag': ['tag2']}, path=base.path)
    assert_result_count(res, 1, status='ok', action='save', path=base.path)

    # and again with removal of all metadata in sub
    ok_clean_git(base.path)
    # put to probe files so we see that nothing unrelated gets saved
    create_tree(base.path, {'probe': 'content', 'sub': {'probe': 'othercontent'}})
    res = base.metadata('sub', reset=['tag'], dataset_global=True)
    assert_result_count(res, 3)
    assert_result_count(res, 1, status='ok', action='metadata',
                        metadata={})
    assert_result_count(res, 1, status='ok', action='save', path=base.path)
    assert(exists(basedb_path))
    assert(not exists(subdb_path))
    # when we remove the probe files things should be clean
    os.remove(opj(base.path, 'probe'))
    os.remove(opj(sub.path, 'probe'))
    ok_clean_git(base.path)
