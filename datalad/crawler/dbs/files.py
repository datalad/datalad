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

import os
from os.path import join as opj, exists, lexists, islink, realpath, basename, normpath
from os.path import isabs

from ...dochelpers import exc_str
from ...support.status import FileStatus
from ...support.exceptions import CommandError
from ...utils import auto_repr
from ...utils import swallow_logs
from ...utils import find_files
from ...consts import HANDLE_META_DIR

import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'


@auto_repr
class AnnexFileAttributesDB(object):

    def __init__(self, annex, track_queried=True):
        """

        Parameters
        ----------
        annex : AnnexRepo
          Annex repository which will be consulted on the size and full path
        track_queried : bool, optional
          Either to track what file paths were queried
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

    def _get_fullpath(self, fpath):
        if isabs(fpath):
            return normpath(fpath)
        else:
            return normpath(opj(self.annex.path, fpath))

    # TODO: think if default should be provided
    def get(self, fpath):
        """Given a file (under annex) relative path, return its status record

        annex information about size etc might be used if load is not available

        Parameters
        ----------
        fpath: str
          Path (relative to the top of the repo) of the file to get stats of
        """
        filepath = self._get_fullpath(fpath)
        if self._track_queried:
            self._queried_filepaths.add(filepath)

        if not lexists(filepath):
            return None

        # I wish I could just test using filesystem stats but that would not
        # be reliable, and also file might not even be here.
        # File might be under git, not annex so then we would need to assess size
        filestat = os.lstat(filepath)
        try:
            with swallow_logs():
                info = self.annex.annex_info(fpath)
            size = info['size']
        except (CommandError, TypeError) as exc:
            # must be under git or a plain file
            lgr.debug("File %s must be not under annex, since info failed: %s" % (filepath, exc_str(exc)))
            size = filestat.st_size

        # deduce mtime from the file or a content which it points to. Take the oldest (I wonder
        # if it would bite ;) XXX)
        mtime = filestat.st_mtime

        if islink(fpath):
            filepath_ = realpath(filepath)  # symlinked to
            if exists(filepath_):
                mtime_ = os.stat(filepath_).st_mtime
                mtime = min(mtime_, mtime)

        return FileStatus(
            size=size,
            mtime=mtime
        )

    def set(self, fpath, status=None):
        # This DB doesn't implement much of it, besides marking internally that we do care about this file
        filepath = self._get_fullpath(fpath)
        if self._track_queried:
            self._queried_filepaths.add(filepath)
        pass

    def is_different(self, fpath, status, url=None):
        """Return True if file pointed by fpath newer in status
        """
        # TODO: make use of URL -- we should validate that url is among those associated
        #  with the file
        old_status = self.get(fpath)
        if status.filename and not old_status.filename:
            old_status.filename = basename(fpath)
        return old_status != status

    def get_obsolete(self):
        """Returns paths which weren't queried, thus must have been deleted

        Note that it doesn't track across branches etc.
        """
        if not self._track_queried:
            raise RuntimeError("Cannot determine which files were removed since track_queried was set to False")
        obsolete = []
        # those aren't tracked by annexificator
        datalad_path = opj(self.annex.path, HANDLE_META_DIR)
        for fpath in find_files('.*', topdir=self.annex.path):
            filepath = self._get_fullpath(fpath)
            if filepath.startswith(datalad_path):
                continue
            if fpath not in self._queried_filepaths:
                obsolete.append(filepath)
        return obsolete

    def reset(self):
        """Reset internal state, e.g. about known queried filedpaths"""
        self._queried_filepaths = set()