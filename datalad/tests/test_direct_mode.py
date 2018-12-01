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
from datalad import cfg

from nose.tools import ok_
from mock import patch

from datalad.support.annexrepo import AnnexRepo
from datalad.utils import swallow_logs
from datalad.distribution.dataset import Dataset

from ..support.exceptions import DirectModeNoLongerSupportedError
from ..support import path as op

from .utils import with_tempfile
from .utils import skip_if_no_network
from .utils import with_testrepos
from .utils import on_windows
from .utils import SkipTest
from .utils import assert_raises
from .utils import assert_in
from .utils import eq_


# if on_windows:
#     raise SkipTest("Can't test direct mode switch, "
#                    "if direct mode is forced by OS anyway.")
#
# repo_version = cfg.get("datalad.repo.version", None)
# if repo_version and int(repo_version) >= 6:
#     raise SkipTest("Can't test direct mode switch, "
#                    "if repository version 6 or later is enforced.")


@with_tempfile
@with_tempfile
def test_direct_cfg(path1, path2):
    # and if repo already exists and we have env var - we fail too
    # Adding backend so we get some commit into the repo
    ar = AnnexRepo(path1, create=True, backend='MD5E')
    del ar;  AnnexRepo._unique_instances.clear()  # fight flyweight
    for path in (path1, path2):
        with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
            # try to create annex repo in direct mode as see how it fails
            with assert_raises(DirectModeNoLongerSupportedError) as cme:
                AnnexRepo(path, create=True)
            assert_in("no longer supported by DataLad", str(cme.exception)) # we have generic part
            assert_in("datalad.repo.direct configuration", str(cme.exception)) # situation specific part
    # assert not op.exists(path2)   # that we didn't create it - we do!
    #   fixing for that would be too cumbersome since we first call GitRepo.__init__
    #   with create
    ar = AnnexRepo(path1)
    # check if we somehow didn't reset the flag
    assert not ar.is_direct_mode()

    if ar.config.obtain("datalad.repo.version") >= 6:
        raise SkipTest("Created repo not v5, cannot test detection of direct mode repos")
    # and if repo existed before and was in direct mode, we fail too
    # Since direct= option was deprecated entirely, we use protected method now
    ar._set_direct_mode(True)
    assert ar.is_direct_mode()
    del ar  # but we would need to disable somehow the flywheel
    with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
        with assert_raises(DirectModeNoLongerSupportedError) as cme:
            AnnexRepo(path1, create=False)


    # TODO: RM DIRECT decide what should we here -- should we test/blow?
    #   ATM both tests below just pass
    ar2 = AnnexRepo(path2, create=True)
    # happily can do it since it doesn't need a worktree to do the clone
    ar2.add_submodule('sub1', url=path1)
    ar2sub1 = AnnexRepo(op.join(path2, 'sub1'))
    # but now let's convert that sub1 to direct mode
    assert not ar2sub1.is_direct_mode()
    ar2sub1._set_direct_mode(True)
    assert ar2sub1.is_direct_mode()
    del ar2; del ar2sub1; AnnexRepo._unique_instances.clear()  # fight flyweight

    ar2 = AnnexRepo(path2)
    ar2.get_submodules()

    # And what if we are trying to add pre-cloned repo in direct mode?
    ar2sub2 = AnnexRepo.clone(path1, op.join(path2, 'sub2'))
    ar2sub2._set_direct_mode(True)
    del ar2sub2; AnnexRepo._unique_instances.clear()  # fight flyweight
    ar2.add('sub2')
