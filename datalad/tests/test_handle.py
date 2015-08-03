# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class Handle

"""

import os.path
import platform

from nose.tools import assert_raises, assert_is_instance, assert_true, assert_equal, assert_false
from nose import SkipTest
from git.exc import GitCommandError

from ..support.handle import Handle
from ..support.exceptions import FileInGitError

from .utils import with_tempfile, with_testrepos, assert_cwd_unchanged, \
    ignore_nose_capturing_stdout, \
    on_windows, ok_clean_git, ok_clean_git_annex_proxy, \
    get_most_obscure_supported_name, swallow_outputs

from .utils import local_testrepo_flavors

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_Handle(src, dst):

    ds = Handle(dst, src)
    assert_is_instance(ds, Handle, "Handle was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.datalad')))

    #do it again should raise GitCommandError since git will notice there's already a git-repo at that path
    assert_raises(GitCommandError, Handle, dst, src)

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_Handle_direct(src, dst):

    ds = Handle(dst, src, direct=True)
    assert_is_instance(ds, Handle, "Handle was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.datalad')))
    assert_true(ds.is_direct_mode(), "Forcing direct mode failed.")
    

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
def test_Handle_instance_from_existing(path):

    gr = Handle(path)
    assert_is_instance(gr, Handle, "Handle was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_Handle_instance_brand_new(path):

    gr = Handle(path)
    assert_is_instance(gr, Handle, "Handle was not created.")
    assert_true(os.path.exists(os.path.join(path, '.datalad')))


@ignore_nose_capturing_stdout
@with_testrepos(flavors=['network'])
@with_tempfile
def test_Handle_get(src, dst):

    ds = Handle(dst, src)
    assert_is_instance(ds, Handle, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = os.path.join(dst, testfile)
    assert_false(ds.file_has_content("test-annex.dat"))
    with swallow_outputs() as cmo:
        ds.get(testfile)
    assert_true(ds.file_has_content("test-annex.dat"))
    f = open(testfile_abs, 'r')
    assert_equal(f.readlines(), ['123\n'], "test-annex.dat's content doesn't match.")


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_Handle_add_to_annex(src, dst):

    ds = Handle(dst, src)
    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_annex(filename)

    if not ds.is_direct_mode():
        assert_true(os.path.islink(filename_abs), "Annexed file is not a link.")
        ok_clean_git(dst, annex=True)
    else:
        assert_false(os.path.islink(filename_abs), "Annexed file is link in direct mode.")
        ok_clean_git_annex_proxy(dst)

    key = ds.get_file_key(filename)
    assert_false(key == '')
    # could test for the actual key, but if there's something and no exception raised, it's fine anyway.



@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_Handle__add_to_git(src, dst):

    ds = Handle(dst, src)

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_git(filename_abs)

    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(dst)
    else:
        ok_clean_git(dst, annex=True)
    assert_raises(FileInGitError, ds.get_file_key, filename)


@assert_cwd_unchanged
@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile
def test_Handle_commit(src, path):

    ds = Handle(path, src)
    filename = os.path.join(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.annex_add(filename)

    if ds.is_direct_mode():
        assert_raises(AssertionError, ok_clean_git_annex_proxy, path)
    else:
        assert_raises(AssertionError, ok_clean_git, path, annex=True)

    ds._commit("test _commit")
    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(path)
    else:
        ok_clean_git(path, annex=True)
