# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for create-handle command

"""

__docformat__ = 'restructuredtext'

from os.path import basename, exists, isdir, join as opj
from mock import patch
from nose.tools import assert_is_instance
from six.moves.urllib.parse import urlparse

from ...api import create_handle
from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.handle import Handle
from ...support.handlerepo import HandleRepo
from ...consts import HANDLE_META_DIR, REPO_CONFIG_FILE, REPO_STD_META_FILE


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_create_handle(path1, path2, path3, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:
        return_value = create_handle(path1, "TestHandle")

        # get repo to read what was actually created and raise exceptions,
        # if repo is not a valid handle:
        created_repo = get_repo_instance(path1, HandleRepo)

        # check repo itself:
        ok_clean_git(path1, annex=True)
        ok_(isdir(opj(path1, HANDLE_META_DIR)))
        ok_(exists(opj(path1, HANDLE_META_DIR, REPO_CONFIG_FILE)))
        ok_(exists(opj(path1, HANDLE_META_DIR, REPO_STD_META_FILE)))

        # evaluate return value:
        assert_is_instance(return_value, Handle,
                           "create_handle() returns object of "
                           "incorrect class: %s" % type(return_value))

        eq_(return_value.name, created_repo.name)
        eq_(urlparse(return_value.url).path, created_repo.path)

        # handle is known to datalad:
        assert_in(return_value.name, get_datalad_master().get_handle_list())

        with assert_raises(RuntimeError) as cm:
            create_handle(path2, "TestHandle")
        eq_(str(cm.exception), "Handle 'TestHandle' already exists.")

        # TODO: behaviour of create-handle in existing dir
        # (may be even existing handle), not defined yet.

        # creating without 'name' parameter:
        return_value = create_handle(path3)
        eq_(return_value.name, basename(path3))