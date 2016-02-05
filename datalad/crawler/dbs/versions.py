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
from os.path import join as opj, exists, lexists, islink, realpath, basename, dirname

from ...dochelpers import exc_str
from ...support.status import FileStatus
from ...support.exceptions import CommandError
from ...utils import auto_repr
from ...utils import swallow_logs
from ...consts import CRAWLER_META_VERSIONS_DIR

import logging
lgr = logging.getLogger('datalad.crawler.dbs')

__docformat__ = 'restructuredtext'

@auto_repr
class SingleVersionDB(object):
    """
    Simple helper to store/retrieve information about the version of the last scraped
    """
    def __init__(self, repo, name=None):
        self.repo = repo
        self.name = name
        self._filepath = opj(repo.path, CRAWLER_META_VERSIONS_DIR, name or repo.git_get_active_branch())

    @property
    def version(self):
        if lexists(self._filepath):
            with open(self._filepath) as f:
                return f.read().strip()

    @version.setter
    def version(self, v):
        d = dirname(self._filepath)
        if not exists(d):
            os.makedirs(d)
        with open(self._filepath, 'w') as f:
            f.write(str(v))
        self.repo.git_add(self._filepath)  # stage to be committed