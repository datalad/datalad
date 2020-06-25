# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test get action

"""

from os import curdir
from os.path import (
    join as opj,
    basename,
)
from unittest.mock import patch

from datalad.api import (
    create,
    get,
    install,
)
from datalad.interface.results import only_matching_paths
from datalad.distribution.get import _get_flexible_source_candidates_for_submodule
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    RemoteNotAvailableError,
)
from datalad.tests.utils import (
    ok_,
    eq_,
    with_tempfile,
    with_testrepos,
    with_tree,
    create_tree,
    assert_false,
    assert_raises,
    assert_in,
    assert_status,
    assert_in_results,
    assert_not_in_results,
    assert_repo_status,
    assert_result_count,
    assert_message,
    serve_path_via_http,
    slow,
    known_failure_windows,
)
from datalad.utils import (
    with_pathsep,
    chpwd,
    rmtree,
)
from ..dataset import Dataset


def _make_dataset_hierarchy(path):
    origin = Dataset(path).create()
    origin_sub1 = origin.create('sub1')
    origin_sub2 = origin_sub1.create('sub2')
    with open(opj(origin_sub2.path, 'file_in_annex.txt'), "w") as f:
        f.write('content2')
    origin_sub3 = origin_sub2.create('sub3')
    with open(opj(origin_sub3.path, 'file_in_annex.txt'), "w") as f:
        f.write('content3')
    origin_sub4 = origin_sub3.create('sub4')
    origin.save(recursive=True)
    return origin, origin_sub1, origin_sub2, origin_sub3, origin_sub4


@with_tempfile
@with_tempfile
@with_tempfile
def test_get_flexible_source_candidates_for_submodule(t, t2, t3):
    f = _get_flexible_source_candidates_for_submodule
    # for now without mocking -- let's just really build a dataset
    ds = create(t)
    sub = ds.create('sub')
    clone = install(
        t2, source=t,
        result_xfm='datasets', return_type='item-or-list')

    # first one could just know about itself or explicit url provided
    sshurl = 'ssh://e.c'
    httpurl = 'http://e.c'
    ds_subpath = str(ds.pathobj / 'sub')
    eq_(f(ds, dict(path=ds_subpath, parentds=ds.path)), [])
    eq_(f(ds, dict(path=ds_subpath, parentds=ds.path, gitmodule_url=sshurl)),
        [dict(cost=900, name='local', url=sshurl)])
    eq_(f(ds, dict(path=ds_subpath, parentds=ds.path, gitmodule_url=httpurl)),
        [dict(cost=900, name='local', url=httpurl)])

    # but if we work on dsclone then it should also add urls deduced from its
    # own location default remote for current branch
    clone_subpath = str(clone.pathobj / 'sub')
    eq_(f(clone, dict(path=clone_subpath, parentds=clone.path)),
        [dict(cost=500, name='origin', url=ds_subpath)])
    eq_(f(clone, dict(path=clone_subpath, parentds=clone.path, gitmodule_url=sshurl)),
        [dict(cost=500, name='origin', url=ds_subpath),
         dict(cost=600, name='origin', url=sshurl)])
    eq_(f(clone, dict(path=clone_subpath, parentds=clone.path, gitmodule_url=httpurl)),
        [dict(cost=500, name='origin', url=ds_subpath),
         dict(cost=600, name='origin', url=httpurl)])

    # make sure it does meaningful things in an actual clone with an actual
    # record of a subdataset
    clone_subpath = str(clone.pathobj / 'sub')
    eq_(f(clone, clone.subdatasets(return_type='item-or-list')),
        [
            dict(cost=500, name='origin', url=ds_subpath),
    ])

    # check that a configured remote WITHOUT the desired submodule commit
    # does not show up as a candidate
    clone.siblings('add', name='myremote', url='http://example.com',
                   result_renderer='disabled')
    eq_(f(clone, clone.subdatasets(return_type='item-or-list')),
        [
            dict(cost=500, name='origin', url=ds_subpath),
    ])
    # inject a source URL config, should alter the result accordingly
    with patch.dict(
            'os.environ',
            {'DATALAD_GET_SUBDATASET__SOURCE__CANDIDATE__BANG': 'youredead'}):
        eq_(f(clone, clone.subdatasets(return_type='item-or-list')),
            [
                dict(cost=500, name='origin', url=ds_subpath),
                dict(cost=700, name='bang', url='youredead', from_config=True),
        ])
    # we can alter the cost by given the name a two-digit prefix
    with patch.dict(
            'os.environ',
            {'DATALAD_GET_SUBDATASET__SOURCE__CANDIDATE__400BANG': 'youredead'}):
        eq_(f(clone, clone.subdatasets(return_type='item-or-list')),
            [
                dict(cost=400, name='bang', url='youredead', from_config=True),
                dict(cost=500, name='origin', url=ds_subpath),
        ])
    # verify template instantiation works
    with patch.dict(
            'os.environ',
            {'DATALAD_GET_SUBDATASET__SOURCE__CANDIDATE__BANG': 'pre-{id}-post'}):
        eq_(f(clone, clone.subdatasets(return_type='item-or-list')),
            [
                dict(cost=500, name='origin', url=ds_subpath),
                dict(cost=700, name='bang', url='pre-{}-post'.format(sub.id),
                     from_config=True),
        ])
    # now again, but have an additional remote besides origin that
    # actually has the relevant commit
    clone3 = install(
        t3, source=t2,
        result_xfm='datasets', return_type='item-or-list')
    clone3.siblings('add', name='myremote', url=ds.path,
                    result_renderer='disabled')
    clone3.update(sibling='myremote')
    # we should end up with this additional piece
    # we are not checking for the name of the remote, because it is actually
    # registered under two different names
    assert_in(
        ds_subpath,
        [i['url']
         for i in f(clone3, clone3.subdatasets(return_type='item-or-list'))]
    )

    # TODO: check that http:// urls for the dataset itself get resolved
    # TODO: many more!!


@with_tempfile(mkdir=True)
@with_tempfile(content="doesntmatter")
def test_get_invalid_call(path, file_outside):

    # no argument at all:
    assert_raises(InsufficientArgumentsError, get, None)
    assert_raises(InsufficientArgumentsError, get, [])
    # invalid dataset:
    assert_raises(ValueError, get, None, dataset=path, on_failure='ignore')

    # have a plain git:
    ds = Dataset(path)
    ds.create(annex=False)
    with open(opj(path, "some.txt"), "w") as f:
        f.write("whatever")
    ds.save("some.txt", to_git=True, message="Initial commit.")

    # make it an annex (remove indicator file that create has placed
    # in the dataset to make it possible):
    (ds.pathobj / '.noannex').unlink()
    AnnexRepo(path, init=True, create=True)
    # call get again on a file in git:
    result = ds.get("some.txt")
    assert_status('notneeded', result)

    # invalid source:
    # yoh:  but now we would need to add it to annex since clever code first
    # checks what needs to be fetched at all
    create_tree(path, {'annexed.dat': 'some'})
    ds.save("annexed.dat")
    ds.repo.drop("annexed.dat", options=['--force'])
    with assert_raises(RemoteNotAvailableError) as ce:
        ds.get("annexed.dat", source='MysteriousRemote')
    eq_("MysteriousRemote", ce.exception.remote)

    res = ds.get("NotExistingFile.txt", on_failure='ignore')
    assert_status('impossible', res)
    assert_message("path does not exist", res)

    # path outside repo errors as with most other commands:
    res = ds.get(file_outside, on_failure='ignore', result_renderer='default')
    assert_in_results(
        res, status='error',
        message=('path not associated with dataset %s', ds))


@with_testrepos('basic_annex', flavors='clone')
def test_get_single_file(path):

    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    result = ds.get("test-annex.dat")
    assert_result_count(result, 1)
    assert_status('ok', result)
    eq_(result[0]['path'], opj(ds.path, 'test-annex.dat'))
    eq_(result[0]['annexkey'], ds.repo.get_file_key('test-annex.dat'))
    ok_(ds.repo.file_has_content('test-annex.dat') is True)


@with_tempfile(mkdir=True)
def check_get_subdataset_inherit_reckless(override, path):
    src = Dataset(opj(path, "a")).create()
    src_subds = src.create("sub")
    src_subds.create("subsub")
    src.save(recursive=True)

    clone = install(opj(path, "b"), source=src, reckless="auto",
                    result_xfm="datasets", return_type="item-or-list")
    clone_sub = Dataset(clone.pathobj / "sub")
    assert_false(clone_sub.is_installed())
    clone_subsub = Dataset(clone.pathobj / "sub" / "subsub")

    clone.get(opj("sub", "subsub"), reckless=False if override else None)
    ok_(clone_sub.is_installed())
    ok_(clone_subsub.is_installed())

    for sub in [clone_sub, clone_subsub]:
        eq_(sub.config.get("datalad.clone.reckless", None),
            None if override else "auto")
        eq_(sub.config.get("annex.hardlink", None),
            None if override else "true")


def test_get_subdataset_inherit_reckless():
    yield check_get_subdataset_inherit_reckless, False
    yield check_get_subdataset_inherit_reckless, True


@with_tree(tree={'file1.txt': 'whatever 1',
                 'file2.txt': 'whatever 2',
                 'file3.txt': 'whatever 3',
                 'file4.txt': 'whatever 4'})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_get_multiple_files(path, url, ds_dir):
    from os import listdir
    from datalad.support.network import RI

    file_list = [f for f in listdir(path) if not f.startswith('.')]

    # prepare urls:
    [RI(url + f) for f in file_list]

    # prepare origin
    origin = Dataset(path).create(force=True)
    origin.save(file_list, message="initial")

    ds = install(
        ds_dir, source=path,
        result_xfm='datasets', return_type='item-or-list')

    # no content present:
    ok_(not any(ds.repo.file_has_content(file_list)))

    # get two plus an invalid one:
    result = ds.get(['file1.txt', 'file2.txt', 'not_existing.txt'],
                    on_failure='ignore')
    assert_status('impossible', [result[0]])
    assert_status(['ok', 'notneeded'], result[1:])
    # explicitly given not existing file was skipped:
    # (see test_get_invalid_call)
    eq_(set([basename(item.get('path')) for item in result[1:]]),
        {'file1.txt', 'file2.txt'})
    ok_(all(ds.repo.file_has_content(['file1.txt', 'file2.txt'])))

    # get all of them:
    result = ds.get(curdir)
    # there were two files left to get:
    eq_(set([basename(item.get('path')) for item in result if item['type'] == 'file']),
        {'file3.txt', 'file4.txt'})
    ok_(all(ds.repo.file_has_content(file_list)))


@with_tree(tree={'file1.txt': 'something',
                 'subdir': {'file2.txt': 'something else',
                            'subsubdir': {
                                'file3.txt': 'something completely different',
                                'file4.txt': 'something'
                            }}})
@with_tempfile(mkdir=True)
def test_get_recurse_dirs(o_path, c_path):

    # prepare source:
    origin = Dataset(o_path).create(force=True)
    origin.save()

    ds = install(
        c_path, source=o_path,
        result_xfm='datasets', return_type='item-or-list')

    file_list = ['file1.txt',
                 opj('subdir', 'file2.txt'),
                 opj('subdir', 'subsubdir', 'file3.txt'),
                 opj('subdir', 'subsubdir', 'file4.txt')]
    files_in_sub = [f for f in file_list if f.startswith(with_pathsep('subdir'))]

    # no content present:
    ok_(not any(ds.repo.file_has_content(file_list)))

    result = ds.get('subdir')
    # check result:
    assert_status('ok', result)
    eq_(set([item.get('path')[len(ds.path) + 1:] for item in result
             if item['type'] == 'file']),
        set(files_in_sub))
    # we also get one report on the subdir
    eq_(len(result) - 1, len(files_in_sub))

    # got all files beneath subdir:
    ok_(all(ds.repo.file_has_content(files_in_sub)))

    # additionally got file1.txt silently, since it has the same content as
    # subdir/subsubdir/file4.txt:
    ok_(ds.repo.file_has_content('file1.txt') is True)


# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789022#step:8:541
@known_failure_windows
@slow  # 15.1496s
@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_recurse_subdatasets(src, path):

    ds = install(
        path, source=src,
        result_xfm='datasets', return_type='item-or-list')

    # ask for the two subdatasets specifically. This will obtain them,
    # but not any content of any files in them
    subds1, subds2 = ds.get(['subm 1', '2'], get_data=False,
                            description="youcouldnotmakethisup",
                            result_xfm='datasets')
    for d in (subds1, subds2):
        eq_(d.repo.get_description(), 'youcouldnotmakethisup')

    # there are 3 files to get: test-annex.dat within each dataset:
    rel_path_sub1 = opj(basename(subds1.path), 'test-annex.dat')
    rel_path_sub2 = opj(basename(subds2.path), 'test-annex.dat')
    annexed_files = {'test-annex.dat',
                     rel_path_sub1,
                     rel_path_sub2}

    # None of them is currently present:
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)
    ok_(subds2.repo.file_has_content('test-annex.dat') is False)

    assert_repo_status(subds1.path)
    # explicitly given path in subdataset => implicit recursion:
    # MIH: Nope, we fulfill the dataset handle, but that doesn't
    #      imply fulfilling all file handles
    result = ds.get(rel_path_sub1, recursive=True)
    # the subdataset was already present
    assert_in_results(
        result,
        type='dataset',
        path=subds1.path,
        status='notneeded')
    # we got the file
    assert_in_results(
        result,
        path=opj(ds.path, rel_path_sub1),
        status='ok')

    assert_in_results(result, path=opj(ds.path, rel_path_sub1), status='ok')
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)

    # drop it:
    subds1.repo.drop('test-annex.dat')
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)

    # now, with a path not explicitly pointing within a
    # subdataset, but recursive option:
    # get everything:
    result = ds.get(recursive=True, result_filter=lambda x: x.get('type') != 'dataset')
    assert_status('ok', result)

    eq_(set([item.get('path')[len(ds.path) + 1:] for item in result
             if item['type'] == 'file']),
        annexed_files)
    ok_(ds.repo.file_has_content('test-annex.dat') is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)
    ok_(subds2.repo.file_has_content('test-annex.dat') is True)

    # drop them:
    ds.repo.drop('test-annex.dat')
    subds1.repo.drop('test-annex.dat')
    subds2.repo.drop('test-annex.dat')
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)
    ok_(subds2.repo.file_has_content('test-annex.dat') is False)

    # now, the very same call, but without recursive:
    result = ds.get('.', recursive=False)
    assert_status('ok', result)
    # no duplicate reporting on subdataset install and annex-get of its
    # directory
    eq_(len(result), 1)
    assert_result_count(
        result, 1, path=opj(ds.path, 'test-annex.dat'), status='ok')
    ok_(ds.repo.file_has_content('test-annex.dat') is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)
    ok_(subds2.repo.file_has_content('test-annex.dat') is False)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_greedy_recurse_subdatasets(src, path):

    ds = install(
        path, source=src,
        result_xfm='datasets', return_type='item-or-list')

    # GIMME EVERYTHING
    ds.get(['subm 1', '2'])

    # We got all content in the subdatasets
    subds1, subds2 = ds.subdatasets(result_xfm='datasets')
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)
    ok_(subds2.repo.file_has_content('test-annex.dat') is True)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_install_missing_subdataset(src, path):

    ds = install(
        path=path, source=src,
        result_xfm='datasets', return_type='item-or-list')
    ds.create(force=True)  # force, to cause dataset initialization
    subs = ds.subdatasets(result_xfm='datasets')
    ok_(all([not sub.is_installed() for sub in subs]))

    # we don't install anything, if no explicitly given path points into a
    # not yet installed subdataset:
    ds.get(curdir)
    ok_(all([not sub.is_installed() for sub in subs]))

    # but we do, whenever a given path is contained in such a subdataset:
    file_ = opj(subs[0].path, 'test-annex.dat')
    ds.get(file_)
    ok_(subs[0].is_installed())
    ok_(subs[0].repo.file_has_content('test-annex.dat') is True)

    # but we fulfill any handles, and dataset handles too
    ds.get(curdir, recursive=True)
    ok_(all([sub.is_installed() for sub in subs]))


@slow  # 13.4610s
# @with_tree(tree={'file_in_git.txt': 'no idea',
#                  'subds': {'file_in_annex.txt': 'content'}})
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_mixed_hierarchy(src, path):

    origin = Dataset(src).create(annex=False)
    origin_sub = origin.create('subds')
    with open(opj(origin.path, 'file_in_git.txt'), "w") as f:
        f.write('no idea')
    with open(opj(origin_sub.path, 'file_in_annex.txt'), "w") as f:
        f.write('content')
    origin.save('file_in_git.txt', to_git=True)
    origin_sub.save('file_in_annex.txt')
    origin.save()

    # now, install that thing:
    ds, subds = install(
        path, source=src, recursive=True,
        result_xfm='datasets', return_type='item-or-list', result_filter=None)
    ok_(subds.repo.file_has_content("file_in_annex.txt") is False)

    # and get:
    result = ds.get(curdir, recursive=True)
    # git repo and subds
    assert_status(['ok', 'notneeded'], result)
    assert_result_count(
        result, 1, path=opj(subds.path, "file_in_annex.txt"), status='ok')
    ok_(subds.repo.file_has_content("file_in_annex.txt") is True)


@slow  # 20 sec
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_autoresolve_recurse_subdatasets(src, path):

    origin = Dataset(src).create()
    origin_sub = origin.create('sub')
    origin_subsub = origin_sub.create('subsub')
    with open(opj(origin_subsub.path, 'file_in_annex.txt'), "w") as f:
        f.write('content')
    origin.save(recursive=True)

    ds = install(
        path, source=src,
        result_xfm='datasets', return_type='item-or-list')
    eq_(len(ds.subdatasets(fulfilled=True)), 0)

    with chpwd(ds.path):
        results = get(opj(ds.path, 'sub'), recursive=True, result_xfm='datasets')
    eq_(len(ds.subdatasets(fulfilled=True, recursive=True)), 2)
    subsub = Dataset(opj(ds.path, 'sub', 'subsub'))
    ok_(subsub.is_installed())
    assert_in(subsub, results)
    # all file handles are fulfilled by default
    ok_(Dataset(opj(ds.path, 'sub', 'subsub')).repo.file_has_content(
        "file_in_annex.txt") is True)


@slow  # 92sec
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_recurse_existing(src, path):
    origin_ds = _make_dataset_hierarchy(src)

    # make sure recursion_limit works as expected across a range of depths
    for depth in range(len(origin_ds)):
        res = install(
            path, source=src, recursive=True, recursion_limit=depth,
            result_xfm=None, return_type='list', result_filter=None)
        # we expect one dataset per level
        assert_result_count(
            res, depth + 1, type='dataset', status='ok')
        rmtree(path)

    # now install all but the last two levels, no data
    root, sub1, sub2 = install(
        path, source=src, recursive=True, recursion_limit=2,
        result_xfm='datasets', result_filter=None)
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is False)
    sub3 = Dataset(opj(sub2.path, 'sub3'))
    ok_(not sub3.is_installed())
    # now get all content in all existing datasets, no new datasets installed
    # in the process
    files = root.get(curdir, recursive=True, recursion_limit='existing')
    assert_not_in_results(files, type='dataset', status='ok')
    assert_result_count(files, 1, type='file', status='ok')
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is True)
    ok_(not sub3.is_installed())
    # now pull down all remaining datasets, no data
    sub3, sub4 = root.get(
        curdir, recursive=True, get_data=False,
        result_xfm='datasets', result_filter=lambda x: x['status'] == 'ok')
    ok_(sub4.is_installed())
    ok_(sub3.repo.file_has_content('file_in_annex.txt') is False)
    # aaannd all data
    files = root.get(curdir, recursive=True, result_filter=lambda x: x['status'] == 'ok' and x['type'] == 'file')
    eq_(len(files), 1)
    ok_(sub3.repo.file_has_content('file_in_annex.txt') is True)


@slow  # 33sec
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_in_unavailable_subdataset(src, path):
    _make_dataset_hierarchy(src)
    root = install(
        path, source=src,
        result_xfm='datasets', return_type='item-or-list')
    targetpath = opj('sub1', 'sub2')
    targetabspath = opj(root.path, targetpath)
    with chpwd(path):
        res = get(targetabspath)
    assert_result_count(res, 2, status='ok', action='install', type='dataset')
    # dry-fit result filter that only returns the result that matched the requested
    # path
    filtered = [r for r in res if only_matching_paths(r, path=targetabspath)]
    assert_result_count(
        filtered, 1, status='ok', action='install', type='dataset',
        path=targetabspath)
    # we got the dataset, and its immediate content, but nothing below
    sub2 = Dataset(targetabspath)
    ok_(sub2.is_installed())
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is True)
    ok_(not Dataset(opj(targetabspath, 'sub3')).is_installed())


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_gh3356(src, path):
    # create toy version of gh-3356 scenario
    origin = Dataset(src).create()
    origin_sub = origin.create(origin.pathobj / 'subdir'/ 'subds')
    for p in (
            (origin_sub.pathobj / 'data' / 'file_in_annex.txt'),
            (origin_sub.pathobj / 'data' / 'file_in_annex2.txt')):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(p.name)
    origin.save(recursive=True)
    clone = install(
        path, source=src, result_xfm='datasets', return_type='item-or-list')
    targetpaths = [
        opj('subdir', 'subds', 'data', 'file_in_annex.txt'),
        opj('subdir', 'subds', 'data', 'file_in_annex2.txt'),
    ]
    with chpwd(path):
        res = get(targetpaths)
    # get() must report success on two files
    assert_result_count(res, 2, action='get', type='file', status='ok')
    # status must report content for two files
    assert_result_count(
        clone.status(recursive=True, annex='all', report_filetype='eval'), 2,
        action='status', has_content=True)
