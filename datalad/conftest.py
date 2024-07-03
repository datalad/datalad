import logging
import os
import re
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from datalad.support.exceptions import CapturedException
from datalad.utils import (
    get_encoding_info,
    get_envvars_info,
    get_home_envvars,
)

from . import (
    cfg,
    ssh_manager,
)
from .log import lgr

_test_states = {}

# handle to an HTTP server instance that is used as part of the tests
test_http_server = None

@pytest.fixture(autouse=True, scope="session")
def setup_package():
    import tempfile

    from datalad import consts
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.cookies import cookies_db
    from datalad.support.external_versions import external_versions
    from datalad.tests import _TEMP_PATHS_GENERATED
    from datalad.tests.utils_pytest import (
        DEFAULT_BRANCH,
        DEFAULT_REMOTE,
        OBSCURE_FILENAME,
        HTTPPath,
        rmtemp,
    )
    from datalad.ui import ui
    from datalad.utils import (
        make_tempfile,
        on_osx,
    )

    if on_osx:
        # enforce honoring TMPDIR (see gh-5307)
        tempfile.tempdir = os.environ.get('TMPDIR', tempfile.gettempdir())

    # Use unittest's patch instead of pytest.MonkeyPatch for compatibility with
    # old pytests
    with ExitStack() as m:
        m.enter_context(patch.object(consts, "DATASETS_TOPURL", 'https://datasets-tests.datalad.org/'))
        m.enter_context(patch.dict(os.environ, {'DATALAD_DATASETS_TOPURL': consts.DATASETS_TOPURL}))

        m.enter_context(
            patch.dict(
                os.environ,
                {
                    "GIT_CONFIG_PARAMETERS":
                    "'init.defaultBranch={}' 'clone.defaultRemoteName={}'"
                    .format(DEFAULT_BRANCH, DEFAULT_REMOTE)
                }
            )
        )
        cred_cfg = cfg.obtain('datalad.tests.credentials')
        if cred_cfg == 'plaintext':
            m.enter_context(
                patch.dict(
                    os.environ,
                    {
                        'PYTHON_KEYRING_BACKEND':
                            'keyrings.alt.file.PlaintextKeyring'
                    }
                )
            )
        elif cred_cfg == 'system':
            pass
        else:
            raise ValueError(cred_cfg)

        def prep_tmphome():
            # re core.askPass:
            # Don't let git ask for credentials in CI runs. Note, that this variable
            # technically is not a flag, but an executable (which is why name and value
            # are a bit confusing here - we just want a no-op basically). The environment
            # variable GIT_ASKPASS overwrites this, but neither env var nor this config
            # are supported by git-credential on all systems and git versions (most recent
            # ones should work either way, though). Hence use both across CI builds.
            gitconfig = """\
[user]
        name = DataLad Tester
        email = test@example.com
[core]
	askPass =
[datalad "log"]
        exc = 1
[annex "security"]
	# from annex 6.20180626 file:/// and http://localhost access isn't
	# allowed by default
	allowed-url-schemes = http https file
	allowed-http-addresses = all
[protocol "file"]
    # since git 2.38.1 cannot by default use local clones for submodules
    # https://github.blog/2022-10-18-git-security-vulnerabilities-announced/#cve-2022-39253
    allow = always
""" + os.environ.get('DATALAD_TESTS_GITCONFIG', '').replace('\\n', os.linesep)
            # TODO: split into a function + context manager
            with make_tempfile(mkdir=True) as new_home:
                pass
            # register for clean-up on exit
            _TEMP_PATHS_GENERATED.append(new_home)

            # populate default config
            new_home = Path(new_home)
            new_home.mkdir(parents=True, exist_ok=True)
            cfg_file = new_home / '.gitconfig'
            cfg_file.write_text(gitconfig)
            return new_home, cfg_file

        if external_versions['cmd:git'] < "2.32":
            # To overcome pybuild overriding HOME but us possibly wanting our
            # own HOME where we pre-setup git for testing (name, email)
            if 'GIT_HOME' in os.environ:
                m.enter_context(patch.dict(os.environ, {'HOME': os.environ['GIT_HOME']}))
            else:
                # we setup our own new HOME, the BEST and HUGE one
                new_home, _ = prep_tmphome()
                m.enter_context(patch.dict(os.environ, get_home_envvars(new_home)))
        else:
            _, cfg_file = prep_tmphome()
            m.enter_context(patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(cfg_file)}))

        # Re-load ConfigManager, since otherwise it won't consider global config
        # from new $HOME (see gh-4153
        cfg.reload(force=True)

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

        # Prevent interactive credential entry (note "true" is the command to run)
        # See also the core.askPass setting above
        m.enter_context(patch.dict(os.environ, {'GIT_ASKPASS': 'true'}))

        # Set to non-interactive UI
        _test_states['ui_backend'] = ui.backend
        # obtain() since that one consults for the default value
        ui.set_backend(cfg.obtain('datalad.tests.ui.backend'))

        # in order to avoid having to fiddle with rather uncommon
        # file:// URLs in the tests, have a standard HTTP server
        # that serves an 'httpserve' directory in the test HOME
        # the URL will be available from datalad.test_http_server.url

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

        yield

        lgr.debug("Printing versioning information collected so far")
        # Query for version of datalad, so it is included in ev.dumps below - useful while
        # testing extensions where version of datalad might differ in the environment.
        external_versions['datalad']
        print(external_versions.dumps(query=True))
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

        ui.set_backend(_test_states['ui_backend'])

        if test_http_server:
            test_http_server.stop()
            test_http_server = None
        else:
            lgr.debug("For some reason global http_server was not set/running, thus not stopping")

        if len(_TEMP_PATHS_GENERATED):
            msg = "Removing %d dirs/files: %s" % (len(_TEMP_PATHS_GENERATED), ', '.join(_TEMP_PATHS_GENERATED))
        else:
            msg = "Nothing to remove"
        lgr.debug("Teardown tests. " + msg)
        for path in _TEMP_PATHS_GENERATED:
            rmtemp(str(path), ignore_errors=True)

    # Re-establish correct global config after changing $HOME.
    # Might be superfluous, since after teardown datalad.cfg shouldn't be
    # needed. However, maintaining a consistent state seems a good thing
    # either way.
    cfg.reload(force=True)

    ssh_manager._socket_dir = None

    cookies_db.close()


@pytest.fixture(autouse=True)
def capture_logs(caplog, monkeypatch):
    DATALAD_LOG_LEVEL = os.environ.get('DATALAD_LOG_LEVEL', None)
    if DATALAD_LOG_LEVEL is None:
        # very very silent.  Tests introspecting logs should use
        # swallow_logs(new_level=...)
        caplog.set_level(100, lgr.name)
        # And we should also set it within environ so underlying commands also
        # stay silent
        monkeypatch.setenv('DATALAD_LOG_LEVEL', '100')


def pytest_ignore_collect(collection_path: Path) -> bool:
    # Skip old nose code and the tests for it:
    # Note, that this is not only about executing tests but also importing those
    # files to begin with.
    if collection_path.name == "test_tests_utils.py":
        return True
    if collection_path.parts[:-3] == ("datalad", "tests", "utils.py"):
        return True
    # When pytest is told to run doctests, by default it will import every
    # source file in its search, but a number of datalad source file have
    # undesirable side effects when imported.  This hook should ensure that
    # only `test_*.py` files and `*.py` files containing doctests are imported
    # during test collection.
    if collection_path.name.startswith("test_") or collection_path.is_dir():
        return False
    if collection_path.suffix != ".py":
        return True
    return not any(
        re.match(r"^\s*>>>", ln) for ln in collection_path.read_text("utf-8").splitlines()
    )
