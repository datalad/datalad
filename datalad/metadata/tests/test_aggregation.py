# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test meta data manipulation"""


import os
from os.path import join as opj
from os.path import exists

from datalad.api import metadata
from datalad.distribution.dataset import Dataset
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from datalad.utils import chpwd

from datalad.tests.utils import create_tree
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_dict_equal
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import skip_direct_mode


@with_tempfile(mkdir=True)
@skip_direct_mode  #FIXME
def test_basic_aggregate(path):
    base = Dataset(path).create()
    sub = base.create('sub')
    base.metadata(sub.path, init=dict(homepage='this'), apply2global=True)
    subsub = base.create(opj('sub', 'subsub'))
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True)
    ok_clean_git(base.path)
    direct_meta = base.metadata(sub.path, return_type='item-or-list')
    # no we can throw away the subdataset tree, and loose no metadata
    base.uninstall('sub', recursive=True)
    assert(not sub.is_installed())
    ok_clean_git(base.path)
    # same result for aggregate query than for (saved) direct query
    agg_meta = base.metadata(sub.path, return_type='item-or-list')
    assert_dict_equal(direct_meta, agg_meta)
