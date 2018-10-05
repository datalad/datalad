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
from datalad.api import (
    clone,
    install,
    open,
)
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.utils import chpwd
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_raises
from datalad.tests.utils import eq_
from datalad.tests.utils import getpwd
from datalad.tests.utils import chpwd
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import on_windows, skip_if
from datalad.tests.utils import assert_status, assert_result_count, assert_in_results
from datalad.tests.utils import (
    ok_file_has_content,
    ok_file_under_git,
    ok_clean_git,
)
from datalad.support.path import exists, join as opj

from functools import wraps


def with_sample_ds(t):
    """A "fixture" for the tests to provide a sample dataset
    """
    @wraps(t)
    @assert_cwd_unchanged
    @with_tree(tree={
        'ds': {
            'in-annex': '',
            'in-git': 'text',
            'untracked': 'untracked',
        # TODO: open of 'untracked' and 'outside' aren't "supported" yet
        },
        'outside': 'content'
    })
    def wrapped(path):
        ds_orig = Dataset(opj(path, 'ds')).create(
            # Causes BK TODO https://github.com/datalad/datalad/issues/1651
            # text_no_annex=True,
            force=True)
        ds_orig.add('in-annex')
        ds_orig.add('in-git', to_git=True)
        # bleh -- clone in Python API we return the records, even with
        # return_type
        # ds = clone(path, path + '-clone', return_type='item-or-list')
        ds = install(ds_orig.path + '-clone', source=ds_orig)
        create_tree(ds.path, {'untracked': 'untracked'})
        return t(ds)
    return wrapped


@with_sample_ds
def test_read(ds):
    in_annex = opj(ds.path, 'in-annex')

    assert not exists(in_annex)
    with ds.open('in-annex') as f:
        eq_(f.read(), '')
    with ds.open('in-git') as f:
        eq_(f.read(), 'text')

    ds.drop('in-annex')
    assert not exists(in_annex)  # never know for sure with all those generators etc
    # multiple at once, including untracked
    with ds.open(['in-annex', 'in-git']) as (f1, f2):
        eq_(f1.read(), '')
        eq_(f2.read(), 'text')
    ds.drop('in-annex')

    # TODO: make code work also with 'untracked' and 'outside'

    # Let's test with full and local paths and also explicit mode and buffering
    with chpwd(ds.path):
        with open((in_annex, 'in-git'), 'r', buffering=1) as (f1, f2):
            eq_(f1.read(), '')
            eq_(f2.read(), 'text')


@with_sample_ds
def test_rewrite(ds):
    in_annex = opj(ds.path, 'in-annex')
    in_git = opj(ds.path, 'in-git')
    ok_clean_git(ds.repo, untracked=['untracked'])

    assert not exists(in_annex)
    with ds.open('in-annex', 'w') as f:
        f.write("stuff")
    ok_file_has_content(in_annex, "stuff")
    ok_file_under_git(in_annex, annexed=True)
    ok_clean_git(ds.repo, untracked=['untracked'])

    # We cannot drop since modified
    with ds.open('in-annex', 'w') as f:
        f.write("1")
        f.write("2")
    ok_file_under_git(in_annex, annexed=True)
    ok_file_has_content(in_annex, "12")
    ok_clean_git(ds.repo, untracked=['untracked'])

    with ds.open('in-git', 'w') as f:
        f.write("1")
    ok_file_under_git(in_git, annexed=True) # Automigrates to annex! both with add or save
    ok_file_has_content(in_git, "1")
    ok_clean_git(ds.repo, untracked=['untracked'])

    # TODO: test that commit messages could be passed and save=False
    #  could be of effect
    # # TODO: make code work also with 'untracked' and 'outside'


# TODO: RF - a copy of the above with only mode and content difference
@with_sample_ds
def test_append(ds):
    in_annex = opj(ds.path, 'in-annex')
    in_git = opj(ds.path, 'in-git')
    ok_clean_git(ds.repo, untracked=['untracked'])

    assert not exists(in_annex)
    with ds.open('in-annex', 'a') as f:
        f.write("stuff")
    ok_file_has_content(in_annex, "stuff")
    ok_file_under_git(in_annex, annexed=True)
    ok_clean_git(ds.repo, untracked=['untracked'])

    # We cannot drop since modified
    with ds.open('in-annex', 'a') as f:
        f.write("1")
        f.write("2")
    ok_file_under_git(in_annex, annexed=True)
    ok_file_has_content(in_annex, "stuff12")
    ok_clean_git(ds.repo, untracked=['untracked'])

    with ds.open('in-git', 'a') as f:
        f.write("1")
    ok_file_under_git(in_git, annexed=True) # Automigrates to annex! both with add or save
    ok_file_has_content(in_git, "text1")
    ok_clean_git(ds.repo, untracked=['untracked'])

    # # TODO: make code work also with 'untracked' and 'outside'
