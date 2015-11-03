# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for register-collection command

"""

__docformat__ = 'restructuredtext'

from os.path import basename
from mock import patch
from nose.tools import assert_is_instance, assert_in, assert_not_in

from ...utils import swallow_logs
from ...api import register_collection
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile
from ...cmdline.helpers import get_datalad_master
from ...support.collection import Collection
from ...support.exceptions import CommandError


@assert_cwd_unchanged
@with_testrepos('.*collection.*', flavors=['network', 'local-url'])
@with_tempfile(mkdir=True)
def test_register_collection(collection_url, lcpath):

    class mocked_dirs:
        user_data_dir = lcpath
    name = basename(collection_url)
    with patch('datalad.cmdline.helpers.dirs', mocked_dirs), \
            swallow_logs() as cml:
        assert_not_in(name, get_datalad_master().git_get_remotes())

        return_value = register_collection(collection_url)

        # collection is now known to datalad:
        assert_in(name, get_datalad_master().git_get_remotes())

        # evaluate return value:
        assert_is_instance(return_value, Collection)
        eq_(name, return_value.name)
        eq_(collection_url.rstrip('/'), return_value.url.rstrip('/'))

        # registering again:
        with assert_raises(CommandError) as cm:
            register_collection(collection_url)
        assert_in("fatal: remote %s already exists." % name, cm.exception.stderr)

        # again, with new name:
        new_name = name + "_2"
        register_collection(collection_url, name=new_name)
        assert_in(new_name, get_datalad_master().git_get_remotes())


# TODO: register with new name