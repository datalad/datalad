# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test direct mode mechanic

"""

from unittest.mock import patch

from datalad.support import path as op
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    CommandNotAvailableError,
    DirectModeNoLongerSupportedError,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_raises,
    with_tempfile,
)

# if on_windows:
#     raise SkipTest("Can't test direct mode switch, "
#                    "if direct mode is forced by OS anyway.")
#
# repo_version = cfg.get("datalad.repo.version", None)
# if repo_version and int(repo_version) >= 6:
#     raise SkipTest("Can't test direct mode switch, "
#                    "if repository version 6 or later is enforced.")


# originally lifted from AnnexRepo, kept here to simulate a repo
# that is still in direct mode
def _set_direct_mode(self, enable_direct_mode=True):
    """Switch to direct or indirect mode

    WARNING!  To be used only for internal development purposes.
              We no longer support direct mode and thus setting it in a
              repository would render it unusable for DataLad

    Parameters
    ----------
    enable_direct_mode: bool
        True means switch to direct mode,
        False switches to indirect mode

    Raises
    ------
    CommandNotAvailableError
        in case you try to switch to indirect mode on a crippled filesystem
    """
    if self.is_crippled_fs() and not enable_direct_mode:
        # TODO: ?? DIRECT - should we call git annex upgrade?
        raise CommandNotAvailableError(
            cmd="git-annex indirect",
            msg="Can't switch to indirect mode on that filesystem.")

    self.call_annex(['direct' if enable_direct_mode else 'indirect']),
    self.config.reload()

    # For paranoid we will just re-request
    self._direct_mode = None
    assert(self.is_direct_mode() == enable_direct_mode)

    # All further workarounds were stripped - no direct mode is supported


@with_tempfile
@with_tempfile
def test_direct_cfg(path1=None, path2=None):
    # and if repo already exists and we have env var - we fail too
    # Adding backend so we get some commit into the repo
    ar = AnnexRepo(path1, create=True, backend='MD5E')
    del ar;  AnnexRepo._unique_instances.clear()  # fight flyweight
    for path in (path1, path2):
        with patch.dict('os.environ', {'DATALAD_REPO_DIRECT': 'True'}):
            # try to create annex repo in direct mode as see how it fails
            with assert_raises(DirectModeNoLongerSupportedError) as cme:
                AnnexRepo(path, create=True)
            assert_in("no longer supported by DataLad", str(cme.value)) # we have generic part
            assert_in("datalad.repo.direct configuration", str(cme.value)) # situation specific part
    # assert not op.exists(path2)   # that we didn't create it - we do!
    #   fixing for that would be too cumbersome since we first call GitRepo.__init__
    #   with create
    ar = AnnexRepo(path1)
    # check if we somehow didn't reset the flag
    assert not ar.is_direct_mode()
