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
    assert_dict_equal,
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
    create(op.join(ds.path, 'subds_added'))
    ds.repo.add_submodule('subds_added')
    create(op.join(ds.path, 'subdir', 'subds_added'))
    ds.repo.add_submodule(op.join('subdir', 'subds_added'))
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_untracked': 'file_untracked',
                'file_added': 'file_added',
            },
            'file_untracked': 'file_untracked',
            'file_added': 'file_added',
            'dir_untracked': {
                'file_untracked': 'file_untracked',
            }
        }
    )
    ds.repo.add(['file_added', op.join('subdir', 'file_added')])
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

    # with no reference, the worktree is the reference, hence no deleted
    # files are reported
    for f in ds.repo.get_content_annexinfo(init={}, ref=None):
        assert_not_in('deleted', f)
    # with a Git reference, nothing staged can be reported
    for f in ds.repo.get_content_annexinfo(init={}, ref='HEAD'):
        assert_not_in('added', f)

    # verify general rules on fused info records that are incrementally
    # assembled: for git content info, ammended with annex info on 'HEAD'
    # (to get the last commited stage and with it possibly vanished
    # content), and lastly annex info wrt to the present worktree, to
    # also get info on added/staged content
    # this fuses the info reported from
    # - git ls-files
    # - git annex findref HEAD
    # - git annex find --include '*'
    for f, r in ds.repo.get_content_annexinfo(
            init=ds.repo.get_content_annexinfo(
                ref='HEAD',
                stat_wt=True)).items():
        if f.endswith('untracked'):
            assert(r['gitshasum'] is None)
        if f.endswith('deleted'):
            assert(r['stat_wt'] is None)
        if 'subds_' in f:
                assert(r['type'] == 'dataset' if r['gitshasum'] else 'directory')
        if 'file_' in f:
            # which one exactly depends on many things
            assert_in(r['type'], ('file', 'symlink'))
        if 'file_ingit' in f:
            assert(r['type'] == 'file')
        elif 'datalad' not in f and 'git' not in f and \
                r['gitshasum'] and 'subds' not in f:
            # this should be known to annex, one way or another
            # regardless of whether things add deleted or staged
            # or anything inbetween
            assert_in('key', r, f)
            assert_in('keyname', r, f)
            assert_in('backend', r, f)
            assert_in('bytesize', r, f)
            # no duplication with path
            assert_not_in('file', r, f)

    # query a single absolute path
    res = ds.repo.get_content_info(
        [op.join(ds.path, 'subdir', 'file_normal')])
    assert_equal(len(res), 1)
    assert_in(op.join('subdir', 'file_normal'), res)


@with_tempfile
def test_compare_content_info(path):
    ds = Dataset(path).create()
    ok_clean_git(path)

    # for a clean repo HEAD and worktree query should yield identical results
    wt = ds.repo.get_content_info(ref=None)
    assert_dict_equal(wt, ds.repo.get_content_info(ref='HEAD'))
