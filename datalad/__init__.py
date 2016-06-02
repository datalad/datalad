# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DataLad aims to expose (scientific) data available online as a unified data
distribution with the convenience of git-annex repositories as a backend."""

import atexit

from .version import __version__
from .log import lgr

# Other imports are interspersed with lgr.debug to ease troubleshooting startup
# delays etc.
lgr.debug("Instantiating config")
from .config import ConfigManager
cfg = ConfigManager()

lgr.debug("Instantiating ssh manager")
from .support.sshconnector import SSHManager
ssh_manager = SSHManager()
atexit.register(ssh_manager.close)


def test(package='datalad', **kwargs):
    """A helper to run datalad's tests.  Requires numpy and nose

    See numpy.testing.Tester -- **kwargs are passed into the
    Tester().test call
    """
    try:
        from numpy.testing import Tester
        Tester(package=package).test(**kwargs)
        # we don't have any benchmarks atm
        # bench = Tester().bench
    except ImportError:
        raise RuntimeError('Need numpy >= 1.2 for datalad.tests().  Nothing is done')
test.__test__ = False

# Following fixtures are necessary at the top level __init__ for fixtures which
# would cover all **/tests and not just datalad/tests/


def setup_package():
    import os

    # To overcome pybuild overriding HOME but us possibly wanting our
    # own HOME where we pre-setup git for testing (name, email)
    if 'GIT_HOME' in os.environ:
        os.environ['HOME'] = os.environ['GIT_HOME']

    # To overcome pybuild by default defining http{,s}_proxy we would need
    # to define them to e.g. empty value so it wouldn't bother touching them.
    # But then haskell libraries do not digest empty value nicely, so we just
    # pop them out from the environment
    for ev in ('http_proxy', 'https_proxy'):
        if ev in os.environ and not (os.environ[ev]):
            lgr.debug("Removing %s from the environment since it is empty", ev)
            os.environ.pop(ev)


def teardown_package():
    from datalad.tests import _TEMP_PATHS_GENERATED
    from datalad.tests.utils import rmtemp
    if len(_TEMP_PATHS_GENERATED):
        msg = "Removing %d dirs/files: %s" % (len(_TEMP_PATHS_GENERATED), ', '.join(_TEMP_PATHS_GENERATED))
    else:
        msg = "Nothing to remove"
    lgr.debug("Teardown tests. " + msg)
    for path in _TEMP_PATHS_GENERATED:
        rmtemp(path, ignore_errors=True)
