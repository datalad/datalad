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

import os
import json
from os.path import join as opj, exists, lexists, islink, realpath, basename, dirname
from collections import OrderedDict
from distutils.version import LooseVersion
from six import iteritems

from ...dochelpers import exc_str
from ...utils import auto_repr
from ...consts import CRAWLER_META_VERSIONS_DIR


import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'

@auto_repr
class SingleVersionDB(object):
    """
    Simple helper to store/retrieve information about the version of the last scraped
    """
    __version__ = 1

    def __init__(self, repo, name=None):
        self.repo = repo
        self.name = name
        self._filepath = opj(realpath(repo.path),
                             CRAWLER_META_VERSIONS_DIR,
                             (name or repo.git_get_active_branch())+'.json')
        self._db = {'db_version': SingleVersionDB.__version__,
                    'version': None,
                    'versions': OrderedDict()
                    }
        if lexists(self._filepath):
            self.load()

    def load(self):
        with open(self._filepath) as f:
            db = json.load(f)  # return f.read().strip()
        assert(set(db.keys()) == {'db_version', 'version', 'versions'})
        assert(db['db_version'] == SingleVersionDB.__version__)
        db['versions'] = OrderedDict(db['versions'])
        self._db = db

    def save(self):
        db = self._db.copy()
        # since we have it ordered, let's store as list of items
        db['versions'] = list(db['versions'].items())
        d = dirname(self._filepath)
        if not exists(d):
            os.makedirs(d)
        lgr.debug("Writing versionsdb to %s" % self._filepath)
        with open(self._filepath, 'w') as f:
            json.dump(db, f, indent=2, sort_keys=True, separators=(',', ': '))
        self.repo.git_add(self._filepath)  # stage to be committed

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
