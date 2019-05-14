# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DataLad aims to expose (scientific) data available online as a unified data
distribution with the convenience of git-annex repositories as a backend.

Commands are exposed through both a command-line interface and a Python API. On
the command line, run 'datalad --help' for a summary of the available commands.
From an interactive Python session, import `datalad.api` and inspect its
documentation with `help`.
"""

# For reproducible demos/tests
import os
_seed = os.environ.get('DATALAD_SEED', None)
if _seed:
    import random
    random.seed(_seed)

import atexit
# Colorama (for Windows terminal colors) must be imported before we use/bind
# any sys.stdout
try:
    # this will fix the rendering of ANSI escape sequences
    # for colored terminal output on windows
    # it will do nothing on any other platform, hence it
    # is safe to call unconditionally
    import colorama
    colorama.init()
    atexit.register(colorama.deinit)
except ImportError as e:
    pass

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
from datalad.utils import get_encoding_info, get_envvars_info, getpwd

# To analyze/initiate our decision making on what current directory to return
getpwd()

lgr.log(5, "Instantiating ssh manager")
from .support.sshconnector import SSHManager
ssh_manager = SSHManager()
atexit.register(ssh_manager.close, allow_fail=False)
atexit.register(lgr.log, 5, "Exiting")

from .version import __version__


def test(module='datalad', verbose=False, nocapture=False, pdb=False, stop=False):
    """A helper to run datalad's tests.  Requires nose
    """
    argv = [] #module]
    # could make it 'smarter' but decided to be explicit so later we could
    # easily migrate to another runner without changing any API here
    if verbose:
        argv.append('-v')
    if nocapture:
        argv.append('-s')
    if pdb:
        argv.append('--pdb')
    if stop:
        argv.append('--stop')
    from datalad.support.third.nosetester import NoseTester
    tester = NoseTester(module)
    tester.package_name = module.split('.', 1)[0]
    tester.test(extra_argv=argv)

test.__test__ = False

# Following fixtures are necessary at the top level __init__ for fixtures which
# would cover all **/tests and not just datalad/tests/

# To store settings which setup_package changes and teardown_package should return
_test_states = {
    'loglevel': None,
    'DATALAD_LOG_LEVEL': None,
    'HOME': None,
}


def setup_package():
    import os
    from datalad import consts
    _test_states['HOME'] = os.environ.get('HOME', None)
    _test_states['DATASETS_TOPURL_ENV'] = os.environ.get('DATALAD_DATASETS_TOPURL', None)
    _test_states['DATASETS_TOPURL'] = consts.DATASETS_TOPURL
    os.environ['DATALAD_DATASETS_TOPURL'] = consts.DATASETS_TOPURL = 'http://datasets-tests.datalad.org/'

    # To overcome pybuild overriding HOME but us possibly wanting our
    # own HOME where we pre-setup git for testing (name, email)
    if 'GIT_HOME' in os.environ:
        os.environ['HOME'] = os.environ['GIT_HOME']
    else:
        # we setup our own new HOME, the BEST and HUGE one
        from datalad.utils import make_tempfile
        from datalad.tests import _TEMP_PATHS_GENERATED
        # TODO: split into a function + context manager
        with make_tempfile(mkdir=True) as new_home:
            os.environ['HOME'] = new_home
        if not os.path.exists(new_home):
            os.makedirs(new_home)
        with open(os.path.join(new_home, '.gitconfig'), 'w') as f:
            f.write("""\
[user]
	name = DataLad Tester
	email = test@example.com
""")
        _TEMP_PATHS_GENERATED.append(new_home)

    # For now we will just verify that it is ready to run the tests
    from datalad.support.gitrepo import check_git_configured
    check_git_configured()

    # To overcome pybuild by default defining http{,s}_proxy we would need
    # to define them to e.g. empty value so it wouldn't bother touching them.
    # But then haskell libraries do not digest empty value nicely, so we just
    # pop them out from the environment
    for ev in ('http_proxy', 'https_proxy'):
        if ev in os.environ and not (os.environ[ev]):
            lgr.debug("Removing %s from the environment since it is empty", ev)
            os.environ.pop(ev)

    # During tests we allow for "insecure" access to local file:// and
    # http://localhost URLs since all of them either generated as tests
    # fixtures or cloned from trusted sources
    from datalad.support.annexrepo import AnnexRepo
    AnnexRepo._ALLOW_LOCAL_URLS = True

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

    # Monkey patch nose so it does not ERROR out whenever code asks for fileno
    # of the output. See https://github.com/nose-devs/nose/issues/6
    from six.moves import StringIO as OrigStringIO

    class StringIO(OrigStringIO):
        fileno = lambda self: 1
        encoding = None

    from nose.ext import dtcompat
    from nose.plugins import capture, multiprocess, plugintest
    dtcompat.StringIO = StringIO
    capture.StringIO = StringIO
    multiprocess.StringIO = StringIO
    plugintest.StringIO = StringIO


def teardown_package():
    import os
    from datalad.tests.utils import rmtemp, OBSCURE_FILENAME

    lgr.debug("Printing versioning information collected so far")
    from datalad.support.external_versions import external_versions as ev
    print(ev.dumps(query=True))
    try:
        print("Obscure filename: str=%s repr=%r"
                % (OBSCURE_FILENAME.encode('utf-8'), OBSCURE_FILENAME))
    except UnicodeEncodeError as exc:
        from .dochelpers import exc_str
        print("Obscure filename failed to print: %s" % exc_str(exc))
    def print_dict(d):
        return " ".join("%s=%r" % v for v in d.items())
    print("Encodings: %s" % print_dict(get_encoding_info()))
    print("Environment: %s" % print_dict(get_envvars_info()))

    if os.environ.get('DATALAD_TESTS_NOTEARDOWN'):
        return
    from datalad.ui import ui
    from datalad import consts
    ui.set_backend(_test_states['ui_backend'])
    if _test_states['loglevel'] is not None:
        lgr.setLevel(_test_states['loglevel'])
        if _test_states['DATALAD_LOG_LEVEL'] is None:
            os.environ.pop('DATALAD_LOG_LEVEL')
        else:
            os.environ['DATALAD_LOG_LEVEL'] = _test_states['DATALAD_LOG_LEVEL']

    from datalad.tests import _TEMP_PATHS_GENERATED
    if len(_TEMP_PATHS_GENERATED):
        msg = "Removing %d dirs/files: %s" % (len(_TEMP_PATHS_GENERATED), ', '.join(_TEMP_PATHS_GENERATED))
    else:
        msg = "Nothing to remove"
    lgr.debug("Teardown tests. " + msg)
    for path in _TEMP_PATHS_GENERATED:
        rmtemp(path, ignore_errors=True)

    if _test_states['HOME'] is not None:
        os.environ['HOME'] = _test_states['HOME']

    if _test_states['DATASETS_TOPURL_ENV']:
        os.environ['DATALAD_DATASETS_TOPURL'] = _test_states['DATASETS_TOPURL_ENV']
    consts.DATASETS_TOPURL = _test_states['DATASETS_TOPURL']

    from datalad.support.cookies import cookies_db
    cookies_db.close()
    from datalad.support.annexrepo import AnnexRepo
    AnnexRepo._ALLOW_LOCAL_URLS = False  # stay safe!


lgr.log(5, "Done importing main __init__")
