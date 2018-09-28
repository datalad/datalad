# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test file info getters"""

import os
import os.path as op
import shutil

from datalad.tests.utils import (
    with_tempfile,
    create_tree,
    assert_equal,
    assert_in,
    assert_not_in,
    ok_clean_git,
)

from datalad.api import (
    Dataset,
    create,
)

from datalad.support.gitrepo import GitRepo


def _get_convoluted_situation(path):
    ds = Dataset(path).create(force=True)
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_normal': 'file_normal',
                'file_deleted': 'file_deleted',
            },
            'file_normal': 'file_normal',
            'file_deleted': 'file_deleted',
        }
    )
    ds.add('.')
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_ingit': 'file_ingit',
            },
            'file_ingit': 'file_ingit',
        }
    )
    ds.add('.', to_git=True)
    ds.create('subds_available')
    ds.create(op.join('subdir', 'subds_available'))
    ds.create('subds_unavailable')
    ds.create(op.join('subdir', 'subds_unavailable'))
    ds.create('subds_deleted')
    ds.create(op.join('subdir', 'subds_deleted'))
    ds.uninstall([
        'subds_unavailable',
        op.join('subdir', 'subds_unavailable')],
        check=False)
    ok_clean_git(ds.path)
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_untracked': 'file_untracked',
            },
            'file_untracked': 'file_untracked',
            'dir_untracked': {
                'file_untracked': 'file_untracked',
            }
        }
    )
    create(op.join(ds.path, 'subds_untracked'))
    create(op.join(ds.path, 'subdir', 'subds_untracked'))
    os.remove(op.join(ds.path, 'file_deleted'))
    os.remove(op.join(ds.path, 'subdir', 'file_deleted'))
    shutil.rmtree(op.join(ds.path, 'subds_deleted'))
    shutil.rmtree(op.join(ds.path, 'subdir', 'subds_deleted'))
    return ds


@with_tempfile
def test_get_content_info(path):
    repo = GitRepo(path)
    assert_equal(repo.get_content_info(), {})

    ds = _get_convoluted_situation(path)

    # verify general rules
    for f, r in ds.repo.get_content_info(wtmode=True).items():
        if f.endswith('untracked'):
            assert(r['revision'] is None)
        if f.endswith('deleted'):
            assert(r['stat_wt'] is None)
        if 'subds_' in f:
                assert(r['type'] == 'dataset' if r['revision'] else 'directory')
        if 'file_' in f:
            # which one exactly depends on many things
            assert_in(r['type'], ('file', 'symlink'))
        if 'file_ingit' in f:
            assert(r['type'] == 'file')
        elif 'datalad' not in f and 'git' not in f and \
                r['revision'] and 'subds' not in f:
            # this should be known to annex, one way or another
            assert_in('key', r)
            assert_in('keyname', r)
            assert_in('backend', r)
            assert_in('bytesize', r)
            # no duplication with path
            assert_not_in('file', r)

    # query a single absolute path
    res = ds.repo.get_content_info(
        [op.join(ds.path, 'subdir', 'file_normal')])
    assert_equal(len(res), 1)
    assert_in(op.join('subdir', 'file_normal'), res)


