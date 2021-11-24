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

__all__ = ['RemoteError, SpecialRemote']

from annexremote import (
    ProtocolError,
    SpecialRemote as _SpecialRemote,
    RemoteError as _RemoteError,
)


class RemoteError(_RemoteError):
    # technically the message is optional, but any such case is immediately a
    # UX issue ("reason unknown"), hence let's not allow for it
    def __init__(self, msg):
        # prevent multiline messages, they would be swallowed
        # or kill the protocol
        super().__init__(msg.replace('\n', '\\n'))


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
