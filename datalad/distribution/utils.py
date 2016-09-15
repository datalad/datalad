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
from genericpath import exists, isdir
from os.path import join as opj, islink

from datalad.distribution.dataset import Dataset


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