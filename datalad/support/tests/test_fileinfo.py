# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test file info getters"""


from six import iteritems
import os.path as op
import datalad.utils as ut

from datalad.tests.utils import (
    with_tempfile,
    assert_equal,
    assert_dict_equal,
    assert_in,
    assert_not_in,
    assert_raises,
)

from datalad.distribution.dataset import Dataset
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils import (
    assert_repo_status,
    get_convoluted_situation,
)


@with_tempfile
def test_get_content_info(path):
    repo = GitRepo(path)
    assert_equal(repo.get_content_info(), {})
    # an invalid reference causes an exception
    assert_raises(ValueError, repo.get_content_info, ref='HEAD')

    ds = get_convoluted_situation(path)
    repopath = ds.repo.pathobj

    assert_equal(ds.repo.pathobj, repopath)
    assert_equal(ds.pathobj, ut.Path(path))

    # verify general rules on fused info records that are incrementally
    # assembled: for git content info, amended with annex info on 'HEAD'
    # (to get the last commited stage and with it possibly vanished
    # content), and lastly annex info wrt to the present worktree, to
    # also get info on added/staged content
    # this fuses the info reported from
    # - git ls-files
    # - git annex findref HEAD
    # - git annex find --include '*'
    for f, r in ds.repo.annexstatus().items():
        if f.match('*_untracked'):
            assert(r.get('gitshasum', None) is None)
        if f.match('*_deleted'):
            assert(not f.exists() and not f.is_symlink() is None)
        if f.match('subds_*'):
            assert(r['type'] == 'dataset' if r.get('gitshasum', None) else 'directory')
        if f.match('file_*'):
            # which one exactly depends on many things
            assert_in(r['type'], ('file', 'symlink'))
        if f.match('file_ingit*'):
            assert(r['type'] == 'file')
        elif '.datalad' not in f.parts and not f.match('.git*') and \
                r.get('gitshasum', None) and not f.match('subds*'):
            # this should be known to annex, one way or another
            # regardless of whether things add deleted or staged
            # or anything inbetween
            assert_in('key', r, f)
            assert_in('keyname', r, f)
            assert_in('backend', r, f)
            assert_in('bytesize', r, f)
            # no duplication with path
            assert_not_in('file', r, f)

    # query full untracked report
    res = ds.repo.get_content_info()
    assert_in(repopath.joinpath('dir_untracked', 'file_untracked'), res)
    assert_not_in(repopath.joinpath('dir_untracked'), res)
    # query for compact untracked report
    res = ds.repo.get_content_info(untracked='normal')
    assert_not_in(repopath.joinpath('dir_untracked', 'file_untracked'), res)
    assert_in(repopath.joinpath('dir_untracked'), res)
    # query no untracked report
    res = ds.repo.get_content_info(untracked='no')
    assert_not_in(repopath.joinpath('dir_untracked', 'file_untracked'), res)
    assert_not_in(repopath.joinpath('dir_untracked'), res)

    # git status integrity
    status = ds.repo.status()
    for t in ('subds', 'file'):
        for s in ('untracked', 'added', 'deleted', 'clean',
                  'ingit_clean', 'dropped_clean', 'modified',
                  'ingit_modified'):
            for l in ('', ut.PurePosixPath('subdir', '')):
                if t == 'subds' and 'ingit' in s or 'dropped' in s:
                    # invalid combination
                    continue
                if t == 'subds' and s == 'deleted':
                    # same as subds_unavailable -> clean
                    continue
                p = repopath.joinpath(l, '{}_{}'.format(t, s))
                assert p.match('*_{}'.format(status[p]['state'])), p
                if t == 'subds':
                    assert_in(status[p]['type'], ('dataset', 'directory'), p)
                else:
                    assert_in(status[p]['type'], ('file', 'symlink'), p)

    # git annex status integrity
    annexstatus = ds.repo.annexstatus()
    for t in ('file',):
        for s in ('untracked', 'added', 'deleted', 'clean',
                  'ingit_clean', 'dropped_clean', 'modified',
                  'ingit_modified'):
            for l in ('', ut.PurePosixPath('subdir', '')):
                p = repopath.joinpath(l, '{}_{}'.format(t, s))
                if s in ('untracked', 'ingit_clean', 'ingit_modified'):
                    # annex knows nothing about these things
                    assert_not_in('key', annexstatus[p])
                    continue
                assert_in('key', annexstatus[p])
                # dear future,
                # if the next one fails, git-annex might have changed the
                # nature of the path that are being reported by
                # `annex find --json`
                # when this was written `hashir*` was a native path, but
                # `file` was a POSIX path
                assert_equal(annexstatus[p]['has_content'], 'dropped' not in s)

    # check the different subds evaluation modes
    someds = Dataset(ds.pathobj / 'subds_modified' / 'someds')
    dirtyds_path = someds.pathobj / 'dirtyds'
    assert_not_in(
        'state',
        someds.repo.status(eval_submodule_state='no')[dirtyds_path]
    )
    assert_equal(
        'clean',
        someds.repo.status(eval_submodule_state='commit')[dirtyds_path]['state']
    )
    assert_equal(
        'modified',
        someds.repo.status(eval_submodule_state='full')[dirtyds_path]['state']
    )



@with_tempfile
def test_compare_content_info(path):
    # TODO remove when `create` is RF to return the new Dataset
    ds = Dataset(path).create()
    assert_repo_status(path)

    # for a clean repo HEAD and worktree query should yield identical results
    # minus a 'bytesize' report that is readily available for HEAD, but would
    # not a stat call per file for the worktree, and is not done ATM
    wt = ds.repo.get_content_info(ref=None)
    assert_dict_equal(
        wt,
        {f: {k: v for k, v in iteritems(p) if k != 'bytesize'}
         for f, p in iteritems(ds.repo.get_content_info(ref='HEAD'))}
    )


@with_tempfile
def test_subds_path(path):
    # a dataset with a subdataset with a file, all neatly tracked
    ds = Dataset(path).create()
    subds = ds.create('sub')
    assert_repo_status(path)
    with (subds.pathobj / 'some.txt').open('w') as f:
        f.write(u'test')
    ds.save(recursive=True)
    assert_repo_status(path)

    # querying the toplevel dataset repo for a subdspath should
    # report the subdataset record in the dataset
    # (unlike `git status`, which is silent for subdataset paths),
    # but definitely not report the subdataset as deleted
    # https://github.com/datalad/datalad-revolution/issues/17
    stat = ds.repo.status(paths=[op.join('sub', 'some.txt')])
    assert_equal(list(stat.keys()), [subds.repo.pathobj])
    assert_equal(stat[subds.repo.pathobj]['state'], 'clean')


@with_tempfile
def test_report_absent_keys(path):
    ds = Dataset(path).create()
    # create an annexed file
    testfile = ds.pathobj / 'dummy'
    testfile.write_text(u'nothing')
    ds.save()
    # present in a full report and in a partial report
    # based on worktree of HEAD ref
    for ai in (
            ds.repo.get_content_annexinfo(eval_availability=True),
            ds.repo.get_content_annexinfo(
                paths=['dummy'],
                eval_availability=True),
            ds.repo.get_content_annexinfo(
                ref='HEAD',
                eval_availability=True),
            ds.repo.get_content_annexinfo(
                ref='HEAD',
                paths=['dummy'],
                eval_availability=True)):
        assert_in(testfile, ai)
        assert_equal(ai[testfile]['has_content'], True)
    # drop the key, not available anywhere else
    ds.drop('dummy', check=False)
    # does not change a thing, except the key is gone
    for ai in (
            ds.repo.get_content_annexinfo(eval_availability=True),
            ds.repo.get_content_annexinfo(
                paths=['dummy'],
                eval_availability=True),
            ds.repo.get_content_annexinfo(
                ref='HEAD',
                eval_availability=True),
            ds.repo.get_content_annexinfo(
                ref='HEAD',
                paths=['dummy'],
                eval_availability=True)):
        assert_in(testfile, ai)
        assert_equal(ai[testfile]['has_content'], False)
