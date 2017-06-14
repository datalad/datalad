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


# Other imports are interspersed with lgr.debug to ease troubleshooting startup
# delays etc.

# If there is a bundled git, make sure GitPython uses it too:
from datalad.cmd import GitRunner
GitRunner._check_git_path()
if GitRunner._GIT_PATH:
    import os
    os.environ['GIT_PYTHON_GIT_EXECUTABLE'] = \
        os.path.join(GitRunner._GIT_PATH, 'git')

from .config import ConfigManager
cfg = ConfigManager()

from .log import lgr
import atexit
from datalad.utils import on_windows
if not on_windows:
    lgr.log(5, "Instantiating ssh manager")
    from .support.sshconnector import SSHManager
    ssh_manager = SSHManager()
    atexit.register(ssh_manager.close, allow_fail=False)
else:
    ssh_manager = None

atexit.register(lgr.log, 5, "Exiting")

from .version import __version__


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

# To store settings which setup_package changes and teardown_package should return
_test_states = {
    'loglevel': None,
    'DATALAD_LOG_LEVEL': None,
}


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

    DATALAD_LOG_LEVEL = os.environ.get('DATALAD_LOG_LEVEL', None)
    if DATALAD_LOG_LEVEL is None:
        # very very silent.  Tests introspecting logs should use
        # swallow_logs(new_level=...)
        _test_states['loglevel'] = lgr.getEffectiveLevel()
        lgr.setLevel(100)

        # And we should also set it within environ so underlying commands also stay silent
        _test_states['DATALAD_LOG_LEVEL'] = DATALAD_LOG_LEVEL
        os.environ['DATALAD_LOG_LEVEL'] = '100'
    else:
        # We are not overriding them, since explicitly were asked to have some log level
        _test_states['loglevel'] = None

    # Set to non-interactive UI
    from datalad.ui import ui
    _test_states['ui_backend'] = ui.backend
    # obtain() since that one consults for the default value
    ui.set_backend(cfg.obtain('datalad.tests.ui.backend'))


def teardown_package():
    import os
    if os.environ.get('DATALAD_TESTS_NOTEARDOWN'):
        return
    from datalad.ui import ui
    ui.set_backend(_test_states['ui_backend'])
    if _test_states['loglevel'] is not None:
        lgr.setLevel(_test_states['loglevel'])
        if _test_states['DATALAD_LOG_LEVEL'] is None:
            os.environ.pop('DATALAD_LOG_LEVEL')
        else:
            os.environ['DATALAD_LOG_LEVEL'] = _test_states['DATALAD_LOG_LEVEL']

    from datalad.tests import _TEMP_PATHS_GENERATED
    from datalad.tests.utils import rmtemp
    if len(_TEMP_PATHS_GENERATED):
        msg = "Removing %d dirs/files: %s" % (len(_TEMP_PATHS_GENERATED), ', '.join(_TEMP_PATHS_GENERATED))
    else:
        msg = "Nothing to remove"
    lgr.debug("Teardown tests. " + msg)
    for path in _TEMP_PATHS_GENERATED:
        rmtemp(path, ignore_errors=True)

    lgr.debug("Printing versioning information collected so far")
    from datalad.support.external_versions import external_versions as ev
    # request versioning for few others which we do not check at runtime
    for m in ('git', 'system-ssh'):
        try:  # Let's make sure to not blow up when we are almost done
            ev[m]
        except Exception:
            pass
    print(ev.dumps(query=True))

lgr.log(5, "Done importing main __init__")
