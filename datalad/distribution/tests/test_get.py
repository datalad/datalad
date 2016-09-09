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

from os import curdir
from os import pardir
from os.path import join as opj

from datalad.api import create
from datalad.api import get
from datalad.api import add
from datalad.api import save
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import CommandNotAvailableError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tree
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.tests.utils import serve_path_via_http
from datalad.utils import chpwd
from datalad.utils import swallow_logs

from ..dataset import Dataset
from ..dataset import _with_sep


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
    assert_raises(CommandNotAvailableError, ds.get, "some.txt")

    # make it an annex:
    AnnexRepo(path, init=True, create=True)
    # call get again on a file in git:
    result = ds.get("some.txt")
    # skipped silently, but no result for this file:
    eq_(len(result), 0)

    # invalid source:
    with assert_raises(CommandError) as ce:
        ds.get("some.txt", source='MysteriousRemote')
    assert_in("git-annex: there is no available git remote named "
              "\"MysteriousRemote\"", ce.exception.stderr)

    # warning on not existing file:
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get("NotExistingFile.txt")
        eq_(len(result), 0)
        assert_in("NotExistingFile.txt not found. Ignored.", cml.out)

    # path in subdataset, but not called with recursive=True:
    subds = ds.create_subdataset('sub')
    with open(opj(subds.path, 'newfile.dat'), "w") as f:
        f.write("something")
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(opj('sub', 'newfile.dat'))
        eq_(len(result), 0)
        assert_in("newfile.dat belongs to subdataset %s" % subds, cml.out)

    # path outside repo:
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(file_outside)
        eq_(len(result), 0)
        assert_in("path {0} not in dataset {1}".format(file_outside, ds),
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

    # clone it: (TODO: use install here, once it is redone)
    AnnexRepo(ds_dir, path, create=True)
    ds = Dataset(ds_dir)

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

    # clone it: (TODO: use install here, once it is redone)
    AnnexRepo(c_path, o_path, create=True)
    ds = Dataset(c_path)

    file_list = ['file1.txt',
                 opj('subdir', 'file2.txt'),
                 opj('subdir', 'subsubdir', 'file3.txt'),
                 opj('subdir', 'subsubdir', 'file4.txt')]
    files_in_sub = [f for f in file_list if f.startswith(_with_sep('subdir'))]

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


@with_testrepos('submodule_annex', flavors='clone')
def test_get_recurse_subdatasets(path):

    # just cloned, not installed, so annex-init it:
    # TODO: use install, once it has been fixed.
    repo = AnnexRepo(path, init=True)
    repo.update_submodule('subm 1', init=True)
    repo.update_submodule('subm 2', init=True)

    ds = Dataset(path)
    subds1 = Dataset(opj(path, 'subm 1'))
    subds2 = Dataset(opj(path, 'subm 2'))

    # call with path in submodule, but without 'recursive':
    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(opj('subm 1', 'test-annex.dat'))
        eq_(len(result), 0)
        assert_in("{0} belongs to subdataset {1}".format(
            opj('subm 1', 'test-annex.dat'), subds1), cml.out)

    # now with recursive option:
    result = ds.get(opj('subm 1', 'test-annex.dat'), recursive=True)

    eq_(result[0].get('file'), opj('subm 1', 'test-annex.dat'))
    ok_(result[0].get('success', False) is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)

    # drop it:
    subds1.repo.drop('test-annex.dat')
    ok_(subds1.repo.file_has_content('test-annex.dat') is False)

    # get everything:
    # there are 3 files to get: test-annex.dat within each dataset:
    annexed_files = {'test-annex.dat',
                     opj('subm 1', 'test-annex.dat'),
                     opj('subm 2', 'test-annex.dat')}

    result = ds.get('.', recursive=True)

    eq_(set([item.get('file') for item in result]), annexed_files)
    ok_(all(item.get('success', False) for item in result))
    ok_(ds.repo.file_has_content('test-annex.dat') is True)
    ok_(subds1.repo.file_has_content('test-annex.dat') is True)
    ok_(subds2.repo.file_has_content('test-annex.dat') is True)


def test_get_install_missing_subdataset():
    raise SkipTest("TODO")
