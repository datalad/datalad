# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for functionality of basic datalad commands"""

import os
from os.path import join as opj

from nose import SkipTest
from nose.tools import assert_raises, assert_equal, assert_false, assert_in, \
    assert_not_in

from ..support.handlerepo import HandleRepo
from ..support.collectionrepo import CollectionRepo, CollectionRepoHandleBackend
from ..tests.utils import ok_clean_git, with_tempfile, ok_
from ..utils import get_local_file_url

# Note: For the actual commands use the following to determine paths to
# the local master collection, configs, etc.:
# from appdirs import AppDirs
# dirs = AppDirs("datalad", "datalad.org")
# path_to_local_master = os.path.join(dirs.user_data_dir, 'localcollection')


@with_tempfile
def test_local_master(m_path):

    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    assert_equal(m_path, local_master.path)
    ok_clean_git(m_path, annex=False)
    ok_(os.path.exists(opj(m_path, 'datalad.ttl')))
    ok_(os.path.exists(opj(m_path, 'config.ttl')))
    assert_equal(local_master.get_handle_list(), [])


@with_tempfile
def test_register_collection(m_path):

    test_url = "https://github.com/bpoldrack/ExampleCollection.git"
    test_name = test_url.split('/')[-1].rstrip('.git')
    assert_equal(test_name, 'ExampleCollection')

    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    local_master.git_remote_add(test_name, test_url)
    local_master.git_fetch(test_name)

    assert_equal(local_master.git_get_remotes(), [test_name])
    assert_equal(set(local_master.git_get_files(test_name + '/master')),
                 {'config.ttl', 'datalad.ttl'})
    ok_clean_git(m_path, annex=False)


@with_tempfile
@with_tempfile
def test_create_collection(m_path, c_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    # create the collection:
    new_collection = CollectionRepo(c_path, name='new_collection')
    assert_equal(new_collection.name, 'new_collection')

    # register with local master:
    local_master.git_remote_add(new_collection.name, new_collection.path)
    local_master.git_fetch(new_collection.name)

    assert_equal(local_master.git_get_remotes(), [new_collection.name])
    ok_clean_git(m_path, annex=False)
    ok_clean_git(c_path, annex=False)
    assert_equal(set(local_master.git_get_files(new_collection.name +
                                                '/master')),
                 {'config.ttl', 'datalad.ttl'})


@with_tempfile
@with_tempfile
def test_create_handle(m_path, h_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    # create the handle repository:
    handle = HandleRepo(h_path, name="MyHandleDefaultName")

    ok_clean_git(h_path, annex=True)
    ok_(os.path.exists(opj(h_path, '.datalad')))
    ok_(os.path.isdir(opj(h_path, '.datalad')))
    ok_(os.path.exists(opj(h_path, '.datalad', 'datalad.ttl')))
    ok_(os.path.exists(opj(h_path, '.datalad', 'config.ttl')))

    # add it to the local master collection:
    local_master.add_handle(handle, name="MyHandle")

    ok_clean_git(local_master.path, annex=False)
    assert_equal(local_master.get_handle_list(), ["MyHandle"])


@with_tempfile
@with_tempfile
@with_tempfile
def test_add_handle_to_collection(m_path, c_path, h_path):
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')

    # create collection:
    collection = CollectionRepo(c_path, name="MyCollection")
    # register collection:
    local_master.git_remote_add(collection.name, c_path)
    local_master.git_fetch(collection.name)
    # create handle:
    handle = HandleRepo(h_path, name="MyHandle")
    # add to master:
    local_master.add_handle(handle, handle.name)
    # add to collection:
    collection.add_handle(handle, handle.name)
    # update knowledge about the collection in local master:
    local_master.git_fetch(collection.name)

    ok_clean_git(local_master.path, annex=False)
    ok_clean_git(collection.path, annex=False)
    ok_clean_git(handle.path, annex=True)
    assert_equal(collection.get_handle_list(), ["MyHandle"])
    assert_equal(local_master.get_handle_list(), ["MyHandle"])
    assert_equal(set(local_master.git_get_files(collection.name + '/master')),
                 {'MyHandle/config.ttl', 'MyHandle/datalad.ttl',
                  'config.ttl', 'datalad.ttl'})
    assert_equal(set(collection.git_get_files()),
                 {'MyHandle/config.ttl', 'MyHandle/datalad.ttl',
                  'config.ttl', 'datalad.ttl'})


@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_install_handle(m_path, c_path, h_path, install_path):
    handle_by_name = "MyCollection/MyHandle"

    # setup:
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    collection = CollectionRepo(c_path, name="MyCollection")
    handle = HandleRepo(h_path, name="MyHandle")
    collection.add_handle(handle, handle.name)
    local_master.git_remote_add(collection.name, collection.path)
    local_master.git_fetch(collection.name)

    # retrieve handle's url:
    q_col = handle_by_name.split('/')[0]
    q_hdl = handle_by_name.split('/')[1]

    handle_backend = CollectionRepoHandleBackend(repo=local_master, key=q_hdl,
                                                 branch=q_col + '/master')
    assert_equal(handle_backend.url, get_local_file_url(h_path))

    # install the handle:
    installed_handle = HandleRepo(install_path, handle_backend.url)
    local_master.add_handle(installed_handle, name=handle_by_name)

    ok_clean_git(install_path, annex=True)
    ok_clean_git(local_master.path, annex=False)
    assert_equal(set(installed_handle.git_get_files()),
                 {opj('.datalad', 'datalad.ttl'),
                  opj('.datalad', 'config.ttl')})
    assert_equal(installed_handle.git_get_remotes(), ['origin'])
    assert_equal(local_master.get_handle_list(), [handle_by_name])
    assert_equal(installed_handle.name, "MyHandle")


@with_tempfile
def test_unregister_collection(m_path):

    # setup:
    m_path = opj(m_path, 'localcollection')
    local_master = CollectionRepo(m_path, name='local')
    collection_url = "https://github.com/bpoldrack/ExampleCollection.git"
    local_master.git_remote_add(name="MyCollection", url=collection_url)
    local_master.git_fetch("MyCollection")

    # unregister:
    local_master.git_remote_remove("MyCollection")

    ok_clean_git(local_master.path, annex=False)
    assert_equal(local_master.git_get_remotes(), [])


def test_uninstall_handle():
    raise SkipTest