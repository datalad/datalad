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

from annexremote import (
    ProtocolError,
    SpecialRemote as _SpecialRemote,
    RemoteError as _RemoteError,
)
from datalad.support.exceptions import format_exception_with_cause


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
