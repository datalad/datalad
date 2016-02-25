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

        same = \
            self.size == other.size and \
            self.filename == other.filename
        if not same:
            return False

        # now deal with time.

        # TODO: provide a config option for mtime comparison precision
        #  we might want to claim times equal up to a second precision
        #  since e.g. some file systems do not even store sub-sec timing
        # TODO: config crawl.mtime_delta

        # if any of them int and another float -- we need to trim float to int
        if self.mtime == other.mtime:
            return True
        elif self.mtime is None or other.mtime is None:
            return False

        # none is None if here and not equal exactly
        if isinstance(self.mtime, int) or isinstance(other.mtime, int):
            return int(self.mtime) == int(other.mtime)
        return False

    def __ne__(self, other):
        out = self == other
        if isinstance(out, bool):
            return not out
        elif out is NotImplemented:
            return out
        else:
            raise RuntimeError("Unknown return %r" % (out,))