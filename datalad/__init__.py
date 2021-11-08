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

if not __debug__:
    raise RuntimeError('DataLad cannot run in "optimized" mode, i.e. python -O')


# For reproducible demos/tests
import os
_seed = os.environ.get('DATALAD_SEED', None)
if _seed is not None:
    import random
    _seed = int(_seed)
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

from .config import ConfigManager
cfg = ConfigManager()

from .log import lgr
from datalad.support.exceptions import CapturedException
from datalad.utils import (
    get_encoding_info,
    get_envvars_info,
    get_home_envvars,
    getpwd,
)

# To analyze/initiate our decision making on what current directory to return
getpwd()

lgr.log(5, "Instantiating ssh manager")
from .support.sshconnector import SSHManager
ssh_manager = SSHManager()
atexit.register(ssh_manager.close, allow_fail=False)
atexit.register(lgr.log, 5, "Exiting")


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
    'env': {},
}

# handle to an HTTP server instance that is used as part of the tests
test_http_server = None

def setup_package():
    import os
    from datalad.utils import on_osx
    from datalad.tests import _TEMP_PATHS_GENERATED

    if on_osx:
        # enforce honoring TMPDIR (see gh-5307)
        import tempfile
        tempfile.tempdir = os.environ.get('TMPDIR', tempfile.gettempdir())

    from datalad import consts

    _test_states['env'] = {}

    def set_envvar(v, val):
        """Memoize and then set env var"""
        _test_states['env'][v] = os.environ.get(v, None)
        os.environ[v] = val

    _test_states['DATASETS_TOPURL'] = consts.DATASETS_TOPURL
    consts.DATASETS_TOPURL = 'https://datasets-tests.datalad.org/'
    set_envvar('DATALAD_DATASETS_TOPURL', consts.DATASETS_TOPURL)

    from datalad.tests.utils import (
        DEFAULT_BRANCH,
        DEFAULT_REMOTE,
    )
    set_envvar("GIT_CONFIG_PARAMETERS",
               "'init.defaultBranch={}' 'clone.defaultRemoteName={}'"
               .format(DEFAULT_BRANCH, DEFAULT_REMOTE))

    # To overcome pybuild overriding HOME but us possibly wanting our
    # own HOME where we pre-setup git for testing (name, email)
    if 'GIT_HOME' in os.environ:
        set_envvar('HOME', os.environ['GIT_HOME'])
    else:
        # we setup our own new HOME, the BEST and HUGE one
        from datalad.utils import make_tempfile
        # TODO: split into a function + context manager
        with make_tempfile(mkdir=True) as new_home:
            pass
        for v, val in get_home_envvars(new_home).items():
            set_envvar(v, val)
        if not os.path.exists(new_home):
            os.makedirs(new_home)
        with open(os.path.join(new_home, '.gitconfig'), 'w') as f:
            f.write("""\
[user]
	name = DataLad Tester
	email = test@example.com
[datalad "log"]
	exc = 1
""")
        _TEMP_PATHS_GENERATED.append(new_home)

    # Re-load ConfigManager, since otherwise it won't consider global config
    # from new $HOME (see gh-4153
    cfg.reload(force=True)

    from datalad.interface.common_cfg import compute_cfg_defaults
    compute_cfg_defaults()
    # datalad.locations.sockets has likely changed. Discard any cached values.
    ssh_manager._socket_dir = None

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
        set_envvar('DATALAD_LOG_LEVEL', '100')
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
    from io import StringIO as OrigStringIO

    class StringIO(OrigStringIO):
        fileno = lambda self: 1
        encoding = None

    from nose.ext import dtcompat
    from nose.plugins import capture, multiprocess, plugintest
    dtcompat.StringIO = StringIO
    capture.StringIO = StringIO
    multiprocess.StringIO = StringIO
    plugintest.StringIO = StringIO

    # in order to avoid having to fiddle with rather uncommon
    # file:// URLs in the tests, have a standard HTTP server
    # that serves an 'httpserve' directory in the test HOME
    # the URL will be available from datalad.test_http_server.url
    from datalad.tests.utils import HTTPPath
    import tempfile

    global test_http_server
    # Start the server only if not running already
    # Relevant: we have test_misc.py:test_test which runs datalad.test but
    # not doing teardown, so the original server might never get stopped
    if test_http_server is None:
        serve_path = tempfile.mkdtemp(
            dir=cfg.get("datalad.tests.temp.dir"),
            prefix='httpserve',
        )
        test_http_server = HTTPPath(serve_path)
        test_http_server.start()
        _TEMP_PATHS_GENERATED.append(serve_path)

    if cfg.obtain('datalad.tests.setup.testrepos'):
        lgr.debug("Pre-populating testrepos")
        from datalad.tests.utils import with_testrepos
        with_testrepos()(lambda repo: 1)()


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
        ce = CapturedException(exc)
        print("Obscure filename failed to print: %s" % ce)
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

    global test_http_server
    if test_http_server:
        test_http_server.stop()
        test_http_server = None
    else:
        lgr.debug("For some reason global http_server was not set/running, thus not stopping")

    from datalad.tests import _TEMP_PATHS_GENERATED
    if len(_TEMP_PATHS_GENERATED):
        msg = "Removing %d dirs/files: %s" % (len(_TEMP_PATHS_GENERATED), ', '.join(_TEMP_PATHS_GENERATED))
    else:
        msg = "Nothing to remove"
    lgr.debug("Teardown tests. " + msg)
    for path in _TEMP_PATHS_GENERATED:
        rmtemp(path, ignore_errors=True)

    # restore all the env variables
    for v, val in _test_states['env'].items():
        if val is not None:
            os.environ[v] = val
        else:
            os.environ.pop(v)

    # Re-establish correct global config after changing $HOME.
    # Might be superfluous, since after teardown datalad.cfg shouldn't be
    # needed. However, maintaining a consistent state seems a good thing
    # either way.
    cfg.reload(force=True)

    from datalad.interface.common_cfg import compute_cfg_defaults
    compute_cfg_defaults()
    ssh_manager._socket_dir = None

    consts.DATASETS_TOPURL = _test_states['DATASETS_TOPURL']

    from datalad.support.cookies import cookies_db
    cookies_db.close()
    from datalad.support.annexrepo import AnnexRepo
    AnnexRepo._ALLOW_LOCAL_URLS = False  # stay safe!


from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

if str(__version__) == '0' or __version__.startswith('0+'):
    lgr.warning(
        "DataLad was not installed 'properly' so its version is an uninformative %r.\n"
        "It can happen e.g. if datalad was installed via\n"
        "  pip install https://github.com/.../archive/{commitish}.zip\n"
        "instead of\n"
        "  pip install git+https://github.com/...@{commitish} .\n"
        "We advise to re-install datalad or downstream projects might not operate correctly.",
        __version__
    )

lgr.log(5, "Done importing main __init__")
