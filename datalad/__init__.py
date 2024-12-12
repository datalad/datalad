# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
    raise RuntimeError(
        'DataLad cannot run in "optimized" mode, i.e. python -O')

import atexit
import os

# this is not to be modified. for querying use get_apimode()
__api = 'python'


def get_apimode():
    """Returns the API mode label for the current session.

    The API mode label indicates whether DataLad is running in "normal"
    mode in a Python session, or whether it is used via the command line
    interface.

    This function is a utility for optimizing behavior and messaging to the
    particular API (Python vs command line) in use in a given process.

    Returns
    {'python', 'cmdline'}
      The API mode is 'python' by default, unless the main command line
      entrypoint set it to 'cmdline'.
    """
    return __api


def in_librarymode():
    """Returns whether DataLad is requested to run in "library mode"

    In this mode DataLad aims to behave without the assumption that it is
    itself the front-end of a process and in full control over messaging
    and parameters.

    Returns
    -------
    bool
    """
    return __runtime_mode == 'library'


def enable_librarymode():
    """Request DataLad to operate in library mode.

    This function should be executed immediately after importing the `datalad`
    package, when DataLad is not used as an application, or in interactive
    scenarios, but as a utility library inside other applications. Enabling
    this mode will turn off some convenience feature that are irrelevant in
    such use cases (with performance benefits), and alters it messaging
    behavior to better interoperate with 3rd-party front-ends.

    Library mode can only be enabled once. Switching it on and off within
    the runtime of a process is not supported.

    Example::

        >>> import datalad
        >>> datalad.enable_librarymode()
    """
    global __runtime_mode
    __runtime_mode = 'library'
    # export into the environment for child processes to inherit
    os.environ['DATALAD_RUNTIME_LIBRARYMODE'] = '1'


# For reproducible demos/tests
_seed = os.environ.get('DATALAD_SEED', None)
if _seed is not None:
    import random
    _seed = int(_seed)
    random.seed(_seed)

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

from .config import (
    ConfigManager,
    warn_on_undefined_git_identity,
)

cfg = ConfigManager()
warn_on_undefined_git_identity(cfg)


# must come after config manager
# this is not to be modified. see enable/in_librarymode()
# by default, we are in application-mode, simply because most of
# datalad was originally implemented with this scenario assumption
__runtime_mode = 'library' \
    if cfg.getbool('datalad.runtime', 'librarymode', False) \
    else 'application'

from datalad.utils import (
    get_encoding_info,
    get_envvars_info,
    getpwd,
)

from .log import lgr


def setup_package():
    import warnings

    warnings.warn(
        "setup_package() and testing with nose are deprecated."
        "  Switch to using pytest instead.",
        DeprecationWarning,
    )
    from datalad.tests.utils import setup_package
    return setup_package()


def teardown_package():
    import warnings
    warnings.warn(
        "teardown_package() and testing with nose are deprecated."
        "  Switch to using pytest instead.",
        DeprecationWarning,
    )
    from datalad.tests.utils import teardown_package
    return teardown_package()

# To analyze/initiate our decision making on what current directory to return
getpwd()

lgr.log(5, "Instantiating ssh manager")
from .support.sshconnector import SSHManager

ssh_manager = SSHManager()
atexit.register(ssh_manager.close, allow_fail=False)
atexit.register(lgr.log, 5, "Exiting")

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
