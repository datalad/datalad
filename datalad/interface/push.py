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
from ..support.constraints import EnsureStr, EnsureNone
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance
from ..log import lgr


class Push(Interface):
    """Push changes to a remote repository.

    Examples:

      ~/MyRepository $ datalad push
      ~/MyRepository $ datalad push MyRemote
    """

    _params_ = dict(
        remote=Parameter(
            args=('remote',),
            doc="Name of the remote repository to push to.",
            constraints=EnsureStr(),
            nargs='?'),
        branch=Parameter(
            args=('branch',),
            doc="branch of the remote repository to push to.",
            nargs='?',
            constraints=EnsureStr() | EnsureNone()))

    @staticmethod
    def __call__(remote='origin', branch=None):

        repo = get_repo_instance()
        repo.git_push(remote + (' ' + branch if branch is not None else ''))
