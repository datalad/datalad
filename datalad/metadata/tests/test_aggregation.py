# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test metadata manipulation"""


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


_dataset_hierarchy_template = {
    'origin': {
        'dataset_description.json': """
{
    "Name": "mother_äöü東"
}""",
        'sub': {
            'dataset_description.json': """
{
    "Name": "child_äöü東"
}""",
            'subsub': {
                'dataset_description.json': """
            {
    "Name": "grandchild_äöü東"
}"""}}}}


@with_tree(tree=_dataset_hierarchy_template)
@skip_direct_mode  #FIXME
def test_basic_aggregate(path):
    # TODO give datasets some more metadata to actually aggregate stuff
    base = Dataset(opj(path, 'origin')).create(force=True)
    sub = base.create('sub', force=True)
    base.metadata(sub.path, init=dict(homepage='this'), apply2global=True)
    subsub = base.create(opj('sub', 'subsub'), force=True)
    base.add('.', recursive=True)
    ok_clean_git(base.path)
    base.aggregate_metadata(recursive=True)
    ok_clean_git(base.path)
    direct_meta = base.metadata(recursive=True, return_type='list')
    # loose the deepest dataset
    sub.uninstall('subsub', check=False)
    # no we should eb able to reaggregate metadata, and loose nothing
    # because we can aggregate aggregated metadata of subsub from sub
    base.aggregate_metadata(recursive=True)
    # same result for aggregate query than for (saved) direct query
    agg_meta = base.metadata(recursive=True, return_type='list')
    for d, a in zip(direct_meta, agg_meta):
        print(d['path'], a['path'])
        assert_dict_equal(d, a)
    # no we can throw away the subdataset tree, and loose no metadata
    base.uninstall('sub', recursive=True, check=False)
    assert(not sub.is_installed())
    ok_clean_git(base.path)
    # same result for aggregate query than for (saved) direct query
    agg_meta = base.metadata(recursive=True, return_type='list')
    for d, a in zip(direct_meta, agg_meta):
        assert_dict_equal(d, a)
