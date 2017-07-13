# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target github"""

from os.path import join as opj
# this must with with and without pygithub
from datalad.api import create_sibling_github
from datalad.api import Dataset
from datalad.support.exceptions import MissingExternalDependency
from datalad.tests.utils import with_tempfile
from nose.tools import assert_raises, assert_in, assert_true, assert_false, \
    assert_not_in, assert_equal
from nose import SkipTest


try:
    import github as gh
except ImportError:
    # make sure that the command complains too
    assert_raises(MissingExternalDependency, create_sibling_github, 'some')
    raise SkipTest


@with_tempfile
def test_invalid_call(path):
    # no dataset
    assert_raises(ValueError, create_sibling_github, 'bogus', dataset=path)
    ds = Dataset(path).create()
    # no user
    assert_raises(gh.BadCredentialsException, ds.create_sibling_github, 'bogus', github_login='disabledloginfortesting')


@with_tempfile
def test_dont_trip_over_missing_subds(path):
    ds1 = Dataset(opj(path, 'ds1')).create()
    ds2 = Dataset(opj(path, 'ds2')).create()
    subds2 = ds1.install(
        source=ds2.path, path='subds2',
        result_xfm='datasets', return_type='item-or-list')
    assert_true(subds2.is_installed())
    assert_in('subds2', ds1.subdatasets(result_xfm='relpaths'))
    subds2.uninstall()
    assert_in('subds2', ds1.subdatasets(result_xfm='relpaths'))
    assert_false(subds2.is_installed())
    # see if it wants to talk to github (and fail), or if it trips over something
    # before
    assert_raises(gh.BadCredentialsException, ds1.create_sibling_github, 'bogus', recursive=True, github_login='disabledloginfortesting')
    # inject remote config prior run
    assert_not_in('github', ds1.repo.get_remotes())
    # fail on existing
    ds1.repo.add_remote('github', 'http://nothere')
    assert_raises(ValueError, ds1.create_sibling_github, 'bogus', recursive=True, github_login='disabledloginfortesting')
    # talk to github when existing is OK
    assert_raises(gh.BadCredentialsException, ds1.create_sibling_github, 'bogus', recursive=True, github_login='disabledloginfortesting', existing='reconfigure')
    # return happy emptiness when all is skipped
    assert_equal(ds1.create_sibling_github('bogus', recursive=True, github_login='disabledloginfortesting', existing='skip'), [])
