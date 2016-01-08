# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""(comparable) descriptors of the file status

"""

__docformat__ = 'restructuredtext'

from ..utils import auto_repr

@auto_repr
class FileStatus(object):
    """Description of the file status to e.g. check if newer version is available

    """

    def __init__(self, size=None, mtime=None, filename=None):
        self.size = size
        self.mtime = mtime
        # TODO: actually not sure if filename should be here!
        self.filename = filename

    def __eq__(self, other):
        # Disallow comparison of empty ones
        if self.size is None and self.mtime is None and self.filename is None:
            return NotImplemented
        if other.size is None and other.mtime is None and other.filename is None:
            return NotImplemented

        return \
            self.size == other.size and \
            self.mtime == other.mtime and \
            self.filename == other.filename

    def __ne__(self, other):
        out = self == other
        if isinstance(out, bool):
            return not out
        elif out is NotImplemented:
            return out
        else:
            raise RuntimeError("Unknown return %r" % (out,))