# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test uninstall action

"""

from os.path import join as opj
from os.path import exists

from datalad.api import uninstall
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import assert_in

from ..dataset import Dataset


@with_testrepos('.*basic.*', flavors=['local'])
def test_uninstall_invalid(path):

    assert_raises(InsufficientArgumentsError, uninstall)

    res = uninstall(dataset=Dataset(path), path='not_existent')
    ok_(res is None)

    with assert_raises(ValueError) as cme:
        uninstall(dataset=Dataset(path))
        eq_("No dataset found to uninstall %s from." % path, str(cme))


@with_testrepos('basic_annex', flavors=['clone'])
def test_uninstall_annex_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_file_under_git(path, 'test-annex.dat', annexed=True)
    ds.repo.get('test-annex.dat')
    ok_(ds.repo.file_has_content('test-annex.dat'))

    # remove file's content:
    res = ds.uninstall(path='test-annex.dat', data_only=True)
    # test it happened:
    ok_(not ds.repo.file_has_content('test-annex.dat'))
    ok_file_under_git(path, 'test-annex.dat', annexed=True)
    # test result:
    eq_(res, ['test-annex.dat'])

    ds.repo.get('test-annex.dat')

    # remove file:
    ds.uninstall(path='test-annex.dat')
    assert_raises(AssertionError, ok_file_under_git, path, 'test-annex.dat',
                  annexed=True)
    assert_raises(AssertionError, ok_file_under_git, path, 'test-annex.dat',
                  annexed=False)
    ok_(not exists(opj(path, 'test-annex.dat')))


@with_testrepos('.*basic.*', flavors=['clone'])
def test_uninstall_git_file(path):
    ds = Dataset(path)
    ok_(ds.is_installed())
    ok_(exists(opj(path, 'INFO.txt')))
    ok_file_under_git(path, 'INFO.txt')

    # uninstalling data only doesn't make sense:
    assert_raises(ValueError, ds.uninstall, path='INFO.txt', data_only=True)

    # uninstall removes the file:
    res = ds.uninstall(path='INFO.txt')
    assert_raises(AssertionError, ok_file_under_git, path, 'INFO.txt')
    ok_(not exists(opj(path, 'INFO.txt')))
    eq_(res, ['INFO.txt'])


def test_uninstall_dataset():
    raise SkipTest("TODO")


def test_uninstall_subdataset():
    raise SkipTest("TODO")


def test_uninstall_recursive():
    raise SkipTest("TODO")

