# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test dirty dataset handling

"""

__docformat__ = 'restructuredtext'

from os.path import join as opj
from nose.tools import assert_raises, assert_equal
from datalad.tests.utils import with_tempfile, assert_not_equal
from datalad.tests.utils import ok_clean_git
from datalad.interface.utils import handle_dirty_dataset
from datalad.distribution.dataset import Dataset
from datalad.api import save

_dirty_modes = ('fail', 'ignore', 'save-before')


def _check_all_clean(ds, state):
    assert state is not None
    for mode in _dirty_modes:
        # nothing wrong, nothing saved
        handle_dirty_dataset(ds, mode)
        assert_equal(state, ds.repo.get_hexsha())


def _check_auto_save(ds, orig_state):
    handle_dirty_dataset(ds, 'ignore')
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'fail')
    handle_dirty_dataset(ds, 'save-before')
    state = ds.repo.get_hexsha()
    assert_not_equal(orig_state, state)
    _check_all_clean(ds, state)
    return state


@with_tempfile(mkdir=True)
def test_dirty(path):
    for mode in _dirty_modes:
        # does nothing without a dataset
        handle_dirty_dataset(None, mode)
    # placeholder, but not yet created
    ds = Dataset(path)
    # unknown mode
    assert_raises(ValueError, handle_dirty_dataset, ds, 'MADEUP')
    # not yet created is very dirty
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'fail')
    handle_dirty_dataset(ds, 'ignore')
    assert_raises(RuntimeError, handle_dirty_dataset, ds, 'save-before')
    # should yield a clean repo
    ds.create()
    orig_state = ds.repo.get_hexsha()
    _check_all_clean(ds, orig_state)
    # tainted: untracked
    with open(opj(ds.path, 'something'), 'w') as f:
        f.write('some')
    orig_state = _check_auto_save(ds, orig_state)
    # tainted: staged
    with open(opj(ds.path, 'staged'), 'w') as f:
        f.write('some')
    ds.repo.add('staged', git=True)
    orig_state = _check_auto_save(ds, orig_state)
    # tainted: submodule
    # not added to super on purpose!
    subds = ds.create('subds')
    _check_all_clean(subds, subds.repo.get_hexsha())
    ok_clean_git(ds.path)
    # subdataset must be added as a submodule!
    assert_equal(ds.get_subdatasets(), ['subds'])
