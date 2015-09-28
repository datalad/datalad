# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for getting a handle's content
"""

__docformat__ = 'restructuredtext'

from glob import glob
from .base import Interface
from ..support.param import Parameter
from ..support.constraints import EnsureStr
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance
from ..log import lgr


class Get(Interface):
    """Get dataset's content from a remote repository.

    Examples:

      $ datalad get foo/*
    """

    _params_ = dict(
        paths=Parameter(
            doc="path(s) to data content that is to be obtained",
            constraints=EnsureStr(),
            metavar='file',
            nargs='+'))

    def __call__(self, paths):

        try:
            handle = get_repo_instance(class_=AnnexRepo)
        except RuntimeError as e:
            lgr.error(str(e))
            return -1  # TODO: How is this properly done?

        # 'paths' comes as a list
        # Expansions (like globs) provided by the shell itself are already
        # done. But: We don't know exactly what shells we are running on and
        # what it may provide or not. Therefore, make any expansion we want to
        # guarantee, per item of the list:

        expanded_list = []
        [expanded_list.extend(glob(item)) for item in paths]
        handle.annex_get(expanded_list)
