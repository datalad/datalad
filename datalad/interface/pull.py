# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for performing a git pull
"""

__docformat__ = 'restructuredtext'

from glob import glob
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance
from ..log import lgr


class Pull(Interface):
    """Get changes from a remote repository.

    Examples:

      ~/MyRepository $ datalad pull
      ~/MyRepository $ datalad pull MyRemote
    """

    _params_ = dict(
        remote=Parameter(
            doc="Name of the remote repository to pull from.",
            constraints=EnsureStr(),
            nargs='?'))

    @staticmethod
    def __call__(remote='origin'):

        repo = get_repo_instance()
        repo.git_pull()
