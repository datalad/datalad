# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""DataLad command execution runner
"""

from .coreprotocols import (
    KillOutput,
    NoCapture,
    StdErrCapture,
    StdOutCapture,
    StdOutErrCapture,
)
from .exception import CommandError
from .gitrunner import GitWitlessRunner as GitRunner
from .protocol import WitlessProtocol as Protocol
from .runner import WitlessRunner as Runner
