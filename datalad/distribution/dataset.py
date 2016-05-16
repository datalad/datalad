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
from os.path import abspath, join as opj, normpath
from six import string_types, PY2
from functools import wraps

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import InvalidGitRepositoryError, NoSuchPathError
from datalad.support.constraints import Constraint
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
        # TODO: Check whether we should use PWD instead of CWD here. Is it done
        # by abspath?
        return abspath(path)
    else:
        return normpath(opj(ds.path, path))


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


        Parameters
        ----------
        pattern : None
          Not implemented
        fulfilled : None or bool
          If not None, return either only present or absent datasets.
        absolute : bool
          If True, absolute paths will be returned.
        recursive : bool
          If True, recurse into all subdatasets and report their dataset
          handles too.

        Returns
        -------
        list(Dataset paths) or None
          None is return if there is not repository instance yet. For an
          existing repository with no subdatasets an empty list is returned.
        """
        if pattern is not None:
            raise NotImplementedError

        repo = self.repo
        if repo is None:
            return

        # check whether we have anything in the repo. if not go home early
        if not repo.repo.head.is_valid():
            return []

        try:
            submodules = repo.get_submodules()
        except InvalidGitRepositoryError:
            # this happens when we access a repository with a submodule that
            # has no commits, hence doesn't appear in the index and
            # 'git submodule status' also doesn't list it
            return []

        # filter if desired
        if fulfilled is None:
            submodules = [sm.path for sm in submodules]
        else:
            submodules = [sm.path for sm in submodules
                          if sm.module_exists() == fulfilled]

        # expand list with child submodules. keep all paths relative to parent
        # and convert jointly at the end
        if recursive:
            rsm = []
            for sm in submodules:
                rsm.append(sm)
                sdspath = opj(self._path, sm)
                rsm.extend(
                    [opj(sm, sdsh)
                     for sdsh in Dataset(sdspath).get_dataset_handles(
                         pattern=pattern, fulfilled=fulfilled, absolute=False,
                         recursive=recursive)])
            submodules = rsm

        if absolute:
            return [opj(self._path, sm) for sm in submodules]
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

    # TODO maybe needs to get its own interface
    def remember_state(self, message, auto_add_changes=True, version=None):
        """
        Parameters
        ----------
        auto_add_changes: bool
        message: str
        update_superdataset: bool
        version: str
        """
        if not self.is_installed():
            raise RuntimeError(
                "cannot remember a state when a dataset is not yet installed")
        repo = self.repo
        if auto_add_changes:
            repo.annex_add('.')
        repo.commit(message)
        if version:
            repo._git_custom_command('', 'git tag "{0}"'.format(version))

    def recall_state(self, whereto):
        """Something that can be used to checkout a particular state
        (tag, commit) to "undo" a change or switch to a otherwise desired
        previous state.

        Parameters
        ----------
        whereto: str
        """
        if not self.is_installed():
            raise RuntimeError(
                "cannot remember a state when a dataset is not yet installed")
        self.repo.git_checkout(whereto)

    def is_installed(self):
        """Returns whether a dataset is installed.

        A dataset is installed when a repository for it exists on the filesystem.

        Returns
        -------
        bool
        """
        return self.path is not None and self.repo is not None


@optional_args
def datasetmethod(f, name=None):
    """Decorator to bind functions to Dataset class.

    The decorated function is still directly callable and additionally serves
    as method `name` of class Dataset.
    To achieve this, the first positional argument is redirected to original
    keyword argument 'dataset'. All other arguments stay in order (and keep
    their names, of course). That means, that the signature of the bound
    function is name(self, a, b) if the original signature is
    name(a, dataset, b) for example.

    The decorator has no effect on the actual function decorated with it.
    """
    if not name:
        name = f.func_name if PY2 else f.__name__

    @wraps(f)
    def apply_func(*args, **kwargs):
        """Wrapper function to assign arguments of the bound function to
        original function.

        Note
        ----
        This wrapper is NOT returned by the decorator, but only used to bind
        the function `f` to the Dataset class.
        """
        kwargs = kwargs.copy()
        from inspect import getargspec
        orig_pos = getargspec(f).args

        # If bound function is used with wrong signature (especially by
        # explicitly passing a dataset, let's raise a proper exception instead
        # of a 'list index out of range', that is not very telling to the user.
        if len(args) > len(orig_pos) or 'dataset' in kwargs:
            raise TypeError("{0}() takes at most {1} arguments ({2} given):"
                            " {3}".format(name, len(orig_pos), len(args),
                                          ['self'] + [a for a in orig_pos
                                                      if a != 'dataset']))
        kwargs['dataset'] = args[0]
        ds_index = orig_pos.index('dataset')
        for i in range(1, len(args)):
            if i <= ds_index:
                kwargs[orig_pos[i-1]] = args[i]
            elif i > ds_index:
                kwargs[orig_pos[i]] = args[i]
        return f(**kwargs)

    setattr(Dataset, name, apply_func)
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
