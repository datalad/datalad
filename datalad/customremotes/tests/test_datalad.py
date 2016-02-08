# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the universal datalad's annex customremote"""

from ...support.handlerepo import HandleRepo
from ...consts import DATALAD_SPECIAL_REMOTE
from ...tests.utils import *

from . import _get_custom_runner
from ...support.exceptions import CommandError
from ...downloaders.tests.utils import get_test_providers


@with_tempfile()
@skip_if_no_network
def check_basic_scenario(direct, d):
    handle = HandleRepo(d, runner=_get_custom_runner(d), direct=direct)
    handle.annex_initremote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'autoenable=true'])

    # TODO skip if no boto or no credentials
    get_test_providers('s3://datalad-test0-versioned/') # so to skip if unknown creds

    # Let's try to add some file which we should have access to
    with swallow_outputs() as cmo:
        handle.annex_addurls(['s3://datalad-test0-versioned/3versions-allversioned.txt'])
        assert_in('100%', cmo.err)  # we do provide our progress indicator

    # if we provide some bogus address which we can't access, we shouldn't pollute output
    with swallow_outputs() as cmo, swallow_logs() as cml:
        with assert_raises(CommandError) as cme:
            handle.annex_addurls(['s3://datalad-test0-versioned/3versions-allversioned.txt_bogus'])
        # assert_equal(cml.out, '')
        err, out = cmo.err, cmo.out
    assert_equal(out, '')
    assert_in('addurl: 1 failed', err)
    # and there should be nothing more


def test_basic_scenario():
    yield check_basic_scenario, False
    if not on_windows:
        yield check_basic_scenario, True
