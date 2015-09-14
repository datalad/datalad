# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test proxying of core IO operations
"""

import os
from os.path import join as opj, dirname
from .utils import with_testrepos, assert_raises, eq_
from .utils import swallow_outputs

from ..auto import AutomagicIO

from ..support.annexrepo import AnnexRepo

@with_testrepos('basic', flavors=['network-clone',
                                  'clone'
                                  ])
def test_proxying_open(repo):
    TEST_CONTENT = "123\n"
    fname = 'test-annex.dat'
    fpath = opj(repo, fname)
    assert_raises(IOError, open, fpath)

    aio = AutomagicIO(activate=True)
    try:
        with swallow_outputs():
            # now we should be able just to request to open this file
            with open(fpath) as f:
                content = f.read()
                eq_(content, TEST_CONTENT)
    finally:
        aio.deactivate()

    # and now that we have fetched it, nothing should forbid us to open it again
    with open(fpath) as f:
        eq_(f.read(), TEST_CONTENT)

    annex = AnnexRepo(repo, create=False)
    # Let's create another file deeper under the directory with the same content
    # so it would point to the same key, which we would drop and repeat the drill
    fpath2 = opj(repo, 'd1', 'd2', 'test2.dat')
    os.makedirs(dirname(fpath2))
    with open(fpath2, 'w') as f:
        f.write(content)
    annex.annex_add(fpath2)
    annex.annex_drop(fpath2)
    annex.git_commit("added and dropped")
    assert_raises(IOError, open, fpath2)

    aio = AutomagicIO(activate=True)
    try:
        with swallow_outputs():
            # now we should be able just to request to open this file
            with open(fpath2) as f:
                content = f.read()
                eq_(content, TEST_CONTENT)
    finally:
        aio.deactivate()
