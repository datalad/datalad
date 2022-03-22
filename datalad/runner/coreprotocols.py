# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Generic core protocols for use with the DataLad runner
"""

import logging

from .protocol import WitlessProtocol

lgr = logging.getLogger('datalad.runner.coreprotocols')


class NoCapture(WitlessProtocol):
    """WitlessProtocol that captures no subprocess output

    As this is identical with the behavior of the WitlessProtocol base class,
    this class is merely a more readable convenience alias.
    """
    pass


class StdOutCapture(WitlessProtocol):
    """WitlessProtocol that only captures and returns stdout of a subprocess"""
    proc_out = True


class StdErrCapture(WitlessProtocol):
    """WitlessProtocol that only captures and returns stderr of a subprocess"""
    proc_err = True


class StdOutErrCapture(WitlessProtocol):
    """WitlessProtocol that captures and returns stdout/stderr of a subprocess
    """
    proc_out = True
    proc_err = True


class KillOutput(WitlessProtocol):
    """WitlessProtocol that swallows stdout/stderr of a subprocess
    """
    proc_out = True
    proc_err = True

    def pipe_data_received(self, fd, data):
        if lgr.isEnabledFor(5):
            lgr.log(
                5,
                'Discarded %i bytes from %i[%s]',
                len(data), self.process.pid, self.fd_infos[fd][0])
