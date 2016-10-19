# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test get action

"""


import logging
import re

from os import curdir
from os.path import join as opj, basename
from glob import glob

from datalad.api import get
from datalad.api import install
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.exceptions import RemoteNotAvailableError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import assert_re_in
from datalad.utils import swallow_logs, with_pathsep
from datalad.utils import chpwd
from datalad.utils import assure_list
from datalad.utils import rmtree

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
    origin.save(recursive=True, auto_add_changes=True)
    return origin, origin_sub1, origin_sub2, origin_sub3, origin_sub4


@with_tempfile(mkdir=True)
@with_tempfile(content="doesntmatter")
def test_get_invalid_call(path, file_outside):

    # no argument at all:
    assert_raises(InsufficientArgumentsError, get, None)
    assert_raises(InsufficientArgumentsError, get, [])
    # invalid dataset:
    assert_raises(ValueError, get, None, dataset=path)

    # have a plain git:
    ds = Dataset(path)
    ds.create(no_annex=True)
    with open(opj(path, "some.txt"), "w") as f:
        f.write("whatever")
    ds.add("some.txt", to_git=True)
    ds.save("Initial commit.")

    # no path given:
    assert_raises(InsufficientArgumentsError, get, dataset=path,
                  source="some", path=None)

    # get on a plain git:
    # MIH: why do we warn? user got what was desired. if they want technical
    # background they better read books not warnings
    #with swallow_logs(new_level=logging.WARNING) as cml:
    #    # but we don't fail if not annex -- just inform
    #    out = ds.get(curdir)
    #    assert_in('Found no annex. Could not perform any get operation.',
    #              cml.out)
    #    eq_(out, [])

    # make it an annex:
    AnnexRepo(path, init=True, create=True)
    # call get again on a file in git:
    result = ds.get("some.txt")
    # skipped silently, but no result for this file:
    eq_(len(result), 0)

    # invalid source:
    # yoh:  but now we would need to add it to annex since clever code first
    # checks what needs to be fetched at all
    create_tree(path, {'annexed.dat': 'some'})
    ds.add("annexed.dat")
    ds.repo.drop("annexed.dat", options=['--force'])
    with assert_raises(RemoteNotAvailableError) as ce:
        ds.get("annexed.dat", source='MysteriousRemote')
    eq_("MysteriousRemote", ce.exception.remote)

    # warning on not existing file:
    with swallow_logs(new_level=logging.WARNING) as cml:
        with assert_raises(IncompleteResultsError) as cme:
            ds.get("NotExistingFile.txt")
        result = cme.exception.results
        eq_(len(result), 0)
        assert_in("ignored non-existing paths", cml.out)

    # path outside repo:
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(file_outside)
        eq_(len(result), 0)
        assert_in("{0} is not part of a dataset, ignored".format(file_outside, ds),
                  cml.out)

    # TODO: annex --json doesn't report anything when get fails to do get a
    # file from a specified source, where the file isn't available from.
    # File report for Joey (plus other failures like not existing when
    # called with --json)


@with_testrepos('basic_annex', flavors='clone')
def test_get_single_file(path):

    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    result = ds.get("test-annex.dat")
    eq_(len(result), 1)
    eq_(result[0]['file'], 'test-annex.dat')
    ok_(result[0]['success'] is True)
    eq_(result[0]['key'], ds.repo.get_file_key('test-annex.dat'))
    ok_(ds.repo.file_has_content('test-annex.dat') is True)


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
    urls = [RI(url + f) for f in file_list]

    # prepare origin
    origin = Dataset(path).create(force=True)
    origin.add(file_list)
    origin.save("initial")

    ds = install(ds_dir, source=path)

    # no content present:
    ok_(not any(ds.repo.file_has_content(file_list)))

    # get two plus an invalid one:
    with assert_raises(IncompleteResultsError) as cme:
        ds.get(['file1.txt', 'file2.txt', 'not_existing.txt'])
    result = cme.exception.results
    # explicitly given not existing file was skipped:
    # (see test_get_invalid_call)
    eq_(set([item.get('file') for item in result]),
        {'file1.txt', 'file2.txt'})
    ok_(all([x['success'] is True
             for x in result if x['file'] in ['file1.txt', 'file2.txt']]))
    ok_(all(ds.repo.file_has_content(['file1.txt', 'file2.txt'])))

    # get all of them:
    result = ds.get(curdir)
    # there were two files left to get:
    eq_(set([item.get('file') for item in result]),
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
    origin.save("Initial", auto_add_changes=True)

    ds = install(c_path, source=o_path)

    file_list = ['file1.txt',
                 opj('subdir', 'file2.txt'),
                 opj('subdir', 'subsubdir', 'file3.txt'),
                 opj('subdir', 'subsubdir', 'file4.txt')]
    files_in_sub = [f for f in file_list if f.startswith(with_pathsep('subdir'))]

    # no content present:
    ok_(not any(ds.repo.file_has_content(file_list)))

    result = ds.get('subdir')

    # check result:
    eq_(set([item.get('file') for item in result]),
        set(files_in_sub))
    ok_(all([x['success'] is True for x in result if x['file'] in files_in_sub]))
    eq_(len(result), len(files_in_sub))

    # got all files beneath subdir:
    ok_(all(ds.repo.file_has_content(files_in_sub)))

    # additionally got file1.txt silently, since it has the same content as
    # subdir/subsubdir/file4.txt:
    ok_(ds.repo.file_has_content('file1.txt') is True)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_recurse_subdatasets(src, path):

    ds = install(path, source=src)

    # ask for the two subdatasets specifically. This will obtain them,
    # but not any content of any files in them
    subds1, subds2 = ds.get(['subm 1', 'subm 2'], get_data=False)

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

    # explicitly given path in subdataset => implicit recursion:
    # MIH: Nope, we fulfill the dataset handle, but that doesn't
    #      imply fulfilling all file handles
    result = ds.get(rel_path_sub1, recursive=True)

    eq_(result[0].get('file'), rel_path_sub1)
    ok_(result[0].get('success', False) is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)

    # drop it:
    subds1.repo.drop('test-annex.dat')
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)

    # now, with a path not explicitly pointing within a
    # subdataset, but recursive option:
    # get everything:
    result = ds.get('.', recursive=True)

    eq_(set([item.get('file') for item in result]), annexed_files)
    ok_(all(item.get('success', False) for item in result))
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
    eq_(len(result), 1)
    eq_(result[0]['file'], 'test-annex.dat')
    ok_(result[0]['success'] is True)
    ok_(ds.repo.file_has_content('test-annex.dat') is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)
    ok_(subds2.repo.file_has_content('test-annex.dat') is False)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_greedy_recurse_subdatasets(src, path):

    ds = install(path, source=src)

    # GIMME EVERYTHING
    ds.get(['subm 1', 'subm 2'])

    # We got all content in the subdatasets
    subds1, subds2 = [Dataset(d) for d in ds.get_subdatasets(absolute=True)]
    ok_(ds.repo.file_has_content('test-annex.dat') is False)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)
    ok_(subds2.repo.file_has_content('test-annex.dat') is True)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_get_install_missing_subdataset(src, path):

    ds = install(path, source=src)
    subs = [Dataset(s_path) for s_path in ds.get_subdatasets(absolute=True)]
    ok_(all([not sub.is_installed() for sub in subs]))

    # we don't install anything, if no explicitly given path points into a
    # not yet installed subdataset:
    ds.get(curdir)
    ok_(all([not sub.is_installed() for sub in subs]))

    # but we do, whenever a given path is contained in such a subdataset:
    file = opj(subs[0].path, 'test-annex.dat')
    ds.get(file)
    ok_(subs[0].is_installed())
    ok_(subs[0].repo.file_has_content('test-annex.dat') is True)

    # but we fulfill any handles, and dataset handles too
    ds.get(curdir, recursive=True)
    ok_(all([sub.is_installed() for sub in subs]))


# @with_tree(tree={'file_in_git.txt': 'no idea',
#                  'subds': {'file_in_annex.txt': 'content'}})
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_mixed_hierarchy(src, path):

    origin = Dataset(src).create(no_annex=True)
    origin_sub = origin.create('subds')
    with open(opj(origin.path, 'file_in_git.txt'), "w") as f:
        f.write('no idea')
    with open(opj(origin_sub.path, 'file_in_annex.txt'), "w") as f:
        f.write('content')
    origin.add('file_in_git.txt', to_git=True)
    origin_sub.add('file_in_annex.txt')
    origin.save(auto_add_changes=True)

    # now, install that thing:
    ds, subds = install(path, source=src, recursive=True)
    ok_(subds.repo.file_has_content("file_in_annex.txt") is False)

    # and get:
    with swallow_logs(new_level=logging.DEBUG) as cml:
        result = ds.get(curdir, recursive=True)
        assert_re_in('.*Found no annex at {0}. Skipped.'.format(ds),
                     cml.out, flags=re.DOTALL)
        eq_(len(result), 1)
        eq_(result[0]['file'], opj("subds", "file_in_annex.txt"))
        ok_(result[0]['success'] is True)
        ok_(subds.repo.file_has_content("file_in_annex.txt") is True)


@with_testrepos('submodule_annex', flavors='local')
@with_tempfile(mkdir=True)
def test_autoresolve_multiple_datasets(src, path):
    with chpwd(path):
        ds1 = install('ds1', source=src)
        ds2 = install('ds2', source=src)
        results = get([opj('ds1', 'test-annex.dat')] + glob(opj('ds2', '*.dat')))
        # each ds has one file
        eq_(len(results), 2)
        ok_(ds1.repo.file_has_content('test-annex.dat') is True)
        ok_(ds2.repo.file_has_content('test-annex.dat') is True)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_autoresolve_recurse_subdatasets(src, path):

    origin = Dataset(src).create()
    origin_sub = origin.create('sub')
    origin_subsub = origin_sub.create('subsub')
    with open(opj(origin_subsub.path, 'file_in_annex.txt'), "w") as f:
        f.write('content')
    origin.save(recursive=True, auto_add_changes=True)

    ds = install(path, source=src)
    eq_(len(ds.get_subdatasets(fulfilled=True)), 0)

    results = get(opj(ds.path, 'sub'), recursive=True)
    eq_(len(ds.get_subdatasets(fulfilled=True, recursive=True)), 2)
    subsub = Dataset(opj(ds.path, 'sub', 'subsub'))
    ok_(subsub.is_installed())
    assert_in(subsub, results)
    # all file handles are fulfilled by default
    ok_(Dataset(opj(ds.path, 'sub', 'subsub')).repo.file_has_content(
        "file_in_annex.txt") is True)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_recurse_existing(src, path):
    origin_ds = _make_dataset_hierarchy(src)

    # make sure recursion_limit works as expected across a range of depths
    for depth in range(len(origin_ds)):
        datasets = assure_list(
            install(path, source=src, recursive=True, recursion_limit=depth))
        # we expect one dataset per level
        eq_(len(datasets), depth + 1)
        rmtree(path)

    # now install all but the last two levels, no data
    root, sub1, sub2 = install(path, source=src, recursive=True, recursion_limit=2)
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is False)
    sub3 = Dataset(opj(sub2.path, 'sub3'))
    ok_(not sub3.is_installed())
    # now get all content in all existing datasets, no new datasets installed
    # in the process
    files = root.get(curdir, recursive=True, recursion_limit='existing')
    eq_(len(files), 1)
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is True)
    ok_(not sub3.is_installed())
    # now pull down all remaining datasets, no data
    sub3, sub4 = root.get(curdir, recursive=True, get_data=False)
    ok_(sub4.is_installed())
    ok_(sub3.repo.file_has_content('file_in_annex.txt') is False)
    # aaannd all data
    files = root.get(curdir, recursive=True)
    eq_(len(files), 1)
    ok_(sub3.repo.file_has_content('file_in_annex.txt') is True)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_get_in_unavailable_subdataset(src, path):
    origin_ds = _make_dataset_hierarchy(src)
    root = install(path, source=src)
    targetpath = opj('sub1', 'sub2')
    targetabspath = opj(root.path, targetpath)
    get(targetabspath)
    # we got the dataset, and its immediate content, but nothing below
    sub2 = Dataset(targetabspath)
    ok_(sub2.is_installed())
    ok_(sub2.repo.file_has_content('file_in_annex.txt') is True)
    ok_(not Dataset(opj(targetabspath, 'sub3')).is_installed())
