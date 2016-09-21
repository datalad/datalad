# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Distribution utility functions

"""

import logging
from os import linesep
from os.path import exists
from os.path import lexists
from os.path import isdir
from os.path import join as opj
from os.path import islink

from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.dochelpers import exc_str

from .dataset import Dataset

lgr = logging.getLogger('datalad.distribution.utils')


def _install_subds_inplace(ds, path, relativepath, name=None):
    """Register an existing repository in the repo tree as a submodule"""
    # FLOW GUIDE EXIT POINT
    # this is an existing repo and must be in-place turned into
    # a submodule of this dataset
    ds.repo.add_submodule(relativepath, url=None, name=name)
    _fixup_submodule_dotgit_setup(ds, relativepath)
    # return newly added submodule as a dataset
    return Dataset(path)


def _fixup_submodule_dotgit_setup(ds, relativepath):
    """Implementation of our current of .git in a subdataset

    Each subdataset/module has its own .git directory where a standalone
    repository would have it. No gitdir files, no symlinks.
    """
    # move .git to superrepo's .git/modules, remove .git, create
    # .git-file
    path = opj(ds.path, relativepath)
    src_dotgit = get_git_dir(path)

    # at this point install always yields the desired result
    # just make sure
    assert(src_dotgit == '.git')


def get_git_dir(path):
    """figure out a repo's gitdir

    '.git' might be a  directory, a symlink or a file

    Parameter
    ---------
    path: str
      currently expected to be the repos base dir

    Returns
    -------
    str
      relative path to the repo's git dir; So, default would be ".git"
    """

    from os.path import isfile
    from os import readlink

    dot_git = opj(path, ".git")
    if not exists(dot_git):
        raise RuntimeError("Missing .git in %s." % path)
    elif islink(dot_git):
        git_dir = readlink(dot_git)
    elif isdir(dot_git):
        git_dir = ".git"
    elif isfile(dot_git):
        with open(dot_git) as f:
            git_dir = f.readline()
            if git_dir.startswith("gitdir:"):
                git_dir = git_dir[7:]
            git_dir = git_dir.strip()

    return git_dir


# TODO: evolved to sth similar to get_containing_subdataset. Therefore probably
# should move into this one as an option. But: consider circular imports!
def install_necessary_subdatasets(ds, path):
    """Installs subdatasets of `ds`, that are necessary to obtain in order
    to have access to `path`.

    Gets the subdataset containing `path` regardless of whether or not it was
    already installed. While doing so, installs everything necessary in between
    the uppermost installed one and `path`.

    Note: `ds` itself has to be installed.

    Parameters
    ----------
    ds: Dataset
    path: str

    Returns
    -------
    Dataset
      the last (deepest) subdataset, that was installed
    """

    assert ds.is_installed()

    # figuring out what dataset to start with:
    start_ds = ds.get_containing_subdataset(path, recursion_limit=None)

    if start_ds.is_installed():
        return start_ds

    # we try to install subdatasets as long as there is anything to
    # install in between the last one installed and the actual thing
    # to get (which is `path`):
    cur_subds = start_ds

    # Note, this is not necessarily `ds`:
    cur_par_ds = start_ds.get_superdataset()
    assert cur_par_ds is not None

    while not cur_subds.is_installed():
        lgr.info("Installing subdataset {0} in order to get "
                 "{1}".format(cur_subds, path))
        cur_par_ds.install(cur_subds.path)
        cur_par_ds = cur_subds

        # Note: PathOutsideRepositoryError should not happen here.
        # If so, there went something fundamentally wrong, so raise something
        # different, to not let the caller mix it up with a "regular"
        # PathOutsideRepositoryError from above. (Although it could be
        # detected via its `repo` attribute)
        try:
            cur_subds = \
                cur_subds.get_containing_subdataset(path, recursion_limit=None)
        except PathOutsideRepositoryError as e:
            raise RuntimeError("Unexpected failure: {0}".format(exc_str(e)))

    return cur_subds
