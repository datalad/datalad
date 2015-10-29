# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for get command

"""

__docformat__ = 'restructuredtext'

import re
from mock import patch

from os.path import join as opj, exists
from ...utils import swallow_logs
from ...api import install_handle

from ...support.annexrepo import AnnexRepo
from ...tests.utils import ok_, eq_
from ...tests.utils import assert_raises
from ...tests.utils import with_testrepos
from ...tests.utils import with_tempfile

#@assert_cwd_unchanged
@with_testrepos('basic_annex', flavors=['clone'])
@with_tempfile()
@with_tempfile(mkdir=True)
def test_install_handle_basic(handle_url, path, lcpath):
    ok_(not exists(opj(lcpath, "localcollection")))
    # TODO: make it saner see https://github.com/datalad/datalad/issues/234
    # apparently can't mock a property
    #with patch('datalad.interface.install_handle.dirs.user_data_dir', lcpath):

    class mocked_dirs:
        user_data_dir = lcpath

    with patch('datalad.interface.install_handle.dirs', mocked_dirs), \
        swallow_logs() as cml:
        install_handle(handle_url, path)
        # TODO: verify output value, see https://github.com/datalad/datalad/issues/236
        ok_(exists(opj(lcpath, "localcollection")))

        # we should be able to install handle again to the same location
        install_handle(handle_url, path)

        with assert_raises(ValueError) as cm:
            install_handle(handle_url, path, name="some different name")
        ok_(re.match('Different handle .* is already installed under %s' % path, str(cm.exception)))

        # We have no check for orin
        with assert_raises(RuntimeError) as cm:
            install_handle(handle_url, lcpath)
        eq_(str(cm.exception), '%s already exists, and is not a handle' % lcpath)