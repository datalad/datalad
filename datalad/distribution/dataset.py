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
from os.path import abspath, join as opj, commonprefix, sep, normpath
from six import string_types, PY2
from functools import wraps

from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import InvalidGitRepositoryError, NoSuchPathError
from datalad.support.constraints import Constraint
from datalad.utils import optional_args, expandpath, is_explicit_path
from datalad.utils import swallow_logs
from datalad.utils import getpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.dochelpers import exc_str

lgr = logging.getLogger('datalad.dataset')

lgr.log(5, "Importing dataset")


def _with_sep(path):
    """Little helper to guarantee that path ends with /"""
    return path + sep if not path.endswith(sep) else path


# TODO: use the same piece for resolving paths against Git/AnnexRepo instances
#       (see normalize_path)
def resolve_path(path, ds=None):
    """Resolve a path specification (against a Dataset location)

    Any explicit path (absolute or relative) is returned as an absolute path.
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
        return normpath(opj(ds.path, path))


class Dataset(object):
    __slots__ = ['_path', '_repo', '_id']

    def __init__(self, path):
        self._path = abspath(path)
        self._repo = None
        self._id = None

    def __repr__(self):
        return "<Dataset path=%s>" % self.path

    def __eq__(self, other):
        return self.path == other.path

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
                for cls, ckw, kw in (
                        (AnnexRepo, {'allow_noninitialized': True}, {'init': False}),
                        (GitRepo, {}, {})
                ):
                    if cls.is_valid_repo(self._path, **ckw):
                        try:
                            lgr.debug("Detected %s at %s", cls, self._path)
                            self._repo = cls(self._path, create=False, **kw)
                            break
                        except (InvalidGitRepositoryError, NoSuchPathError, RuntimeError) as exc:
                            lgr.debug("Oops -- guess on repo type was wrong?: %s", exc_str(exc))
                            pass
                if self._repo is None:
                    lgr.info("Failed to detect a valid repo at %s" % self.path)
                else:
                    # reset ID, because we now have a repo attached
                    self._id = None
        elif not isinstance(self._repo, AnnexRepo):
            # repo was initially set to be self._repo but might become AnnexRepo
            # at a later moment, so check if it didn't happen
            if 'git-annex' in self._repo.get_branches():
                # we acquired git-annex branch
                self._repo = AnnexRepo(self._repo.path, create=False)
                # reset ID, because we now have an annex attached
                self._id = None
        return self._repo

    @property
    def id(self):
        """Identifier of the dataset

        Returns
        -------
        str
          This is either a UUID of the dataset's annex, or the SHA sum
          of the current commit of the Git repository (if there is no annex),
          or string composed from the path of the dataset. Any non-UUID ID
          string is prefixed with '_:'
        """
        if self._id is None:
            if self.repo:
                if hasattr(self.repo, 'uuid'):
                    self._id = self.repo.uuid
                if not self._id:
                    # no annex
                    self._id = '_:{}'.format(self.repo.get_hexsha())
            else:
                # not even a VCS
                self._id = '_:{}'.format(self.path.replace(os.sep, '_'))

        return self._id

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

        if name not in repo.get_remotes():
            # Add remote
            repo.add_remote(name, url)
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

    # TODO: RF: Dataset.get_subdatasets to return Dataset instances! (optional?)
    def get_subdatasets(self, pattern=None, fulfilled=None, absolute=False,
                        recursive=False, recursion_limit=None):

        """Get names/paths of all known dataset_datasets (subdatasets),
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
          If True, recurse into all subdatasets and report them too.
        recursion_limit: int or None
          If not None, set the number of subdataset levels to recurse into.
        Returns
        -------
        list(Dataset paths) or None
          None is return if there is not repository instance yet. For an
          existing repository with no subdatasets an empty list is returned.
        """

        if recursion_limit is not None and (recursion_limit <= 0):
            return []

        if pattern is not None:
            raise NotImplementedError

        repo = self.repo
        if repo is None:
            return []

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
        if recursive and (recursion_limit is None or recursion_limit > 1):
            rsm = []
            for sm in submodules:
                rsm.append(sm)
                sdspath = opj(self._path, sm)
                rsm.extend(
                    [opj(sm, sdsh)
                     for sdsh in Dataset(sdspath).get_subdatasets(
                         pattern=pattern, fulfilled=fulfilled, absolute=False,
                         recursive=recursive,
                         recursion_limit=(recursion_limit - 1)
                         if recursion_limit is not None else None)])
            submodules = rsm

        if absolute:
            return [opj(self._path, sm) for sm in submodules]
        else:
            return submodules

    def create_subdataset(self, path,
                          name=None,
                          force=False,
                          description=None,
                          no_annex=False,
                          annex_version=None,
                          annex_backend='MD5E',
                          git_opts=None,
                          annex_opts=None,
                          annex_init_opts=None):
        """Create a subdataset within this dataset

        Creates a new dataset at `path` and adds it as a subdataset to `self`.
        `path` is required to point to a location inside the dataset `self`.

        Parameters
        ----------
        path: str
          path to the subdataset to be created
        name: str
          name of the subdataset
        force: bool
          enforce creation of a subdataset in a non-empty directory
        description: str
          a human-readable description of the dataset, that helps to identify it.
          Note: Doesn't work with `no_annex`
        no_annex: bool
          whether or not to create a pure git repository
        annex_version: str
          version of annex repository to be used
        annex_backend: str
          backend to be used by annex for computing file keys
        git_opts: list of str
          cmdline options to be passed to the git executable
        annex_opts: list of str
          cmdline options to be passed to git-annex
        annex_init_opts: list of str
          cmdline options to be passed to git-annex-init

        Returns
        -------
        Dataset
          the newly created dataset
        """

        # get absolute path (considering explicit vs relative):
        path = resolve_path(path, self)
        if not path.startswith(_with_sep(self.path)):
            raise ValueError("path %s outside dataset %s" % (path, self))

        subds = Dataset(path)

        # create the dataset
        subds.create(force=force,
                     description=description,
                     no_annex=no_annex,
                     annex_version=annex_version,
                     annex_backend=annex_backend,
                     git_opts=git_opts,
                     annex_opts=annex_opts,
                     annex_init_opts=annex_init_opts,
                     # Note:
                     # adding to the superdataset is what we are doing herein!
                     # add_to_super=True would lead to calling ourselves again
                     # and again
                     # While this is somewhat ugly, the issue behind this is a
                     # necessarily slightly different logic of `create` in
                     # comparison to other toplevel functions, which operate on
                     # an existing dataset and possibly on subdatasets.
                     # With `create` we suddenly need to operate on a
                     # superdataset, if add_to_super is True.
                     add_to_super=False)

        # add it as a submodule
        # TODO: clean that part and move it in here (Dataset)
        #       or call install to add the thing inplace
        from .install import _install_subds_inplace
        from os.path import relpath
        return _install_subds_inplace(ds=self, path=subds.path,
                                      relativepath=relpath(subds.path, self.path),
                                      name=name)

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
        self.repo.checkout(whereto)

    def is_installed(self):
        """Returns whether a dataset is installed.

        A dataset is installed when a repository for it exists on the filesystem.

        Returns
        -------
        bool
        """
        return self.path is not None and self.repo is not None

    def get_superdataset(self):
        """Get the dataset's superdataset

        Returns
        -------
        Dataset or None
        """

        # TODO: return only if self is subdataset of the superdataset
        #       (meaning: registered as submodule)?

        from os import pardir
        sds_path = GitRepo.get_toppath(opj(self.path, pardir))
        if sds_path is None:
            return None
        else:
            return Dataset(sds_path)

    def get_containing_subdataset(self, path, recursion_limit=None):
        """Get the (sub-)dataset containing `path`

        Parameters
        ----------
        path : str
          Path to determine the containing (sub-)dataset for
        recursion_limit: int
          limit the subdatasets to take into account to the given number of
          hierarchy levels

        Returns
        -------
        Dataset
        """

        if recursion_limit is not None and (recursion_limit < 1):
            lgr.warning("recursion limit < 1 (%s) always results in self.")
            return self

        if is_explicit_path(path):
            path = resolve_path(path, self)
            if not path.startswith(self.path):
                # TODO: - have dedicated exception
                raise ValueError("path {0} not in dataset {1}.".format(path, self))
            from os.path import relpath
            path = relpath(path, self.path)

        for subds in self.get_subdatasets(recursive=True,
                                          recursion_limit=recursion_limit,
                                          absolute=False):
            common = commonprefix((_with_sep(subds), _with_sep(path)))
            if common.endswith(sep) and common == _with_sep(subds):
                return Dataset(path=opj(self.path, common))
        return self


@optional_args
def datasetmethod(f, name=None, dataset_argname='dataset'):
    """Decorator to bind functions to Dataset class.

    The decorated function is still directly callable and additionally serves
    as method `name` of class Dataset.  To achieve this, the first positional
    argument is redirected to original keyword argument 'dataset_argname'. All
    other arguments stay in order (and keep their names, of course). That
    means, that the signature of the bound function is name(self, a, b) if the
    original signature is name(a, dataset, b) for example.

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
        if len(args) > len(orig_pos) or dataset_argname in kwargs:
            raise TypeError("{0}() takes at most {1} arguments ({2} given):"
                            " {3}".format(name, len(orig_pos), len(args),
                                          ['self'] + [a for a in orig_pos
                                                      if a != dataset_argname]))
        kwargs[dataset_argname] = args[0]
        ds_index = orig_pos.index(dataset_argname)
        for i in range(1, len(args)):
            if i <= ds_index:
                kwargs[orig_pos[i-1]] = args[i]
            elif i > ds_index:
                kwargs[orig_pos[i]] = args[i]
        return f(**kwargs)

    setattr(Dataset, name, apply_func)
    # So we could post-hoc later adjust the documentation string which is assigned
    # within .api
    apply_func.__orig_func__ = f
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


def require_dataset(dataset, check_installed=True, purpose=None):
    """Helper function to resolve a dataset.

    This function tries to resolve a dataset given an input argument,
    or based on the process' working directory, if `None` is given.

    Parameters
    ----------
    dataset : None or path or Dataset
      Some value identifying a dataset or `None`. In the latter case
      a dataset will be searched based on the process working directory.
    check_installed : boold, optional
      If True, an optional check whether the resolved dataset is
      properly installed will be performed.
    purpose : str, optional
      This string will be inserted in error messages to make them more
      informative. The pattern is "... dataset for <STRING>".

    Returns
    -------
    Dataset
      Or raises an exception (InsufficientArgumentsError).
    """
    if dataset is not None and not isinstance(dataset, Dataset):
        dataset = Dataset(dataset)

    if dataset is None:  # possible scenario of cmdline calls
        dspath = GitRepo.get_toppath(getpwd())
        if not dspath:
            raise InsufficientArgumentsError("No dataset found")
        dataset = Dataset(dspath)

    assert(dataset is not None)
    lgr.debug("Resolved dataset{0}: {1}".format(
        'for {}'.format(purpose) if purpose else '',
        dataset))

    if check_installed and not dataset.is_installed():
        raise ValueError("No installed dataset found at "
                         "{0}.".format(dataset.path))

    return dataset
