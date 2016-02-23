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
from os.path import join as opj, exists, lexists, islink, realpath, sep

from ...dochelpers import exc_str
from ...support.status import FileStatus
from ...support.exceptions import CommandError
from ...utils import auto_repr
from ...utils import swallow_logs
from ...consts import CRAWLER_META_STATUSES_DIR

from .base import JsonBaseDB, FileStatusesBaseDB
import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'

__all__ = ['PhysicalFileStatusesDB']

#
# Concrete implementations
#

@auto_repr
class PhysicalFileStatusesDB(FileStatusesBaseDB):
    """Non-persistent DB based on file attributes

    It uses file modification times and size as known to annex to deduce
    if new version is available

    In general should not be used since neither git nor annex stores any files
    meta-information (besides mode, and size) so mtime would get lost while switching
    the branches and dropping the load
    """

    def _get(self, filepath):
        if not lexists(filepath):
            return None

        # I wish I could just test using filesystem stats but that would not
        # be reliable, and also file might not even be here.
        # File might be under git, not annex so then we would need to assess size
        filestat = os.lstat(filepath)
        try:
            with swallow_logs():
                info = self.annex.annex_info(filepath, batch=True)
            size = info['size']
        except (CommandError, TypeError) as exc:
            # must be under git or a plain file
            lgr.debug("File %s must be not under annex, since info failed: %s" % (filepath, exc_str(exc)))
            size = filestat.st_size

        # deduce mtime from the file or a content which it points to. Take the oldest (I wonder
        # if it would bite ;) XXX)
        mtime = filestat.st_mtime
        if islink(filepath):
            filepath_ = realpath(filepath)  # symlinked to
            if exists(filepath_):
                mtime_ = os.stat(filepath_).st_mtime
                mtime = min(mtime_, mtime)
        return FileStatus(
                size=size,
                mtime=mtime
        )

    def _set(self, filepath, status):
        # This DB doesn't implement much of it, besides marking internally that we do care about this file
        pass

    def save(self):
        # nothing for us to do but JsonFileStatusesDB has it so let's keep it common
        pass

    def _remove(self, filepath):
        pass


@auto_repr
class JsonFileStatusesDB(JsonBaseDB, PhysicalFileStatusesDB):
    """Persistent DB to store information about files' size/mtime/filename in a json file
    """

    __version__ = 1
    __crawler_subdir__ = CRAWLER_META_STATUSES_DIR

    def __init__(self, annex, track_queried=True, name=None):
        PhysicalFileStatusesDB.__init__(self, annex, track_queried=track_queried)
        JsonBaseDB.__init__(self, annex, name=name)

    #
    # Defining abstract methods implementations
    #
    def _get_empty_db(self):
        return {'files': {}}

    def _get_loaded_db(self, db):
        """Given a DB loaded from a file, prepare it for being used
        """
        assert (set(db.keys()) == {'db_version', 'files'})
        return db

    def _get_db_to_save(self):
        """Return DB to be saved as JSON file
        """
        return self._db

    def _get_fpath(self, filepath):
        assert (filepath.startswith(self.annex.path))
        fpath = filepath[len(self.annex.path.rstrip(sep)) + 1:]
        return fpath

    def _get_fileattributes_status(self, fpath):
        filepath = self._get_filepath(fpath)
        return PhysicalFileStatusesDB._get(self, filepath)

    def _get(self, filepath):
        # TODO: may be avoid this all fpath -> filepath -> fpath?
        fpath = self._get_fpath(filepath)

        files = self._db['files']
        if fpath not in files:
            return None
        return FileStatus(**files[fpath])

    # TODO: get URL all the way here?
    def _set(self, filepath, status):
        fpath = self._get_fpath(filepath)
        if status is None:
            status_dict = {}
            # get it from the locally available file
            # status = PhysicalFileStatusesDB._get(self, filepath)
            # NOPE since then generated files would keep changing
        else:
            status_dict = {f: getattr(status, f)
                           for f in ('size', 'mtime', 'filename')
                           if getattr(status, f) is not None}
        self._db['files'][fpath] = status_dict

    def _remove(self, filepath):
        fpath = self._get_fpath(filepath)
        if fpath in self._db['files']:
            self._db['files'].pop(fpath)
