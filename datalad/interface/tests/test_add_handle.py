# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for add-handle command

"""

__docformat__ = 'restructuredtext'

from os.path import basename, exists, isdir, join as opj
from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...api import add_handle, install_handle, register_collection
from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.handlerepo import HandleRepo
from ...support.collectionrepo import CollectionRepo, Collection, CollectionRepoBackend
from ...consts import REPO_CONFIG_FILE, REPO_STD_META_FILE


# test add-handle by passing paths to the function call:
@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile
@with_testrepos('.*collection.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_add_handle_by_paths(hurl, hpath, cpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        # get testrepos and make them known to datalad:
        handle = install_handle(hurl, hpath)
        collection = register_collection(cpath)
        assert_not_in(handle.name, collection)

        return_value = add_handle(hpath, cpath)

        # now handle is listed by collection:
        collection._reload()
        assert_in(handle.name, collection)

        # test collection repo:
        ok_clean_git(cpath, annex=False)
        ok_(isdir(opj(cpath, handle.name)))
        ok_(exists(opj(cpath, handle.name, REPO_CONFIG_FILE)))
        ok_(exists(opj(cpath, handle.name, REPO_STD_META_FILE)))

        # evaluate return value:
        assert_is_instance(return_value, Handle,
                           "install_handle() returns object of "
                           "incorrect class: %s" % type(return_value))
        eq_(return_value.name, handle.name)
        eq_(urlparse(return_value.url).path, urlparse(handle.url).path)


# test add-handle by passing names to the function call:
@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile
@with_testrepos('.*collection.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_add_handle_by_names(hurl, hpath, cpath, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        # get testrepos and make them known to datalad:
        handle = install_handle(hurl, hpath)
        collection = register_collection(cpath)
        assert_not_in(handle.name, collection)

        return_value = add_handle(handle.name, collection.name)

        # now handle is listed by collection:
        collection._reload()
        assert_in(handle.name, collection)

        # test collection repo:
        ok_clean_git(cpath, annex=False)
        ok_(isdir(opj(cpath, handle.name)))
        ok_(exists(opj(cpath, handle.name, REPO_CONFIG_FILE)))
        ok_(exists(opj(cpath, handle.name, REPO_STD_META_FILE)))

        # evaluate return value:
        assert_is_instance(return_value, Handle,
                           "install_handle() returns object of "
                           "incorrect class: %s" % type(return_value))
        eq_(return_value.name, handle.name)
        eq_(urlparse(return_value.url).path, urlparse(handle.url).path)


# TODO: Fix it; Currently fails:
# test add-handle and assign new name:
# @assert_cwd_unchanged
# @with_testrepos('.*annex_handle.*', flavors=['clone'])
# @with_tempfile
# @with_testrepos('.*collection.*', flavors=['clone'])
# @with_tempfile(mkdir=True)
# def test_add_handle_new_name(hurl, hpath, cpath, lcpath):
#
#     class mocked_dirs:
#         user_data_dir = lcpath
#
#     with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
#             swallow_logs() as cml:
#
#         # get testrepos and make them known to datalad:
#         handle = install_handle(hurl, hpath)
#         collection = register_collection(cpath)
#
#         new_name = handle.name + "_new"
#         assert_not_in(new_name, collection)
#
#         return_value = add_handle(handle.name, collection.name, name=new_name)
#
#         # now handle is listed by collection:
#         collection._reload()
#         assert_in(new_name, collection)
#
#         # test collection repo:
#         ok_clean_git(cpath, annex=False)
#         ok_(isdir(opj(cpath, new_name)))
#         ok_(exists(opj(cpath, new_name, REPO_CONFIG_FILE)))
#         ok_(exists(opj(cpath, new_name, REPO_STD_META_FILE)))
#
#         # evaluate return value:
#         assert_is_instance(return_value, Handle,
#                            "install_handle() returns object of "
#                            "incorrect class: %s" % type(return_value))
#         eq_(return_value.name, new_name)
#         eq_(urlparse(return_value.url).path, urlparse(handle.url).path)



