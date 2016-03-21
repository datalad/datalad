# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements class Dataset
"""

import logging
import os
from os.path import isabs, abspath, join as opj, expanduser, expandvars
from six import string_types

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import InvalidGitRepositoryError, NoSuchPathError
from datalad.support.constraints import EnsureDatasetAbsolutePath, Constraint
from datalad.utils import optional_args, expandpath, is_explicit_path
from datalad.utils import swallow_logs

lgr = logging.getLogger('datalad.dataset')


def resolve_path(path, ds=None):
    """Resolve a path specification (against a Dataset location)

    Any explicit path (absolute or relative) is return as an absolute path.
    In case of an explicit relative path, the current working directory is
    used as a reference. Any non-explicit relative path is resolved against
    as dataset location, i.e. considered relative to the location of the
    dataset. If no dataset is provided, the current working directory is
    used.

    Returns
    -------
    Absolute path
    """
    path = expandpath(path, force_absolute=False)
    if is_explicit_path(path):
        return abspath(path)
    if ds is None:
        # no dataset given, use CWD as reference
        return abspath(path)
    else:
        return opj(ds.path, path)


class Dataset(object):
    __slots__ = ['_path', '_repo']

    def __init__(self, path):
        self._path = abspath(path)
        self._repo = None

    def __repr__(self):
        return "<Dataset path=%s>" % self.path

    @property
    def path(self):
        """path to the dataset"""
        return self._path

    @property
    def repo(self):
        """Get an instance of the version control system/repo for this dataset,
        or None if there is none yet.

        If creating an instance of GitRepo is guaranteed to be really cheap
        this could also serve as a test whether a repo is present.

        Returns
        -------
        GitRepo
        """
        if self._repo is None:
            with swallow_logs():
                try:
                    self._repo = AnnexRepo(self._path, create=False, init=False)
                except (InvalidGitRepositoryError, NoSuchPathError, RuntimeError):
                    try:
                        self._repo = GitRepo(self._path, create=False)
                    except (InvalidGitRepositoryError, NoSuchPathError):
                        pass
        elif not isinstance(self._repo, AnnexRepo):
            # repo was initially set to be self._repo but might become AnnexRepo
            # at a later moment, so check if it didn't happen
            if 'git-annex' in self._repo.git_get_branches():
                # we acquired git-annex branch
                self._repo = AnnexRepo(self._repo.path, create=False)
        return self._repo

    def register_sibling(self, name, url, publish_url=None, verify=None):
        """Register the location of a sibling dataset under a given name.

        Optionally, different URLs can be given for retrieving information from
        the sibling and for publishing information to it.
        This is a cheap operation that does not confirm that at the given
        location an actual sibling dataset is available, unless verify is set.
        The value "dataset" verifies, that at the given URL an accessible
        dataset is available and the value "sibling" furthermore verifies, that
        this dataset shares at least one commit with self.

        Parameters
        ----------
        name
        url
        publish_url
        verify
          None | "dataset" | "sibling"
        """
        repo = self.repo

        if verify is not None:
            raise NotImplementedError("TODO: verify not implemented yet")

        if name not in repo.git_get_remotes():
            # Add remote
            repo.git_remote_add(name, url)
            if publish_url is not None:
                # set push url:
                repo._git_custom_command('', ["git", "remote",
                                              "set-url",
                                              "--push", name,
                                              publish_url])
            lgr.info("Added remote '%s':\n %s (pull)\n%s (push)." %
                     (name, url, publish_url if publish_url else url))
        else:
            lgr.warning("Remote '%s' already exists. Ignore.")
            raise ValueError("'%s' already exists. Couldn't register sibling.")

    def get_dataset_handles(self, pattern=None, fulfilled=None, absolute=False,
                            recursive=False):
        """Get names/paths of all known dataset_handles (subdatasets),
        optionally matching a specific name pattern.

        If fulfilled is True, only paths to fullfiled handles are returned,
        if False, only paths to unfulfilled handles are returned.


        Parameters
        ----------
        pattern
        fulfilled

        Returns
        -------
        list(Dataset) or None
          None is return if there is not repository instance yet. For an
          existing repository with no subdatasets an empty list is returned.
        """
        if pattern is not None:
                raise NotImplementedError

        repo = self.repo
        if repo is None:
            return

        cmd = ["git", "submodule", "status"]
        if recursive:
            cmd.append("--recursive")
        out, err = repo._git_custom_command('', cmd)

        lines = [line.split() for line in out.splitlines()]
        if fulfilled is None:
            submodules = [line[1] for line in lines]
        elif not fulfilled:
            submodules = [line[1] for line in lines if line[0].startswith('-')]
        else:
            submodules = [line[1] for line in lines if not line[0].startswith('-')]

        if absolute:
            return [opj(self._path, submodule) for submodule in submodules]
        else:
            return submodules

#    def get_file_handles(self, pattern=None, fulfilled=None):
#        """Get paths to all known file_handles, optionally matching a specific
#        name pattern.
#
#        If fulfilled is True, only paths to fullfiled handles are returned,
#        if False, only paths to unfulfilled handles are returned.
#
#        Parameters
#        ----------
#        pattern: str
#        fulfilled: bool
#
#        Returns
#        -------
#        list of str
#          (paths)
#        """
#        raise NotImplementedError("TODO")

    def remember_state(self, auto_add_changes=True, message=str,
                       version=None):
        """
        Parameters
        ----------
        auto_add_changes: bool
        message: str
        update_superdataset: bool
        version: str
        """
        raise NotImplementedError("TODO")

    def recall_state(self, whereto):
        """Something that can be used to checkout a particular state
        (tag, commit) to "undo" a change or switch to a otherwise desired
        previous state.

        Parameters
        ----------
        whereto: str
        """
        raise NotImplementedError("TODO")

    def is_installed(self, ensure="complete"):
        """Returns whether a dataset is installed.

        Several flavors of "installed" can be tested. By default, a dataset is
        installed if a worktree and a VCS repository are present. Alternative
        to "complete" is "vcs".

        Parameters
        ----------
        ensure: str

        Returns
        -------
        bool
        """
        # TODO: Define what exactly to test for, when different flavors are
        # used.
        if self.get_path() is not None and self.repo is not None:
            return True
        else:
            return False


@optional_args
def datasetmethod(f, name=None):
    """Decorator to bind functions to Dataset class.
    """
    if not name:
        name = f.func_name
    setattr(Dataset, name, f)
    return f


# Note: Cannot be defined with constraints.py, since then dataset.py needs to
# be imported from constraints.py, which needs to be imported from dataset.py
# for another constraint
class EnsureDataset(Constraint):

    def __call__(self, value):
        if isinstance(value, Dataset):
            return value
        elif isinstance(value, string_types):
            return Dataset(path=value)
        else:
            raise ValueError("Can't create Dataset from %s." % type(value))

    # TODO: Proper description? Mentioning Dataset class doesn't make sense for
    # commandline doc!
    def short_description(self):
        return "Dataset"

    def long_description(self):
        return """Value must be a Dataset or a valid identifier of a Dataset
        (e.g. a path)"""
