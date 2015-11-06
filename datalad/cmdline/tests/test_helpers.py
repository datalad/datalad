# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for cmdline.helpers"""

__docformat__ = 'restructuredtext'

from mock import patch
from os.path import join as opj, exists
from ..helpers import get_datalad_master, get_repo_instance

from ...tests.utils import ok_, eq_, assert_cwd_unchanged, ok_clean_git, \
    with_tempfile, SkipTest
from ...support.collectionrepo import CollectionRepo
from ...consts import DATALAD_COLLECTION_NAME


@assert_cwd_unchanged
@with_tempfile(mkdir=True)
def test_get_datalad_master(path):
    lcpath = opj(path, DATALAD_COLLECTION_NAME)
    ok_(not exists(lcpath))

    class mocked_dirs:
        user_data_dir = path

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs) as cm:
        master = get_datalad_master()
        eq_(master.path, lcpath)
        ok_(exists(lcpath))
        ok_clean_git(lcpath, annex=False)
        # raises exception in case of invalid collection repo:
        get_repo_instance(lcpath, CollectionRepo)


# TODO:
def test_get_repo_instance():
    raise SkipTest
