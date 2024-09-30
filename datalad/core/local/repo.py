# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" Core repository-related functionality

"""

import logging

from datalad.support.exceptions import (
    InvalidAnnexRepositoryError,
    InvalidGitRepositoryError,
    NoSuchPathError,
)

lgr = logging.getLogger('datalad.core.local.repo')

__all__ = ["repo_from_path"]


def repo_from_path(path):
    """Get a Repo instance from a path.

    Parameters
    ----------
    path : path-like
      Root path of the repository.

    Returns
    -------
    Repo
      Repo instance matching the type of the repository at path.

    Raises
    ------
    ValueError
      If no repository could be found at the path, or if its type could not
      be determined.
    """
    # keep the imports local for now until it is clearer what the module setup
    # will be
    from datalad.support.annexrepo import AnnexRepo
    from datalad.support.gitrepo import GitRepo

    repo = None
    for cls, ckw, kw in (
            # Non-initialized is okay. We want to figure the correct instance
            # to represent what's there - that's it.
            (AnnexRepo, {'allow_noninitialized': True}, {'init': False}),
            (GitRepo, {}, {})
    ):
        if not cls.is_valid_repo(path, **ckw):
            continue

        try:
            lgr.log(5, "Detected %s at %s", cls, path)
            repo = cls(path, create=False, **kw)
            break
        except (InvalidGitRepositoryError, NoSuchPathError,
                InvalidAnnexRepositoryError) as exc:
            lgr.log(
                5,
                "Ignore exception after inappropriate repository type guess: "
                "%s", exc)

    if repo is None:
        raise ValueError('No repository at {}'.format(path))

    return repo
