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
from __future__ import unicode_literals

__docformat__ = 'restructuredtext'

import os
import stat
from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.api import (
    clone,
    install,
    open,
)
from datalad.support.path import (
    exists,
    join as opj,
)
from datalad.tests.utils import (
    assert_cwd_unchanged,
    chpwd,
    create_tree,
    eq_,
    ok_,
    nok_,
    ok_clean_git,
    ok_file_has_content,
    ok_file_under_git,
    with_tree,
)

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

    # Let's test for error being "handled" separately
    cm = ds.open("in-git")
    try:
        with cm as f:
            raise RuntimeError("Evil exception which should abort everything")
    except RuntimeError:
        pass
    eq_(cm.all_results[-1]['status'], 'error')
    eq_(len(cm.all_results[-1]['exception']), 3)  # all details of the exception


@with_sample_ds
def test_rewrite(ds):
    in_annex = opj(ds.path, 'in-annex')
    in_git = opj(ds.path, 'in-git')
    new_file = opj(ds.path, 'new_file')
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

    # in-git change and also check that we transfer executable permission
    os.chmod(in_git, os.stat(in_git).st_mode | stat.S_IEXEC)
    assert os.stat(in_git).st_mode & stat.S_IEXEC
    with ds.open('in-git', 'w') as f:
        f.write("1")
    assert os.stat(in_git).st_mode & stat.S_IEXEC
    ok_file_under_git(in_git, annexed=True) # Automigrates to annex! both with add or save
    ok_file_has_content(in_git, "1")
    ok_clean_git(ds.repo, untracked=['untracked'])

    # New file and we will test with full path
    with ds.open(new_file, "w") as f:
        f.write("1")
    ok_file_under_git(new_file, annexed=True)
    ok_file_has_content(new_file, "1")
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

    # test a dummy custom "open" to make sure that it is called appropriately
    calls = []

    class myfile:
        def __init__(self, name):
            self.name = name
            self.closed = False
        def close(self):
            self.closed = True

    def myopen(f, mode, fancy1, fancy2=None, fullpath=True):
        if fullpath:  # e.g. when operating with ds.
            eq_(f, opj(ds.path, 'in-annex'))
        else:
            # Let's try to keep things relative... all the "fullpath"ing brings
            # cramps
            eq_(f, 'in-annex')
        eq_(mode, 'append')  # we do not care about anything but first letter
        eq_(fancy1, 1)
        eq_(fancy2, '2')
        calls.append("ok")
        return myfile(f)

    with ds.open('in-annex', 'append', callable=myopen, fancy2='2', fancy1=1, fullpath=True) as f:
        assert isinstance(f, myfile)
        nok_(f.closed)
        eq_(calls, ['ok'])
    ok_(f.closed)

    # and now with relative path
    with chpwd(ds.path):
        with open('in-annex', 'append', callable=myopen, fancy2='2', fancy1=1, fullpath=False) as f:
            assert isinstance(f, myfile)
            nok_(f.closed)
            eq_(calls, ['ok', 'ok'])
    ok_(f.closed)
