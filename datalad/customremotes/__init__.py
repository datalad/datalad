# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Support of custom remotes (e.g. extraction from archives)

"""

__docformat__ = 'restructuredtext'

__all__ = ['RemoteError', 'SpecialRemote']

from annexremote import ProtocolError
from annexremote import RemoteError as _RemoteError
from annexremote import SpecialRemote as _SpecialRemote

from datalad.support.exceptions import format_exception_with_cause
from datalad.ui import ui


class RemoteError(_RemoteError):
    def __str__(self):
        # this is a message given to remote error, if any
        exc_str = super().__str__()
        # this is the cause ala `raise from`
        exc_cause = getattr(self, '__cause__', None)
        if exc_cause:
            # if we have a cause, collect the cause all the way down
            # we can do quite some chaining
            exc_cause = format_exception_with_cause(exc_cause)
        if exc_str and exc_cause:
            # with have the full picture
            msg = f'{exc_str} -caused by- {exc_cause}'
        elif exc_str and not exc_cause:
            # only a custom message
            msg = exc_str
        elif not exc_str and exc_cause:
            # only the cause
            msg = exc_cause
        else:
            # nothing, shame!
            msg = 'exception with unknown cause'
        # prevent multiline messages, they would be swallowed
        # or kill the protocol
        return msg.replace('\n', '\\n')


class SpecialRemote(_SpecialRemote):
    """Common base class for all of DataLad's special remote implementations"""

    def __init__(self, annex):
        super(SpecialRemote, self).__init__(annex=annex)
        # instruct annex backend UI to use this remote
        if ui.backend == 'annex':
            ui.set_specialremote(self)

    def message(self, msg, type='debug'):
        handler = dict(
            debug=self.annex.debug,
            info=self.annex.info,
            error=self.annex.error,
        ).get(type, self.annex.debug)

        # ensure that no multiline messages are sent, they would cause a
        # protocol error
        msg = msg.replace('\n', '\\n')

        try:
            handler(msg)
        except ProtocolError:
            # INFO not supported by annex version.
            # If we can't have an actual info message, at least have a
            # debug message.
            self.annex.debug(msg)

    def send_progress(self, progress):
        """Indicates the current progress of the transfer (in bytes).

        May be repeated any number of times during the transfer process.

        Too frequent updates are wasteful but bear in mind that this is used
        both to display a progress meter for the user, and for
        ``annex.stalldetection``. So, sending an update on each 1% of the file
        may not be frequent enough, as it could appear to be a stall when
        transferring a large file.

        Parameters
        ----------
        progress : int
            The current progress of the transfer in bytes.
        """
        # This method is called by AnnexSpecialRemoteProgressBar through an
        # obscure process that involves multiple layers of abstractions for
        # UIs, providers, downloaders, progressbars, which is only happening
        # within the environment of a running special remote process though
        # a combination of circumstances.
        #
        # The main purpose of this method is to have a place to leave this
        # comment within the code base of the special remotes, in order to
        # aid future souls having to sort this out.
        # (and to avoid having complex code make direct calls to internals
        # of this class, making things even more complex)
        self.annex.progress(progress)
