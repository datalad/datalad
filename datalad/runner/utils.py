# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utilities required by runner-related functionality

All runner-related code imports from here, so this is a comprehensive declaration
of utility dependencies.
"""
import logging
from collections import defaultdict
from typing import (
    List,
    Optional,
)


logger = logging.getLogger("datalad.runner.utils")


class LineSplitter:
    """
    A line splitter that handles 'streamed content' and is based
    on python's built-in splitlines().
    """
    def __init__(self, separator: Optional[str] = None):
        """
        Create a line splitter that will split lines either on a
        given separator, if 'separator' is not None, or on one of
        the known line endings, if 'separator' is None. The
        currently known line endings are "\n", and "\r\n".
        """
        self.separator = separator
        self.remaining_data = None

    def process(self, data: str) -> List[str]:

        assert isinstance(data, str), f"data ({data}) is not of type str"

        # There is nothing to do if we do not get any data, since
        # remaining data would not change, and if it is not None,
        # it has already been parsed.
        if data == "":
            return []

        # Update remaining data before attempting to split lines.
        if self.remaining_data is None:
            self.remaining_data = ""
        self.remaining_data += data

        if self.separator is None:
            # If no separator was specified, use python's built in
            # line split wisdom to split on any known line ending.
            lines_with_ends = self.remaining_data.splitlines(keepends=True)
            detected_lines = self.remaining_data.splitlines()

            # If the last line is identical in lines with ends and
            # lines without ends, it was unterminated, remove it
            # from the list of detected lines and keep it for the
            # next round
            if lines_with_ends[-1] == detected_lines[-1]:
                self.remaining_data = detected_lines[-1]
                del detected_lines[-1]
            else:
                self.remaining_data = None

        else:
            # Split lines on separator. This will create additional
            # empty lines if `remaining_data` end with the separator.
            detected_lines = self.remaining_data.split(self.separator)

            # If replaced data did not end with the separator, it contains an
            # unterminated line. We save that for the next round. Otherwise,
            # we mark that we do not have remaining data.
            if not data.endswith(self.separator):
                self.remaining_data = detected_lines[-1]
            else:
                self.remaining_data = None

            # If replaced data ended with the canonical line ending, we
            # have an extra empty line in detected_lines. If it did not
            # end with canonical line ending, we have to remove the
            # unterminated line.
            del detected_lines[-1]

        return detected_lines

    def finish_processing(self) -> Optional[str]:
        return self.remaining_data


class AssemblingDecoderMixIn:
    """ Mix in to safely decode data that is delivered in parts

    This class can be used to decode data that is partially delivered.
    It detects partial encodings and stores the non-decoded data to
    combine it with additional data, that is delivered later,  and
    decodes the combined data.

    Any un-decoded data is stored in the 'remaining_data'-attribute.
    """
    def __init__(self):
        self.remaining_data = defaultdict(bytes)

    def decode(self, fd: int, data: bytes, encoding: str) -> str:
        assembled_data = self.remaining_data[fd] + data
        try:
            unicode_str = assembled_data.decode(encoding)
            self.remaining_data[fd] = b''
        except UnicodeDecodeError as e:
            unicode_str = assembled_data[:e.start].decode(encoding)
            self.remaining_data[fd] = assembled_data[e.start:]
        return unicode_str

    def __del__(self):
        if any(self.remaining_data.values()):
            logger.debug(
                "unprocessed data in AssemblingDecoderMixIn:\n"
                +"\n".join(
                    f"fd: {key}, data: {value}"
                    for key, value in self.remaining_data.items())
                + "\n")
            logger.warning("unprocessed data in AssemblingDecoderMixIn")
