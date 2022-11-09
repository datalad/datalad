# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the universal datalad's annex customremote"""

import glob
import logging
import os.path as op

from datalad.distribution.dataset import Dataset
from datalad.downloaders.tests.utils import get_test_providers
from datalad.support.exceptions import CommandError
from datalad.support.external_versions import external_versions
from datalad.tests.utils_pytest import (
    assert_in,
    assert_raises,
    eq_,
    serve_path_via_http,
    skip_if_no_network,
    swallow_logs,
    with_tempfile,
    with_tree,
)


@with_tempfile()
@skip_if_no_network
def check_basic_scenario(url, d=None):
    ds = Dataset(d).create()
    annex = ds.repo

    # TODO skip if no boto or no credentials
    get_test_providers(url) # so to skip if unknown creds

    # Let's try to add some file which we should have access to
    ds.download_url(url)
    ds.save()

    # git-annex got a fix where it stopped replacing - in the middle of the filename
    # Let's cater to the developers who might have some intermediate version and not
    # easy to compare -- we will just check that only one file there is an that it
    # matches what we expect when outside of the development versions range:
    filenames = glob.glob(op.join(d, '3versions[-_]allversioned.txt'))
    eq_(len(filenames), 1)
    filename = op.basename(filenames[0])
    # Date after the fix in 8.20200501-53-gcabbc91b1 - must have '-'
    if external_versions['cmd:annex'] >= '8.20200512':
        assert_in('-', filename)
    else:
        # either one is ok
        assert '_' in filename or '-' in filename

    whereis1 = annex.whereis(filename, output='full')
    eq_(len(whereis1), 2)  # here and datalad
    annex.drop(filename)

    whereis2 = annex.whereis(filename, output='full')
    eq_(len(whereis2), 1)  # datalad

    # make sure that there are no "hidden" error messages, despite the
    # whereis command succeeding
    # https://github.com/datalad/datalad/issues/6453#issuecomment-1047533276
    from datalad.runner import StdOutErrCapture

    # we need to swallow logs since if DATALAD_LOG_LEVEL is set low, we
    # would get all the git-annex debug output in stderr
    with swallow_logs(new_level=logging.INFO) as cml:
        out = annex._call_annex(['whereis'], protocol=StdOutErrCapture)
        eq_(out['stderr'].strip(), '')

    # if we provide some bogus address which we can't access, we shouldn't pollute output
    with assert_raises(CommandError) as cme:
        annex.add_url_to_file('bogus', url + '_bogus')
    assert_in('addurl: 1 failed', cme.value.stderr)


# unfortunately with_tree etc decorators aren't generators friendly thus
# this little adapters to test both on local and s3 urls
@with_tree(tree={'3versions-allversioned.txt': "somefile"})
@serve_path_via_http
def test_basic_scenario_local_url(p=None, local_url=None):
    check_basic_scenario("%s3versions-allversioned.txt" % local_url)


def test_basic_scenario_s3():
    check_basic_scenario('s3://datalad-test0-versioned/3versions-allversioned.txt')
