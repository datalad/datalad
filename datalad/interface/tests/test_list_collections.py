# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for list-collections command

"""

__docformat__ = 'restructuredtext'

from os.path import basename
from mock import patch
from nose.tools import assert_is_instance, assert_in, assert_not_in

from ...utils import swallow_logs
from ...api import register_collection, list_collections
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile
from ...cmdline.helpers import get_datalad_master
from ...support.collection import Collection


@assert_cwd_unchanged
@with_testrepos('.*collection.*', flavors=['network', 'local-url'])
@with_tempfile(mkdir=True)
def test_list_collections(collection_url, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:

        register_collection(collection_url)

        new_list = list_collections()

        for item in new_list:
            assert_is_instance(item, Collection)

        # TODO: For easier comparison implement methods like __eq__
        # in class 'Collection'.

        assert_in(basename(collection_url), [c.name for c in new_list])
        assert_in(collection_url.rstrip('/'),
                  [c.url.rstrip('/') for c in new_list])
