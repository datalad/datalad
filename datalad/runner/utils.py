# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from typing import (
    List,
    Optional,
)

from datalad.dochelpers import borrowdoc
from datalad.utils import (
    auto_repr,
    ensure_unicode,
    generate_file_chunks,
    join_cmdline,
    try_multiple,
    unlink,
)


Canonical_Line_Ending = "\n"
Other_Line_Endings = [
    "\r\n",
]


_Ordered_Other_Line_Endings = sorted(Other_Line_Endings, key=lambda e: len(e))


class LineSplitter:
    """
    An OS independent line splitter. In particular, it splits
    lines terminated with "\n" properly in Windows.
    """
    def __init__(self, separator: Optional[str] = None):
        """
        Create a line splitter that will split lines either on a
        given separator, if 'separator' is not None, or on one of
        the known line endings, if 'separator' is None. The
        currently known line endings are "\n", and "\r\n".
        """
        self.separator = separator or Canonical_Line_Ending
        self.unify_separators = separator is None
        self.remaining_data = None

    def process(self, data: str) -> List[str]:

        assert isinstance(data, str), f"data ({data}) is not of type str"

        # There is nothing to do if we do not get any data, since
        # remaining data would not change, and if it is not None,
        # it has already been parsed.
        if data == "":
            return []

        # Update remaining data before we convert line endings to
        # canonical line endings.
        if self.remaining_data is None:
            self.remaining_data = ""
        self.remaining_data += data

        if self.unify_separators:
            # If no separator was specified, we want to split on all
            # known line endings. Convert all known line endings into
            # the canonical line ending and split on this.
            for other_line_ending in _Ordered_Other_Line_Endings:
                self.remaining_data = self.remaining_data.replace(
                    other_line_ending,
                    Canonical_Line_Ending)

        # Split lines on line ending
        detected_lines = self.remaining_data.split(self.separator)

        # If replaced data did not end with the separator, it contains an
        # unterminated line. We save that for the next round. Otherwise
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
