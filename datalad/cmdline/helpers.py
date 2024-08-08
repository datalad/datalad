# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
"""

__docformat__ = 'restructuredtext'

import os
import warnings
from logging import getLogger

lgr = getLogger('datalad.cmdline')


def get_repo_instance(path=os.curdir, class_=None):
    """Returns an instance of appropriate datalad repository for path.
    Check whether a certain path is inside a known type of repository and
    returns an instance representing it. May also check for a certain type
    instead of detecting the type of repository.

    .. deprecated:: 0.16
       Use the pattern `Dataset(get_dataset_root(path)).repo` instead. This
       function will be removed in a future release.

    Parameters
    ----------
    path: str
      path to check; default: current working directory
    class_: class
      if given, check whether path is inside a repository, that can be
      represented as an instance of the passed class.

    Raises
    ------
    RuntimeError, in case cwd is not inside a known repository.
    """
    warnings.warn("get_repo_instance() was deprecated in 0.16. "
                  "It will be removed in a future release.",
                  DeprecationWarning)

    from datalad.distribution.dataset import Dataset
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.gitrepo import GitRepo
    from datalad.utils import get_dataset_root

    if class_ is not None:
        if class_ == AnnexRepo:
            type_ = "annex"
        elif class_ == GitRepo:
            type_ = "git"
        else:
            raise RuntimeError("Unknown class %s." % str(class_))
    else:
        type_ = ''

    dsroot = get_dataset_root(path)
    if not dsroot:
        raise RuntimeError(f"No {type_}s repository found at {path}.")

    return Dataset(dsroot).repo
