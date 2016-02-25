# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Base classes for various DBs

"""

import os
import json
from abc import ABCMeta, abstractmethod, abstractproperty

from os.path import join as opj, exists, lexists, realpath, basename, dirname
from os.path import normpath
from os.path import isabs

from ...utils import auto_repr
from ...utils import find_files
from ...consts import HANDLE_META_DIR

import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'


@auto_repr
class JsonBaseDB(object):
    """
    Base class for DBs which would store to Json files
    """

    __metaclass__ = ABCMeta

    def __init__(self, repo, name=None):
        #super(JsonBaseDB, self).__init__()
        self.repo = repo
        self.name = name
        self._filepath = None
        self._loaded = None
        self.__db = None

    def _assure_loaded(self):
        """Make it lazy loading/creation so we get actual active branch where it is used
        """
        if self._filepath is not None:
            return
        self._filepath = opj(realpath(self.repo.path),
                     self.__class__.__crawler_subdir__,
                     (self.name or self.repo.git_get_active_branch())+'.json')
        if lexists(self._filepath):
            self.load()
            self._loaded = True
        else:
            self.__db = self.get_empty_db()
            self._loaded = False  # so we don't bother saving an empty one if was not loaded

    @property
    def _db(self):
        self._assure_loaded()
        return self.__db

    def load(self):
        self._assure_loaded()
        with open(self._filepath) as f:
            json_db = json.load(f)  # return f.read().strip()
        self.__db = self._get_loaded_db(json_db)

    def save(self):
        if self._filepath is None:
            # Nothing to do
            return
        db = self._get_db_to_save()
        if (not self._loaded) and (db == self.get_empty_db()):
            lgr.debug("DB %s which we defaulted to found to be empty, not saving" % self)
            return

        d = dirname(self._filepath)
        if not exists(d):
            os.makedirs(d)
        lgr.debug("Writing %s to %s" % (self.__class__.__name__, self._filepath))
        with open(self._filepath, 'w') as f:
            json.dump(db, f, indent=2, sort_keys=True, separators=(',', ': '))
        self.repo.git_add(self._filepath)  # stage to be committed

    @property
    def db_version(self):
        return self._db['db_version']

    def get_empty_db(self):
        """Return default empty DB.  Relies on subclass'es specific"""
        db = self._get_empty_db()
        db['db_version'] = self.__class__.__version__
        return db

    @abstractmethod
    def _get_empty_db(self):
        pass

    @abstractmethod
    def _get_loaded_db(self, db):
        """Given a DB loaded from a file, prepare it for being used
        """
        pass

    @abstractmethod
    def _get_db_to_save(self):
        """Return DB to be saved as JSON file
        """
        pass


@auto_repr
class FileStatusesBaseDB(object):
    """Base class for DBs to monitor status of the files
    """

    def __init__(self, annex, track_queried=True):
        """

        Parameters
        ----------
        annex : AnnexRepo
          Annex repository which will be consulted on the size and full path
        track_queried : bool, optional
          Either to track what file paths were queried
        """
        # with all the multiple inheritance smth is not working out as should
        # super(FileStatusesBaseDB, self).__init__()
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

    def _get_filepath(self, fpath):
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
        filepath = self._get_filepath(fpath)
        if self._track_queried:
            self._queried_filepaths.add(filepath)

        return self._get(filepath)

    def _get(self, filepath):
        raise NotImplementedError("must be defined in subclasses")


    def set(self, fpath, status=None):
        """Set a new status for the fpath. If status is None, get from available file
        """
        filepath = self._get_filepath(fpath)
        if self._track_queried:
            self._queried_filepaths.add(filepath)
        self._set(filepath, status)

    def _set(self, filepath, status):
        raise NotImplementedError("must be defined in subclasses")

    def remove(self, fpath):
        self._remove(self._get_filepath(fpath))

    def _remove(self, filepath):
        raise NotImplementedError("must be defined in subclasses")

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
        """Returns full paths for files which weren't queried, thus must have been deleted

        Note that it doesn't track across branches etc.
        """
        if not self._track_queried:
            raise RuntimeError("Cannot determine which files were removed since track_queried was set to False")
        obsolete = []
        # those aren't tracked by annexificator
        datalad_path = opj(self.annex.path, HANDLE_META_DIR)
        for fpath in find_files('.*', topdir=self.annex.path):
            filepath = self._get_filepath(fpath)
            if filepath.startswith(datalad_path):
                continue
            if fpath not in self._queried_filepaths:
                obsolete.append(filepath)
        return obsolete

    def reset(self):
        """Reset internal state, e.g. about known queried filedpaths"""
        self._queried_filepaths = set()
