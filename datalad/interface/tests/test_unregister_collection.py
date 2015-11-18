# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for unregister-collection command

"""

__docformat__ = 'restructuredtext'

from mock import patch
from nose.tools import assert_is_instance, assert_in, assert_not_in

from ...utils import swallow_logs
from ...api import register_collection, unregister_collection
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile
from ...cmdline.helpers import get_datalad_master


@assert_cwd_unchanged
@with_testrepos('.*collection.*', flavors=['network', 'local-url'])
@with_tempfile(mkdir=True)
def test_unregister_collection(collection_url, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
        swallow_logs() as cml:

        collection = register_collection(collection_url)
        assert_in(collection.name, get_datalad_master().git_get_remotes())
        unregister_collection(collection.name)
        assert_not_in(collection.name, get_datalad_master().git_get_remotes())