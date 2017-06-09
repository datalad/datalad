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
from os.path import abspath
from os.path import commonprefix
from os.path import curdir
from os.path import exists
from os.path import join as opj
from os.path import normpath, isabs
from os.path import pardir
from os.path import realpath
from os.path import relpath
from os.path import sep
from weakref import WeakValueDictionary
from six import PY2
from six import string_types
from six import add_metaclass
import wrapt

from datalad.config import ConfigManager
from datalad.consts import LOCAL_CENTRAL_PATH
from datalad.dochelpers import exc_str
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import Constraint
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import InvalidGitRepositoryError
from datalad.support.gitrepo import NoSuchPathError
from datalad.support.repo import Flyweight
from datalad.support.network import RI

from datalad.utils import getpwd
from datalad.utils import optional_args, expandpath, is_explicit_path, \
    with_pathsep
from datalad.utils import swallow_logs
from datalad.utils import get_dataset_root


lgr = logging.getLogger('datalad.dataset')
lgr.log(5, "Importing dataset")


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
    # TODO: normpath?!
    if is_explicit_path(path):
        return abspath(path)
    # no dataset given, use CWD as reference
    # note: abspath would disregard symlink in CWD
    top_path = getpwd() \
        if ds is None else ds.path if isinstance(ds, Dataset) else ds
    return normpath(opj(top_path, path))


@add_metaclass(Flyweight)
class Dataset(object):

    # Begin Flyweight
    _unique_instances = WeakValueDictionary()

    @classmethod
    def _flyweight_id_from_args(cls, *args, **kwargs):

        if args:
            # to a certain degree we need to simulate an actual call to __init__
            # and make sure, passed arguments are fitting:
            # TODO: Figure out, whether there is a cleaner way to do this in a
            # generic fashion
            assert('path' not in kwargs)
            path = args[0]
            args = args[1:]
        elif 'path' in kwargs:
            path = kwargs.pop('path')
        else:
            raise TypeError("__init__() requires argument `path`")

        if path is None:
            raise AttributeError

        # Custom handling for few special abbreviations
        path_ = path
        if path == '^':
            # get the topmost dataset from current location. Note that 'zsh'
            # might have its ideas on what to do with ^, so better use as -d^
            path_ = Dataset(curdir).get_superdataset(topmost=True).path
        elif path == '///':
            # TODO: logic/UI on installing a central dataset could move here
            # from search?
            path_ = LOCAL_CENTRAL_PATH
        if path != path_:
            lgr.debug("Resolved dataset alias %r to path %r", path, path_)

        # Sanity check for argument `path`:
        # raise if we cannot deal with `path` at all or
        # if it is not a local thing:
        path_ = RI(path_).localpath

        # we want an absolute path, but no resolved symlinks
        if not isabs(path_):
            path_ = opj(getpwd(), path_)

        # use canonical paths only:
        path_ = normpath(path_)
        kwargs['path'] = path_
        return path_, args, kwargs
    # End Flyweight

    def __init__(self, path):
        self._path = path
        self._repo = None
        self._id = None
        self._cfg = None

    def __repr__(self):
        return "<Dataset path=%s>" % self.path

    def __eq__(self, other):
        if not hasattr(other, 'path'):
            return False
        return realpath(self.path) == realpath(other.path)

    def close(self):
        """Perform operations which would close any possible process using this Dataset
        """
        repo = self._repo
        self._repo = None
        if repo:
            # might take care about lingering batched processes etc
            del repo

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

        # Note: lazy loading was disabled, since this is provided by the
        # flyweight pattern already and a possible invalidation of an existing
        # instance has to be done therein.
        # TODO: Still this is somewhat problematic. We can't invalidate strong
        # references

        with swallow_logs():
            for cls, ckw, kw in (
                    # TODO: Do we really want allow_noninitialized=True here?
                    # And if so, leave a proper comment!
                    (AnnexRepo, {'allow_noninitialized': True}, {'init': False}),
                    (GitRepo, {}, {})
            ):
                if cls.is_valid_repo(self._path, **ckw):
                    try:
                        lgr.debug("Detected %s at %s", cls, self._path)
                        self._repo = cls(self._path, create=False, **kw)
                        break
                    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
                        lgr.debug(
                            "Oops -- guess on repo type was wrong?: %s",
                            exc_str(exc))
                        pass
                    # version problems come as RuntimeError: DO NOT CATCH!
        if self._repo is None:
            # Often .repo is requested to 'sense' if anything is installed
            # under, and if so -- to proceed forward. Thus log here only
            # at DEBUG level and if necessary "complaint upstairs"
            lgr.debug("Failed to detect a valid repo at %s" % self.path)

        return self._repo

    @property
    def id(self):
        """Identifier of the dataset.

        This identifier is supposed to be unique across datasets, but identical
        for different versions of the same dataset (that have all been derived
        from the same original dataset repository).

        Returns
        -------
        str
          This is either a stored UUID, or `None`.
        """
        if self._id is None:
            # if we have one on record, stick to it!
            self.config.reload()
            self._id = self.config.get('datalad.dataset.id', None)
        return self._id

    @property
    def config(self):
        """Get an instance of the parser for the persistent dataset configuration.

        Returns
        -------
        ConfigManager
        """
        if self._cfg is None:
            if self.repo is None:
                # associate with this dataset and read the entire config hierarchy
                self._cfg = ConfigManager(dataset=self, dataset_only=False)
            else:
                self._cfg = self.repo.config
        return self._cfg

    def get_subdatasets(self, pattern=None, fulfilled=None, absolute=False,
                        recursive=False, recursion_limit=None, edges=False):
        # TODO wipe this function out completely once we are comfortable
        # with it. Internally we don't need or use it anymore.
        import inspect
        lgr.warning('%s still uses Dataset.get_subdatasets(). RF to use `subdatasets` command', inspect.stack()[1][3])
        from datalad.api import subdatasets
        if edges:
            return [(r['parentpath'] if absolute else relpath(r['parentpath'], start=self.path),
                     r['path'] if absolute else relpath(r['path'], start=self.path))
                    for r in subdatasets(
                        dataset=self,
                        fulfilled=fulfilled,
                        recursive=recursive,
                        recursion_limit=recursion_limit,
                        bottomup=True)]
        else:
            return subdatasets(
                dataset=self,
                fulfilled=fulfilled,
                recursive=recursive,
                recursion_limit=recursion_limit,
                bottomup=True,
                result_xfm='{}paths'.format('' if absolute else 'rel'))

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
        # do early check manually if path exists to not even ask git at all
        exists_now = exists(self.path)

        was_once_installed = None
        if exists_now:
            was_once_installed = self.path is not None and \
                                 self.repo is not None

        if not exists_now or \
                (was_once_installed and not exists(self.repo.repo.git_dir)):
            # repo gone now, reset
            self._repo = None
            return False
        else:
            return was_once_installed

    def get_superdataset(self, datalad_only=False, topmost=False):
        """Get the dataset's superdataset

        Parameters
        ----------
        datalad_only : bool, optional
          Either to consider only "datalad datasets" (with non-None
          id), or (if False, which is default) - any git repository
        topmost : bool, optional
          Return the topmost super-dataset. Might then be the current one.

        Returns
        -------
        Dataset or None
        """
        # TODO: return only if self is subdataset of the superdataset
        #       (meaning: registered as submodule)?
        path = self.path
        sds_path = path if topmost else None
        while path:
            # normalize the path after adding .. so we guaranteed to not
            # follow into original directory if path itself is a symlink
            par_path = normpath(opj(path, pardir))
            sds_path_ = get_dataset_root(par_path)
            if sds_path_ is None:
                # no more parents, use previous found
                break

            if datalad_only:
                # test if current git is actually a dataset?
                sds = Dataset(sds_path_)
                # can't use ATM since we just autogenerate and ID, see
                # https://github.com/datalad/datalad/issues/986
                # if not sds.id:
                if not sds.config.get('datalad.dataset.id', None):
                    break

            # That was a good candidate
            sds_path = sds_path_
            path = par_path
            if not topmost:
                # no looping
                break

        if sds_path is None:
            # None was found
            return None

        # No postprocessing now should be necessary since get_toppath
        # tries its best to not resolve symlinks now

        return Dataset(sds_path)

    # TODO this function is obselete and replaced by a faster
    # `subdatasets --contains` -- remove once `aggregate` is RF'ed to no
    # longer use it
    def get_containing_subdataset(self, path, recursion_limit=None):
        """Get the (sub-)dataset containing `path`

        Note: The "mount point" of a subdataset is classified as belonging to
        that respective subdataset.

        WARNING: This function is rather expensive, because it queries for all
        subdatasets recursively, and repeatedly -- which can take a substantial
        amount of time for datasets with many (sub-)subdatasets.  In Many cases
        the `subdatasets` command can be used with its `contains` parameter to
        achieve the desired result in a less expensive way.

        Parameters
        ----------
        path : str
          Path to determine the containing (sub-)dataset for
        recursion_limit: int or None
          limit the subdatasets to take into account to the given number of
          hierarchy levels

        Returns
        -------
        Dataset
        """

        if recursion_limit is not None and (recursion_limit < 1):
            lgr.warning("recursion limit < 1 (%s) always results in self.",
                        recursion_limit)
            return self

        if is_explicit_path(path):
            path = resolve_path(path, self)
            if not path.startswith(self.path):
                raise PathOutsideRepositoryError(file_=path, repo=self)
            path = relpath(path, self.path)

        candidates = []
        # TODO: this one would follow all the sub-datasets, which might
        # be inefficient if e.g. there is lots of other sub-datasets already
        # installed but under another sub-dataset.  There is a TODO 'pattern'
        # option which we could use I guess eventually
        for subds in self.subdatasets(recursive=True,
                                      #pattern=
                                      recursion_limit=recursion_limit,
                                      result_xfm='relpaths'):
            common = commonprefix((with_pathsep(subds), with_pathsep(path)))
            if common.endswith(sep) and common == with_pathsep(subds):
                candidates.append(common)
        if candidates:
            return Dataset(path=opj(self.path, max(candidates, key=len)))
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

    @wrapt.decorator
    def apply_func(wrapped, instance, args, kwargs):
        # Wrapper function to assign arguments of the bound function to
        # original function.
        #
        # Note
        # ----
        # This wrapper is NOT returned by the decorator, but only used to bind
        # the function `f` to the Dataset class.

        kwargs = kwargs.copy()
        from inspect import getargspec
        orig_pos = getargspec(f).args

        # If bound function is used with wrong signature (especially by
        # explicitly passing a dataset, let's raise a proper exception instead
        # of a 'list index out of range', that is not very telling to the user.
        if len(args) >= len(orig_pos):
            raise TypeError("{0}() takes at most {1} arguments ({2} given):"
                            " {3}".format(name, len(orig_pos), len(args),
                                          ['self'] + [a for a in orig_pos
                                                      if a != dataset_argname]))
        if dataset_argname in kwargs:
            raise TypeError("{}() got an unexpected keyword argument {}"
                            "".format(name, dataset_argname))
        kwargs[dataset_argname] = instance
        ds_index = orig_pos.index(dataset_argname)
        for i in range(0, len(args)):
            if i < ds_index:
                kwargs[orig_pos[i]] = args[i]
            elif i >= ds_index:
                kwargs[orig_pos[i+1]] = args[i]
        return f(**kwargs)

    setattr(Dataset, name, apply_func(f))
    return f


# Note: Cannot be defined within constraints.py, since then dataset.py needs to
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
    check_installed : bool, optional
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
        dspath = get_dataset_root(getpwd())
        if not dspath:
            raise NoDatasetArgumentFound("No dataset found")
        dataset = Dataset(dspath)

    assert(dataset is not None)
    lgr.debug("Resolved dataset{0}: {1}".format(
        ' for {}'.format(purpose) if purpose else '',
        dataset))

    if check_installed and not dataset.is_installed():
        raise ValueError("No installed dataset found at "
                         "{0}.".format(dataset.path))

    return dataset
