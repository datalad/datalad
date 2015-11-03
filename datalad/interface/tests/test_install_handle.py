# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for install-handle command

"""

__docformat__ = 'restructuredtext'

import re

from mock import patch
from nose.tools import assert_is_instance, assert_in
from six.moves.urllib.parse import urlparse

from ...utils import swallow_logs
from ...api import install_handle, register_collection
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, with_testrepos, \
    with_tempfile
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.handlerepo import HandleRepo


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=['clone'])  # should work for any annex
@with_tempfile()
@with_tempfile(mkdir=True)
def test_install_handle_from_url(handle_url, path, lcpath):

    # Docstring verbatim copied from InstallHandle class
    ok_startswith(install_handle.__doc__, 'Install a handle')
    assert_in("\nParameters\n-------", install_handle.__doc__)
    assert_in("\nReturns\n-------\n", install_handle.__doc__)

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
        swallow_logs() as cml:
        return_value = install_handle(handle_url, path)

        # get repo to read what was actually installed and raise exceptions,
        # if repo is not a valid handle:
        installed_repo = get_repo_instance(path, HandleRepo)

        # evaluate return value:
        assert_is_instance(return_value, Handle,
                           "install_handle() returns object of "
                           "incorrect class: %s" % type(return_value))

        eq_(return_value.name, installed_repo.name)
        eq_(urlparse(return_value.url).path, installed_repo.path)

        # handle is known to datalad:
        assert_in(return_value.name, get_datalad_master().get_handle_list())

        # we should be able to install handle again to the same location
        install_handle(handle_url, path)

        with assert_raises(ValueError) as cm:
            install_handle(handle_url, path, name="some different name")
        ok_(re.match('Different handle .* is already installed under %s' % path, str(cm.exception)))

        # We have no check for orin
        with assert_raises(RuntimeError) as cm:
            install_handle(handle_url, lcpath)
        eq_(str(cm.exception), '%s already exists, and is not a handle' % lcpath)


@assert_cwd_unchanged
@with_testrepos('collection', flavors=['local-url'])
@with_tempfile()
@with_tempfile(mkdir=True)
def test_install_handle_from_collection(collection_url, path, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
        swallow_logs() as cml:
        collection = register_collection(collection_url, name="TEST_COLLECTION")
        handle = install_handle("TEST_COLLECTION/BasicHandle", path)

        # get repo to read what was actually installed and raise exceptions,
        # if repo is not a valid handle:
        installed_repo = get_repo_instance(path, HandleRepo)

        # evaluate return value:
        assert_is_instance(handle, Handle,
                           "install_handle() returns object of "
                           "incorrect class: %s" % type(handle))

        eq_(handle.name, installed_repo.name)
        eq_(urlparse(handle.url).path, installed_repo.path)

        # handle is known to datalad:
        assert_in("TEST_COLLECTION/BasicHandle",
                  get_datalad_master().get_handle_list())

        # we should be able to install handle again to the same location
        install_handle("TEST_COLLECTION/BasicHandle", path)

