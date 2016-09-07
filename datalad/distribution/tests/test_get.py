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


@with_tempfile(mkdir=True)
def test_get_invalid_call(path):

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

    # TODO: Don't know why cml.out is empty, while this works via cmdline ...
    # with swallow_logs() as cml:
    #     ds.get("NotExistingFile.txt")
    #     assert_in("NotExistingFile.txt not found. Ignored.", cml.out)

    # TODO: Same test for a file in subdataset without recursive

    # path outside repo:
    result = ds.get(opj(pardir, "doesntmatter.dat"))
    eq_(len(result), 0)


    # TODO: annex --json doesn't report anything when get fails to do get a
    # file from a specified source, where the file isn't available from.
    # File report for Joey (plus other failures like not existing when
    # called with --json)


@with_testrepos('basic_annex', flavors='clone')
def test_get_single_file(path):

    ds = Dataset(path)
    ok_(ds.repo.file_has_content('test-annex.dat')[0] is False)
    result = ds.get("test-annex.dat")
    eq_(len(result), 1)
    eq_(result[0]['file'], 'test-annex.dat')
    ok_(result[0]['success'] is True)
    eq_(result[0]['key'], ds.repo.get_file_key('test-annex.dat'))
    ok_(ds.repo.file_has_content('test-annex.dat')[0] is True)


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
             for x in result if x['file']]))
    ok_(all(ds.repo.file_has_content(['file1.txt', 'file2.txt'])))

    # get all of them:
    result = ds.get(curdir)
    # there were two files left to get:
    eq_(set([item.get('file') for item in result]),
        {'file3.txt', 'file4.txt'})
    ok_(all(ds.repo.file_has_content(file_list)))


def test_get_recurse_dirs():
    raise SkipTest("TODO")


def test_get_recurse_subdatasets():
    raise SkipTest("TODO")


def test_get_install_missing_subdataset():
    raise SkipTest("TODO")
