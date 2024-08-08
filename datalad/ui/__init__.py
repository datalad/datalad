# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interactive User Interface (as Dialog/GUI/etc) support

"""

__docformat__ = 'restructuredtext'

from logging import getLogger

lgr = getLogger('datalad.ui')

lgr.log(5, "Starting importing ui")

from ..utils import (
    get_ipython_shell,
    is_interactive,
)
from .dialog import (
    ConsoleLog,
    DialogUI,
    IPythonUI,
    QuietConsoleLog,
    SilentConsoleLog,
    UnderAnnexUI,
    UnderTestsUI,
)

KNOWN_BACKENDS = {
    'console': ConsoleLog,
    'dialog': DialogUI,
    'ipython': IPythonUI,
    'annex': UnderAnnexUI,
    'tests': UnderTestsUI,
    'tests-noninteractive': QuietConsoleLog,
    'no-progress': SilentConsoleLog,
}


# TODO: implement logic on selection of the ui based on the cfg and environment
# e.g. we cannot use DialogUI if session is not interactive
# TODO:  GitAnnexUI where interactive queries (such as question) should get to the
# user by proxying some other appropriate (cmdline or GUI) UI, while others, such
# as reporting on progress etc -- should get back to the annex


# TODO: singleton
class _UI_Switcher(object):
    """
    Poor man helper to switch between different backends at run-time.
    """
    def __init__(self, backend=None):
        self._backend = None
        self._ui = None
        self.set_backend(backend)

    def set_backend(self, backend):
        if backend and (backend == self._backend):
            lgr.debug("not changing backend since the same %s", backend)
            return
        if backend is None:
            # Might be IPython
            ipython_shell = get_ipython_shell()
            if ipython_shell:
                # Good old ipython would have TerminalInteractiveShell
                if ipython_shell.__class__.__name__ in ('ZMQInteractiveShell',):
                    backend = 'ipython'
                    # well -- this will not even be printed yet since unlikely
                    # the lgr handlers were set already
                    lgr.info(
                        "Detected IPython session. Setting UI backend to %r. "
                        "If this is not a web IPython notebook session, you "
                        "might like to datalad.ui.ui.set_backend('dialog'). "
                        "Other known UI backends: %s",
                        backend, ', '.join(KNOWN_BACKENDS))
                else:
                    backend = 'dialog'
            else:
                backend = 'dialog' if is_interactive() else 'no-progress'
        self._ui = KNOWN_BACKENDS[backend]()
        lgr.debug("UI set to %s", self._ui)
        self._backend = backend

    @property
    def backend(self):
        return self._backend

    @property
    def ui(self):
        return self._ui

    # Delegate other methods to the actual UI
    def __getattribute__(self, key):
        if key.startswith('_') or key in {'set_backend', 'backend', 'ui'}:
            return super(_UI_Switcher, self).__getattribute__(key)
        return getattr(self._ui, key)

    def __setattr__(self, key, value):
        if key.startswith('_') or key in {'set_backend', 'backend', 'ui'}:
            return super(_UI_Switcher, self).__setattr__(key, value)
        return setattr(self._ui, key, value)

lgr.log(5, "Initiating UI switcher")

ui = _UI_Switcher()

lgr.log(5, "Done importing ui")
