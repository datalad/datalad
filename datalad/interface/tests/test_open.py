# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad open

"""

__docformat__ = 'restructuredtext'

import os
from os.path import join as opj

from datalad.distribution.dataset import Dataset
import datalad.api as dl
from datalad.api import unlock
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import eq_
from datalad.tests.utils import getpwd
from datalad.tests.utils import chpwd
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import on_windows, skip_if
from datalad.tests.utils import assert_status, assert_result_count, assert_in_results


@assert_cwd_unchanged
@with_tree(tree={
    'in-annex': '',
    'in-git': 'text',
    'untracked': 'buga'
})
def test_open_read(path):
    ds = Dataset(path).create(text_no_annex=True, force=True)
    ds.add(['in-annex', 'in-git'])
    with dl.open('in-annex', return_type='generator') as f:
        eq_(f.read(), '')
    with dl.open('in-git') as f:
        eq_(f.read(), 'text')