# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to git-annex by Joey Hess.

For further information on git-annex see https://git-annex.branchable.com/.

"""

import logging

from weakref import WeakValueDictionary

from datalad.core.dataset import RepoInterface
from datalad.core.dataset.gitrepo import GitRepo
from datalad.dochelpers import (
    borrowdoc,
)
from datalad.support.exceptions import (
    InvalidGitRepositoryError,
    NoSuchPathError,
)

lgr = logging.getLogger('datalad.core.dataset.annexrepo')


class AnnexRepo(GitRepo, RepoInterface):
    """Representation of an git-annex repository.
    """

    # Begin Flyweight:
    _unique_instances = WeakValueDictionary()

    def _flyweight_invalid(self):
        return not self.is_valid_annex(allow_noninitialized=True)

    # End Flyweight:

    # To be assigned and checked to be good enough upon first call to AnnexRepo
    # 6.20160923 -- --json-progress for get
    # 6.20161210 -- annex add  to add also changes (not only new files) to git
    # 6.20170220 -- annex status provides --ignore-submodules
    # 6.20180416 -- annex handles unicode filenames more uniformly
    # 6.20180913 -- annex fixes all known to us issues for v6
    # 7          -- annex makes v7 mode default on crippled systems. We demand it for consistent operation
    # 7.20190503 -- annex introduced mimeencoding support needed for our text2git
    GIT_ANNEX_MIN_VERSION = '7.20190503'

    @borrowdoc(GitRepo, 'is_valid_git')
    def is_valid_annex(self, allow_noninitialized=False, check_git=True):

        initialized_annex = (self.is_valid_git() if check_git else True) and (
            self.dot_git / 'annex').exists()

        if allow_noninitialized:
            try:
                return initialized_annex or (
                    (self.is_valid_git() if check_git else True)
                    and self.is_with_annex()
                )
            except (NoSuchPathError, InvalidGitRepositoryError):
                return False
        else:
            return initialized_annex
