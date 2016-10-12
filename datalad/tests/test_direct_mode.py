# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test direct mode mechanic

"""


import logging

# Please do ignore possible unused marking.
# This is used via Dataset class:
import datalad.api

from nose.tools import ok_
from mock import patch

from datalad.support.annexrepo import AnnexRepo
from datalad.utils import swallow_logs
from datalad.distribution.dataset import Dataset

from .utils import with_tempfile, skip_if_no_network, with_testrepos


@with_tempfile
@with_tempfile
@with_tempfile
def test_direct_cfg(path1, path2, path3):
    with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
        # create annex repo in direct mode:
        with swallow_logs(new_level=logging.DEBUG) as cml:
            ar = AnnexRepo(path1, create=True)
            cml.assert_logged("Switching to direct mode",
                              regex=False, level='DEBUG')
            ok_(ar.is_direct_mode())

        # but don't if repo version is 6 (actually, 6 or above):
        with swallow_logs(new_level=logging.WARNING) as cml:
            ar = AnnexRepo(path2, create=True, version=6)
            ok_(not ar.is_direct_mode())
            cml.assert_logged("direct mode not available", regex=False,
                              level='WARNING')

        # explicit parameter `direct` has priority:
        ar = AnnexRepo(path3, create=True, direct=False)
        ok_(not ar.is_direct_mode())

        # don't touch existing repo:
        ar = AnnexRepo(path2, create=True)
        ok_(not ar.is_direct_mode())


@with_tempfile
def test_direct_create(path):
    with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
        ds = Dataset(path).create()
        ok_(ds.repo.is_direct_mode())


# Note/TODO: Currently flavor 'network' only, since creation of local testrepos
# fails otherwise ATM. (git submodule add without needed git options to work in
# direct mode)
@skip_if_no_network
@with_testrepos('basic_annex', flavors=['network'])
@with_tempfile
def test_direct_install(url, path):

    with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
        ds = datalad.api.install(path=path, source=url)
        ok_(ds.repo.is_direct_mode())
