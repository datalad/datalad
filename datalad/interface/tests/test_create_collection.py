# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for create-collection command

"""

__docformat__ = 'restructuredtext'

import re
from os.path import basename, exists, join as opj

from mock import patch
from nose.tools import assert_is_instance
from six.moves.urllib.parse import urlparse

from ...utils import swallow_logs
from ...api import create_collection
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...cmdline.helpers import get_repo_instance, get_datalad_master
from ...support.collection import Collection
from ...support.collectionrepo import CollectionRepo
from ...support.exceptions import CommandError
from ...consts import REPO_CONFIG_FILE, REPO_STD_META_FILE


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_create_collection(path1, path2, path3, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:
        return_value = create_collection(path1, "TestCollection")

        # get repo to read what was actually created and raise exceptions,
        # if repo is not a valid collection:
        created_repo = get_repo_instance(path1, CollectionRepo)

        # check repo itself:
        ok_clean_git(path1, annex=False)
        ok_(exists(opj(path1, REPO_CONFIG_FILE)))
        ok_(exists(opj(path1, REPO_STD_META_FILE)))

        # evaluate return value:
        assert_is_instance(return_value, Collection,
                           "create_handle() returns object of "
                           "incorrect class: %s" % type(return_value))

        eq_(return_value.name, created_repo.name)
        eq_(urlparse(return_value.url).path, created_repo.path)

        # collection is known to datalad:
        assert_in(return_value.name, get_datalad_master().git_get_remotes())

        # can't use the same name twice:
        with assert_raises(CommandError) as cm:
            create_collection(path2, "TestCollection")
        ok_(re.match('.*remote TestCollection already exists.*',
                     str(cm.exception.stderr)))

        # TODO: behaviour of create-collection in existing dir
        # (may be even existing collection), not defined yet.

        # creating without 'name' parameter:
        return_value = create_collection(path3)
        eq_(return_value.name, basename(path3))
