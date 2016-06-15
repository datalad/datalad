# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Simple helper to store/retrieve information about the version of the last scraped

"""

from collections import OrderedDict
from six import iteritems

from ...utils import auto_repr
from ...consts import CRAWLER_META_VERSIONS_DIR

from .base import JsonBaseDB

import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'


@auto_repr
class SingleVersionDB(JsonBaseDB):
    """
    Simple helper to store/retrieve information about the last scraped version

    Since we do not expect many changes being done to this DB, it also
    saves its state into the file upon any change
    """
    __version__ = 1
    __crawler_subdir__ = CRAWLER_META_VERSIONS_DIR

    #
    # Defining abstract methods implementations
    #
    def _get_empty_db(self):
        return {'version': None,
                'versions': OrderedDict()}

    def _get_loaded_db(self, db):
        """Given a DB loaded from a file, prepare it for being used
        """
        assert (set(db.keys()) == {'db_version', 'version', 'versions'})
        # no compatibility layers for now
        assert (db['db_version'] == self.__class__.__version__)
        db['versions'] = OrderedDict(db['versions'])
        return db

    def _get_db_to_save(self):
        """Return DB to be saved as JSON file
        """
        db = self._db.copy()
        # since we have it ordered, let's store it as a list of items
        db['versions'] = list(db['versions'].items())
        return db

    #
    # Custom properties and methods
    #
    @property
    def version(self):
        return self._db['version']

    @version.setter
    def version(self, v):
        self._db['version'] = v
        self.save()


    @property
    def versions(self):
        return self._db['versions']

    # @versions.setter
    # def versions(self, v):
    #     self._db['versions'] = v
    #     self.save()

    def update_versions(self, new_versions):
        """Update known versions with new information
        """
        versions = self._db['versions']
        for new_version, new_fpaths in iteritems(new_versions):
            if new_version not in versions:
                # TODO: check that it is newer!?
                versions[new_version] = {}
            fpaths = versions[new_version]
            for new_fpath, entry in iteritems(new_fpaths):
                if new_fpath not in fpaths:
                    # new new_fpath
                    fpaths[new_fpath] = {}
                if entry in fpaths[new_fpath] and entry != fpaths[new_fpath]:
                    raise NotImplementedError("conflict resolutions for when new item added for the same entry")
                else:
                    fpaths[new_fpath] = entry
        self.save()
