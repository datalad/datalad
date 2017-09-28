# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad unlock

"""

__docformat__ = 'restructuredtext'

import logging
from os import geteuid
from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.api import unlock
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import eq_
from datalad.tests.utils import getpwd
from datalad.tests.utils import chpwd
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import assert_in
from datalad.tests.utils import on_windows, skip_if
from datalad.utils import swallow_logs


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def test_unlock_raises(path, path2, path3):

    # make sure, we are not within a dataset:
    _cwd = getpwd()
    chpwd(path)

    # no dataset and no path:
    assert_raises(InsufficientArgumentsError,
                  unlock, dataset=None, path=None)
    # no dataset and path not within a dataset:
    res = unlock(dataset=None, path=path2, result_xfm=None,
                 on_failure='ignore', return_type='item-or-list')
    eq_(res['message'], "path not associated with any dataset")
    eq_(res['path'], path2)

    create(path=path, no_annex=True)
    ds = Dataset(path)
    # no complaints
    ds.unlock()

    # make it annex, but call unlock with invalid path:
    AnnexRepo(path, create=True)
    res = ds.unlock(path="notexistent.txt", result_xfm=None,
                    on_failure='ignore', return_type='item-or-list')
    eq_(res['message'], "path does not exist")

    chpwd(_cwd)


# Note: As root there is no actual lock/unlock.
#       Therefore don't know what to test for yet.
@skip_if(cond=not on_windows and geteuid() == 0)  # uid not available on windows
@with_testrepos('.*annex.*', flavors=['clone'])
def test_unlock(path):

    ds = Dataset(path)

    # file is currently locked:
    # TODO: use get_annexed_files instead of hardcoded filename
    assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

    from datalad.tests.utils import assert_status, assert_result_count, assert_in_results, assert_not_in_results, assert_result_values_equal
    if ds.repo.is_direct_mode():
        res = ds.unlock()
        assert_result_count(res, 1)
        assert_status('notneeded', res)

    # TODO: What about V6? => You can unlock even if there's no content!
    else:
        # cannot unlock without content (annex get wasn't called)
        assert_raises(CommandError, ds.unlock)  # FIXME

    ds.repo.get('test-annex.dat')
    result = ds.unlock()
    assert_result_count(result, 1)
    if ds.repo.is_direct_mode():
        assert_status('notneeded', result)
    else:
        assert_in_results(result, path='test-annex.dat', status='ok')

    with open(opj(path, 'test-annex.dat'), "w") as f:
        f.write("change content")

    ds.repo.add('test-annex.dat')
    ds.repo.commit("edit 'test-annex.dat' via unlock and lock it again")

    if not ds.repo.is_direct_mode():
        # after commit, file is locked again:
        assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

    # content was changed:
    with open(opj(path, 'test-annex.dat'), "r") as f:
        eq_("change content", f.read())

    # unlock again, this time more specific:
    result = ds.unlock(path='test-annex.dat')
    assert_result_count(result, 1)

    # TODO: Why in the following result there is the absolute path in direct mode
    # while it's the relative one in indirect mode?
    # Probably:
    # => direct mode: no actual call to annex-unlock
    # => indirect mode: it's what AnnexRepo.unlock returns
    if ds.repo.is_direct_mode():
        assert_in_results(result, path=opj(ds.path, 'test-annex.dat'), status='notneeded')
    else:
        assert_in_results(result, path='test-annex.dat', status='ok')

    with open(opj(path, 'test-annex.dat'), "w") as f:
        f.write("change content again")

    ds.repo.add('test-annex.dat')
    ds.repo.commit("edit 'test-annex.dat' via unlock and lock it again")

    if not ds.repo.is_direct_mode():
        # after commit, file is locked again:
        assert_raises(IOError, open, opj(path, 'test-annex.dat'), "w")

    # content was changed:
    with open(opj(path, 'test-annex.dat'), "r") as f:
        eq_("change content again", f.read())


