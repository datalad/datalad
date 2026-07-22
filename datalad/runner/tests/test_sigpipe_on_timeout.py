# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Regression: process-timeout teardown must terminate the child *before*
closing its stdout/stderr pipes -- otherwise the child (or anything
sharing its stdout fd) gets SIGPIPE on its next write, surfacing as
``exitcode 141`` (= 128+13) to the caller.

AppVeyor observed this on a ``git annex get ... --json-progress`` call in
build https://ci.appveyor.com/project/mih/datalad/builds/54014269 (test
``test_add_archive_content``).  git-annex itself catches SIGPIPE, but the
``tar`` helper it spawns to extract the archive does not, and its 141
propagates back.
"""

from __future__ import annotations

import shutil
import signal
import sys
from typing import Optional

import pytest

from datalad.runner.coreprotocols import StdOutErrCapture
from datalad.runner.nonasyncrunner import run_command

# bash script: trap SIGTERM so the runner's terminate() does not kill us
# during the close/terminate race; then sleep briefly (long enough for
# the runner's 0.1s timeout to fire), then exec a python emitter that
# leaves SIGPIPE at SIG_DFL.  If the runner closes our stdout *before*
# we resume writing, python is SIGPIPE'd on its first write -> rc = -13
# (Python form) / 141 (shell form).
_CHILD = r"""
trap '' TERM
sleep 0.5
exec python3 -u -c "
import signal, sys
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
for i in range(1000):
    sys.stdout.write('p %d\n' % i)
    sys.stdout.flush()
"
"""


class _TerminateOnTimeoutProtocol(StdOutErrCapture):
    """Return ``True`` for the process-runtime timeout so the runner's
    ``_handle_process_timeout`` is invoked, exercising the
    close-before-terminate race we're guarding against.
    """

    def timeout(self, fd: Optional[int]) -> bool:
        return fd is None


@pytest.mark.ai_generated
@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("bash") is None,
    reason="SIGPIPE-driven exit 141 reproducer is Linux+bash specific.",
)
def test_process_timeout_does_not_sigpipe_child() -> None:
    result = run_command(
        ["bash", "-c", _CHILD],
        stdin=None,
        protocol=_TerminateOnTimeoutProtocol,
        timeout=0.1,
        exception_on_error=False,
    )
    assert isinstance(result, dict)
    rc = result["code"]
    # Anything is fine *except* SIGPIPE.  After the fix we expect SIGKILL
    # (rc == -9) since the child traps SIGTERM; on a non-trapping child
    # SIGTERM (rc == -15) is the expected outcome.  The bug surfaces as
    # rc == -signal.SIGPIPE (Python's representation) or 141 (shell-style
    # propagation through an intermediate exit-code translator).
    assert rc not in (141, -signal.SIGPIPE), (
        f"runner closed child stdout before terminating it; child was "
        f"killed by SIGPIPE (rc={rc!r}).  Expected rc -9 (SIGKILL) or "
        f"-15 (SIGTERM) depending on whether the child traps SIGTERM."
    )
