# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test file info getters"""


import os.path as op
from pathlib import Path

import datalad.utils as ut
from datalad.distribution.dataset import Dataset
from datalad.support.exceptions import NoSuchPathError
from datalad.support.gitrepo import GitRepo
from datalad.tests.utils_pytest import (
    assert_dict_equal,
    assert_equal,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    get_annexstatus,
    get_convoluted_situation,
    known_failure_githubci_win,
    slow,
    with_tempfile,
    with_tree,
)


@slow  # 10sec on travis
@known_failure_githubci_win
@with_tempfile
def test_get_content_info(path=None):
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
    # (to get the last committed stage and with it possibly vanished
    # content), and lastly annex info wrt to the present worktree, to
    # also get info on added/staged content
    # this fuses the info reported from
    # - git ls-files
    # - git annex findref HEAD
    # - git annex find --include '*'
    for f, r in get_annexstatus(ds.repo).items():
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
            # or anything in between
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
    annexstatus = get_annexstatus(ds.repo)
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
def test_compare_content_info(path=None):
    # TODO remove when `create` is RF to return the new Dataset
    ds = Dataset(path).create()
    assert_repo_status(path)

    # for a clean repo HEAD and worktree query should yield identical results
    # minus a 'bytesize' report that is readily available for HEAD, but would
    # not a stat call per file for the worktree, and is not done ATM
    wt = ds.repo.get_content_info(ref=None)
    assert_dict_equal(
        wt,
        {f: {k: v for k, v in p.items() if k != 'bytesize'}
         for f, p in ds.repo.get_content_info(ref='HEAD').items()}
    )


@with_tempfile
def test_subds_path(path=None):
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
def test_report_absent_keys(path=None):
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
    ds.drop('dummy', reckless='kill')
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
    # make sure files with URL keys are correctly reported:
    from datalad.conftest import test_http_server
    remote_file_name = 'imaremotefile.dat'
    local_file_name = 'mehasurlkey'
    (Path(test_http_server.path) / remote_file_name).write_text("weee")
    remote_file_url = f'{test_http_server.url}/{remote_file_name}'
    # we need to get a file with a URL key and check its local availability
    ds.repo.call_annex(['addurl', '--relaxed', remote_file_url, '--file',
                        local_file_name])
    ds.save("URL keys!")
    # should not be there
    res = ds.repo.get_file_annexinfo(local_file_name, eval_availability=True)
    assert_equal(res['has_content'], False)
    ds.get(local_file_name)
    # should be there
    res = ds.repo.get_file_annexinfo(local_file_name, eval_availability=True)
    assert_equal(res['has_content'], True)


@with_tempfile
def test_annexinfo_init(path=None):
    ds = Dataset(path).create()
    foo = ds.pathobj / "foo"
    foo_cont = b"foo content"
    foo.write_bytes(foo_cont)
    bar = ds.pathobj / "bar"
    bar.write_text(u"bar content")
    ds.save()

    # Custom init limits report, with original dict getting updated.
    cinfo_custom_init = ds.repo.get_content_annexinfo(
        init={foo: {"bytesize": 0,
                    "this-is-surely-only-here": "right?"}})
    assert_not_in(bar, cinfo_custom_init)
    assert_in(foo, cinfo_custom_init)
    assert_equal(cinfo_custom_init[foo]["bytesize"], len(foo_cont))
    assert_equal(cinfo_custom_init[foo]["this-is-surely-only-here"],
                 "right?")

    # "git" injects get_content_info() values.
    cinfo_init_git = ds.repo.get_content_annexinfo(init="git")
    assert_in("gitshasum", cinfo_init_git[foo])

    # init=None, on the other hand, does not.
    cinfo_init_none = ds.repo.get_content_annexinfo(init=None)
    assert_in(foo, cinfo_init_none)
    assert_in(bar, cinfo_init_none)
    assert_not_in("gitshasum", cinfo_init_none[foo])


@with_tempfile
def test_info_path_inside_submodule(path=None):
    ds = Dataset(path).create()
    subds = ds.create("submod")
    foo = (subds.pathobj / "foo")
    foo.write_text("foo")
    ds.save(recursive=True)
    cinfo = ds.repo.get_content_info(
        ref="HEAD", paths=[foo.relative_to(ds.pathobj)])
    assert_in("gitshasum", cinfo[subds.pathobj])


@with_tempfile
def test_get_content_info_dotgit(path=None):
    ds = Dataset(path).create()
    # Files in .git/ won't be reported, though this takes a kludge on our side
    # before Git 2.25.
    assert_false(ds.repo.get_content_info(paths=[op.join(".git", "config")]))


@with_tempfile
def test_get_content_info_paths_empty_list(path=None):
    ds = Dataset(path).create()

    # Unlike None, passing any empty list as paths to get_content_info() does
    # not report on all content.
    assert_false(ds.repo.get_content_info(paths=[]))
    assert_false(ds.repo.get_content_info(paths=[], ref="HEAD"))

    # Add annex content to make sure its not reported.
    (ds.pathobj / "foo").write_text("foo")
    ds.save()

    # Same for get_content_annexinfo()...
    assert_false(ds.repo.get_content_annexinfo(paths=[]))
    assert_false(ds.repo.get_content_annexinfo(paths=[], init=None))
    assert_false(ds.repo.get_content_annexinfo(paths=[], ref="HEAD"))
    assert_false(
        ds.repo.get_content_annexinfo(paths=[], ref="HEAD", init=None))
    # ... where whatever was passed for init will be returned as is.
    assert_equal(
        ds.repo.get_content_annexinfo(
            paths=[], ref="HEAD", init={"random": {"entry": "a"}}),
        {"random": {"entry": "a"}})


@with_tempfile
def test_status_paths_empty_list(path=None):
    ds = Dataset(path).create()
    assert_equal(ds.repo.status(paths=[]), {})


@with_tree(tree=(('ingit.txt', 'ingit'),
                 ('inannex.txt', 'inannex'),
                 ('dir1', {'dropped': 'dropped'}),
                 ('dir2', {'d21': 'd21', 'd22': 'd22'})))
def test_get_file_annexinfo(path=None):
    ds = Dataset(path).create(force=True)
    ds.save('ingit.txt', to_git=True)
    ds.save()
    # have some content-less component for testing
    ds.drop(ds.pathobj / 'dir1', reckless='kill')

    repo = ds.repo
    # only handles a single file at a time
    assert_raises(ValueError, repo.get_file_annexinfo, repo.pathobj / 'dir2')
    # however, it only functionally matters that there is only a single file to
    # report on not that the exact query path matches, the matching path is in
    # the report
    assert_equal(
        repo.pathobj / 'dir1' / 'dropped',
        repo.get_file_annexinfo(repo.pathobj / 'dir1')['path'])

    # does not raise on a non-annex file, instead it returns no properties
    assert_equal(repo.get_file_annexinfo('ingit.txt'), {})

    # but does raise on path that doesn exist
    assert_raises(NoSuchPathError, repo.get_file_annexinfo, 'nothere')

    # check return properties for utility
    props = repo.get_file_annexinfo('inannex.txt')
    # to replace get_file_backend()
    assert_equal(props['backend'], 'MD5E')
    # to replace get_file_key()
    assert_equal(props['key'], 'MD5E-s7--3b158c5b0a18c247ebad28c09fc3e180.txt')
    # for size reporting
    assert_equal(props['bytesize'], 7)
    # all records have a pathobj
    assert_equal(props['path'], repo.pathobj / 'inannex.txt')
    # test if `eval_availability` has desired effect
    assert_not_in('has_content', props)

    # extended set of properties, after more expensive availability check
    props = repo.get_file_annexinfo('inannex.txt', eval_availability=True)
    # to replace file_has_content()
    assert_equal(props['has_content'], True)
    # to replace get_contentlocation()
    assert_equal(
        Path(props['objloc']).read_text(),
        'inannex')

    # make sure has_content is not always True
    props = repo.get_file_annexinfo(
        ds.pathobj / 'dir1' / 'dropped', eval_availability=True)
    assert_equal(props['has_content'], False)
    assert_not_in('objloc', props)
