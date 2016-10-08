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
from os.path import join as opj

from datalad.api import get
from datalad.api import install
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import CommandNotAvailableError
from datalad.support.exceptions import RemoteNotAvailableError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import assert_re_in
from datalad.utils import swallow_logs, with_pathsep

from ..dataset import Dataset
from ..dataset import with_pathsep


@with_tempfile(mkdir=True)
@with_tempfile(content="doesntmatter")
def test_get_invalid_call(path, file_outside):

    # no argument at all:
    assert_raises(InsufficientArgumentsError, get)
    # invalid dataset:
    assert_raises(ValueError, get, dataset=path)

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
    with swallow_logs(new_level=logging.WARNING) as cml:
        # but we don't fail if not annex -- just inform
        out = ds.get(curdir)
        assert_in('Found no annex. Could not perform any get operation.',
                  cml.out)
        eq_(out, [])

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
        result = ds.get("NotExistingFile.txt")
        eq_(len(result), 0)
        assert_in("NotExistingFile.txt not found. Ignored.", cml.out)

    # path outside repo:
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(file_outside)
        eq_(len(result), 0)
        assert_in("path {0} not within repository {1}".format(file_outside, ds),
                  cml.out)

    # TODO: annex --json doesn't report anything when get fails to do get a
    # file from a specified source, where the file isn't available from.
    # File report for Joey (plus other failures like not existing when
    # called with --json)


@with_testrepos('basic_annex', flavors='clone')
def test_get_single_file(path):

    ds = Dataset(path)
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
    result = ds.get(['file1.txt', 'file2.txt', 'not_existing.txt'])
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

    ds, subds1, subds2 = install(path=path, source=src, recursive=True)

    # there are 3 files to get: test-annex.dat within each dataset:
    from os.path import basename
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
    result = ds.get(rel_path_sub1)

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
def test_get_install_missing_subdataset(src, path):

    ds = install(path=path, source=src)
    ds.create(force=True)  # force, to cause dataset initialization
    subs = [Dataset(s_path) for s_path in ds.get_subdatasets(absolute=True)]
    ok_(all([not sub.is_installed() for sub in subs]))

    # we don't install anything, if no explicitly given path points into a
    # not yet installed subdataset:
    ds.get(curdir)
    ok_(all([not sub.is_installed() for sub in subs]))

    # with no such paths, we also don't install when recursive is used - it just
    # means to recursively include subdatasets in the get operation:
    ds.get(curdir, recursive=True)
    ok_(all([not sub.is_installed() for sub in subs]))

    # but we do, whenever a given path is contained in such a subdataset:
    file = opj(subs[0].path, 'test-annex.dat')
    ds.get(file)
    ok_(subs[0].is_installed())
    ok_(subs[0].repo.file_has_content('test-annex.dat') is True)


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
    ds, subds = install(path=path, source=src, recursive=True)
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
