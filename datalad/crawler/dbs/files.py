# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""File-based "DB" which uses file modification times to deduce if new version is available

"""

__docformat__ = 'restructuredtext'

import os
from os.path import expanduser, join as opj, exists, isabs, lexists, islink, realpath

from ...support.status import FileStatus
from ...utils import auto_repr

@auto_repr
class AnnexFileAttributesDB(object):

    def __init__(self, annex, track_queried=True):
        """

        Parameters
        ----------
        annex : AnnexRepo
          Annex repository which will be consulted on the size and full path
        """
        self.annex = annex
        # which file paths were referred
        self._track_queried = track_queried
        self._queried_filepaths = set()

    @property
    def track_queried(self):
        return self._track_queried

    @property
    def queried_filepaths(self):
        return self._queried_filepaths

    # TODO: think if default should be provided
    def get(self, fpath):
        """Given a file (under annex) relative path, return its status record

        annex information about size etc might be used if load is not available
        """
        filepath = opj(self.annex.path, fpath)
        if self._track_queried:
            self._queried_filepaths.add(filepath)
        assert(lexists, filepath)  # of check and return None?
        # I wish I could just test using filesystem stats but that would not
        # be reliable, and also file might not even be here.
        # if self.repo.file_has_content(filepath)
        # TODO: that is where doing it once for all files under annex might be of benefit
        info = self.annex.annex_info(fpath)
        # deduce mtime from the file or a content which it points to. Take the oldest (I wonder
        # if it would bite ;) XXX)
        mtime = os.stat(filepath).st_mtime

        if islink(fpath):
            filepath_ = realpath(filepath)  # symlinked to
            if exists(filepath_):
                mtime_ = os.stat(filepath_).st_mtime
                mtime = min(mtime_, mtime)

        return FileStatus(
            size=info['size'],
            mtime=mtime
        )

    def is_different(self, fpath, status):
        """Return True if file pointed by fpath newer according to the status
        """
        old_status = self.get(fpath)
        return old_status != status