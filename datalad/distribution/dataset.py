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
import os.path as op
from os.path import curdir
from os.path import exists
from os.path import join as opj
from os.path import normpath, isabs
from os.path import pardir
from os.path import realpath
from os.path import relpath
from weakref import WeakValueDictionary
from six import PY2
from six import string_types
from six import text_type
from six import add_metaclass
import wrapt

from datalad import cfg
from datalad.config import ConfigManager
from datalad.dochelpers import exc_str
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import Constraint
# DueCredit
from datalad.support.due import due
from datalad.support.due_utils import duecredit_dataset
from datalad.support.exceptions import NoDatasetArgumentFound
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import InvalidGitRepositoryError
from datalad.support.gitrepo import NoSuchPathError
from datalad.support.repo import Flyweight
from datalad.support.network import RI
from datalad.support.exceptions import InvalidAnnexRepositoryError

import datalad.utils as ut
from datalad.utils import getpwd
from datalad.utils import optional_args, expandpath, is_explicit_path
from datalad.utils import get_dataset_root
from datalad.utils import dlabspath
from datalad.utils import Path
from datalad.utils import PurePath
from datalad.utils import assure_list


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
    if is_explicit_path(path):
        # normalize path consistently between two (explicit and implicit) cases
        return dlabspath(path, norm=True)

    # no dataset given, use CWD as reference
    # note: abspath would disregard symlink in CWD
    top_path = getpwd() \
        if ds is None else ds.path if isinstance(ds, Dataset) else ds
    return normpath(opj(top_path, path))


class Dataset(object, metaclass=Flyweight):
    """Representation of a DataLad dataset/repository

    This is the core data type of DataLad: a representation of a dataset.
    At its core, datasets are (git-annex enabled) Git repositories. This
    class provides all operations that can be performed on a dataset.

    Creating a dataset instance is cheap, all actual operations are
    delayed until they are actually needed. Creating multiple `Dataset`
    class instances for the same Dataset location will automatically
    yield references to the same object.

    A dataset instance comprises of two major components: a `repo`
    attribute, and a `config` attribute. The former offers access to
    low-level functionality of the Git or git-annex repository. The
    latter gives access to a dataset's configuration manager.

    Most functionality is available via methods of this class, but also
    as stand-alone functions with the same name in `datalad.api`.
    """
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

        # mirror what is happening in __init__
        if isinstance(path, ut.PurePath):
            path = str(path)

        # Custom handling for few special abbreviations
        path_ = path
        if path == '^':
            # get the topmost dataset from current location. Note that 'zsh'
            # might have its ideas on what to do with ^, so better use as -d^
            path_ = Dataset(curdir).get_superdataset(topmost=True).path
        elif path == '///':
            # TODO: logic/UI on installing a default dataset could move here
            # from search?
            path_ = cfg.obtain('datalad.locations.default-dataset')
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

    def __hash__(self):
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    def __init__(self, path):
        """
        Parameters
        ----------
        path : str or Path
          Path to the dataset location. This location may or may not exist
          yet.
        """
        if isinstance(path, ut.PurePath):
            path = str(path)
        self._path = path
        self._repo = None
        self._id = None
        self._cfg = None
        self._cfg_bound = None

    @property
    def pathobj(self):
        """pathobj for the dataset"""
        # XXX this relies on the assumption that self._path as managed
        # by the base class is always a native path
        return ut.Path(self._path)

    def __repr__(self):
        return "<Dataset path=%s>" % self.path

    def __eq__(self, other):
        if not hasattr(other, 'path'):
            return False
        return realpath(self.path) == realpath(other.path)

    def __getattr__(self, attr):
        # Assure that we are not just missing some late binding
        # @datasetmethod . We will use interface definitions.
        # The gotcha could be the mismatch between explicit name
        # provided to @datasetmethod and what is defined in interfaces
        meth = None
        if not attr.startswith('_'):  # do not even consider those
            from datalad.interface.base import (
                get_interface_groups, get_api_name, load_interface
            )
            groups = get_interface_groups(True)
            for group, _, interfaces in groups:
                for intfspec in interfaces:
                    # lgr.log(5, "Considering interface %s", intfspec)
                    name = get_api_name(intfspec)
                    if attr == name:
                        meth_ = load_interface(intfspec)
                        if meth_:
                            lgr.debug("Found matching interface %s for %s",
                                      intfspec, name)
                            if meth:
                                lgr.debug(
                                    "New match %s possibly overloaded previous one %s",
                                    meth_, meth
                                )
                            meth = meth_
            if not meth:
                lgr.debug("Found no match among known interfaces for %r", attr)
        return super(Dataset, self).__getattribute__(attr)

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
        or None if there is none yet (or none anymore).

        If testing the validity of an instance of GitRepo is guaranteed to be
        really cheap this could also serve as a test whether a repo is present.

        Note, that this property is evaluated every time it is used. If used
        multiple times within a function it's probably a good idea to store its
        value in a local variable and use this variable instead.

        Returns
        -------
        GitRepo or AnnexRepo
        """

        # If we already got a *Repo instance, check whether it's still valid;
        # Note, that this basically does part of the testing that would
        # (implicitly) be done in the loop below again. So, there's still
        # potential to speed up when we actually need to get a new instance
        # (or none). But it's still faster for the vast majority of cases.
        #
        # TODO: Dig deeper into it and melt with new instance guessing. This
        # should also involve to reduce redundancy of testing such things from
        # within Flyweight.__call__, AnnexRepo.__init__ and GitRepo.__init__!
        #
        # Also note, that this could be forged into a single big condition, but
        # that is hard to read and we should be well aware of the actual
        # criteria here:
        if self._repo is not None and realpath(self.path) == self._repo.path:
            # we got a repo and path references still match
            if isinstance(self._repo, AnnexRepo):
                # it's supposed to be an annex
                if self._repo is AnnexRepo._unique_instances.get(
                        self._repo.path, None) and \
                        AnnexRepo.is_valid_repo(self._repo.path,
                                                allow_noninitialized=True):
                    # it's still the object registered as flyweight and it's a
                    # valid annex repo
                    return self._repo
            elif isinstance(self._repo, GitRepo):
                # it's supposed to be a plain git
                if self._repo is GitRepo._unique_instances.get(
                        self._repo.path, None) and \
                        GitRepo.is_valid_repo(self._repo.path) and not \
                        self._repo.is_with_annex():
                    # it's still the object registered as flyweight, it's a
                    # valid git repo and it hasn't turned into an annex
                    return self._repo

        # Note: Although it looks like the "self._repo = None" assignments
        # could be used instead of variable "valid", that's a big difference!
        # The *Repo instances are flyweights, not singletons. self._repo might
        # be the last reference, which would lead to those objects being
        # destroyed and therefore the constructor call would result in an
        # actually new instance. This is unnecessarily costly.
        valid = False
        for cls, ckw, kw in (
                # TODO: Do we really want to allow_noninitialized=True here?
                # And if so, leave a proper comment!
                (AnnexRepo, {'allow_noninitialized': True}, {'init': False}),
                (GitRepo, {}, {})
        ):
            if cls.is_valid_repo(self._path, **ckw):
                try:
                    lgr.log(5, "Detected %s at %s", cls, self._path)
                    self._repo = cls(self._path, create=False, **kw)
                    valid = True
                    break
                except (InvalidGitRepositoryError, NoSuchPathError,
                        InvalidAnnexRepositoryError) as exc:
                    lgr.log(5,
                            "Oops -- guess on repo type was wrong?: %s",
                            exc_str(exc))

        if not valid:
            self._repo = None

        if self._repo is None:
            # Often .repo is requested to 'sense' if anything is installed
            # under, and if so -- to proceed forward. Thus log here only
            # at DEBUG level and if necessary "complaint upstairs"
            lgr.log(5, "Failed to detect a valid repo at %s", self.path)
        elif due.active:
            # Makes sense only on installed dataset - @never_fail'ed
            duecredit_dataset(self)

        return self._repo

    @property
    def id(self):
        """Identifier of the dataset.

        This identifier is supposed to be unique across datasets, but identical
        for different versions of the same dataset (that have all been derived
        from the same original dataset repository).

        Note, that a plain git/git-annex repository doesn't necessarily have
        a dataset id yet. It is created by `Dataset.create()` and stored in
        .datalad/config. If None is returned while there is a valid repository,
        there may have never been a call to `create` in this branch before
        current commit.

        Note, that this property is evaluated every time it is used. If used
        multiple times within a function it's probably a good idea to store its
        value in a local variable and use this variable instead.

        Returns
        -------
        str
          This is either a stored UUID, or `None`.
        """

        return self.config.get('datalad.dataset.id', None)

    @property
    def config(self):
        """Get an instance of the parser for the persistent dataset configuration.

        Note, that this property is evaluated every time it is used. If used
        multiple times within a function it's probably a good idea to store its
        value in a local variable and use this variable instead.

        Returns
        -------
        ConfigManager
        """

        if self.repo is None:
            # if there's no repo (yet or anymore), we can't read/write config at
            # dataset level, but only at user/system level
            # However, if this was the case before as well, we don't want a new
            # instance of ConfigManager
            if self._cfg_bound in (True, None):
                self._cfg = ConfigManager(dataset=None, dataset_only=False)
                self._cfg_bound = False

        else:
            self._cfg = self.repo.config
            self._cfg_bound = True

        return self._cfg

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

        return self.path is not None and exists(self.path) and \
            self.repo is not None

    def get_superdataset(self, datalad_only=False, topmost=False,
                         registered_only=True):
        """Get the dataset's superdataset

        Parameters
        ----------
        datalad_only : bool, optional
          Whether to consider only "datalad datasets" (with non-None
          id), or (if False, which is default) - any git repository
        topmost : bool, optional
          Return the topmost super-dataset. Might then be the current one.
        registered_only : bool, optional
          Test whether any discovered superdataset actually contains the
          dataset in question as a registered subdataset (as opposed to
          just being located in a subdirectory without a formal relationship).

        Returns
        -------
        Dataset or None
        """
        from datalad.coreapi import subdatasets
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

            sds = Dataset(sds_path_)
            if datalad_only:
                # test if current git is actually a dataset?
                if not sds.id:
                    break
            if registered_only:
                if path not in sds.subdatasets(
                        recursive=False,
                        contains=path,
                        result_xfm='paths'):
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
        name = f.__name__

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
        from datalad.utils import getargspec
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
    """Despite its name, this constraint does not actually ensure that the
    argument is a valid dataset, because for procedural reasons this would
    typically duplicate subsequent checks and processing. However, it can
    be used to achieve uniform documentation of `dataset` arguments."""

    def __call__(self, value):
        if isinstance(value, Dataset):
            return value
        elif isinstance(value, str):
            # we cannot convert to a Dataset class right here
            # - duplicates require_dataset() later on
            # - we need to be able to distinguish between a bound
            #   dataset method call and a standalone call for
            #   relative path argument disambiguation
            #return Dataset(path=value)
            return value
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
        # assure_unicode() can be dropped once we drop PY2.
        dspath = assure_unicode(get_dataset_root(getpwd()))
        if not dspath:
            raise NoDatasetArgumentFound("No dataset found")
        dataset = Dataset(dspath)

    assert(dataset is not None)
    lgr.debug(u"Resolved dataset%s: %s",
              u' for {}'.format(purpose) if purpose else '',
              dataset.path)

    if check_installed and not dataset.is_installed():
        raise ValueError(u"No installed dataset found at "
                         u"{0}.".format(dataset.path))

    return dataset


# New helpers, courtesy of datalad-revolution.


def rev_resolve_path(path, ds=None):
    """Resolve a path specification (against a Dataset location)

    Any path is returned as an absolute path. If, and only if, a dataset
    object instance is given as `ds`, relative paths are interpreted as
    relative to the given dataset. In all other cases, relative paths are
    treated as relative to the current working directory.

    Note however, that this function is not able to resolve arbitrarily
    obfuscated path specifications. All operations are purely lexical, and no
    actual path resolution against the filesystem content is performed.
    Consequently, common relative path arguments like '../something' (relative
    to PWD) can be handled properly, but things like 'down/../under' cannot, as
    resolving this path properly depends on the actual target of any
    (potential) symlink leading up to '..'.

    Parameters
    ----------
    path : str or PathLike or list
      Platform-specific path specific path specification. Multiple path
      specifications can be given as a list
    ds : Dataset or None
      Dataset instance to resolve relative paths against.

    Returns
    -------
    `pathlib.Path` object or list(Path)
      When a list was given as input a list is returned, a Path instance
      otherwise.
    """
    got_ds_instance = isinstance(ds, Dataset)
    if ds is not None and not got_ds_instance:
        ds = require_dataset(
            ds, check_installed=False, purpose='path resolution')
    out = []
    for p in assure_list(path):
        if ds is None or not got_ds_instance:
            # no dataset at all or no instance provided -> CWD is always the reference
            # nothing needs to be done here. Path-conversion and absolutification
            # are done next
            pass
        # we have a given datasets instance
        elif not Path(p).is_absolute():
            # we have a dataset and no abspath nor an explicit relative path ->
            # resolve it against the dataset
            p = ds.pathobj / p

        p = ut.Path(p)

        # make sure we return an absolute path, but without actually
        # resolving anything
        if not p.is_absolute():
            # in general it is almost impossible to use resolve() when
            # we can have symlinks in the root path of a dataset
            # (that we don't want to resolve here), symlinks to annex'ed
            # files (that we never want to resolve), and other within-repo
            # symlinks that we (sometimes) want to resolve (i.e. symlinked
            # paths for addressing content vs adding content)
            # CONCEPT: do the minimal thing to catch most real-world inputs
            # ASSUMPTION: the only sane relative path input that needs
            # handling and can be handled are upward references like
            # '../../some/that', wherease stuff like 'down/../someotherdown'
            # are intellectual excercises
            # ALGORITHM: match any number of leading '..' path components
            # and shorten the PWD by that number
            # NOT using ut.Path.cwd(), because it has symlinks resolved!!
            pwd_parts = ut.Path(getpwd()).parts
            path_parts = p.parts
            leading_parents = 0
            for pp in p.parts:
                if pp == op.pardir:
                    leading_parents += 1
                    path_parts = path_parts[1:]
                elif pp == op.curdir:
                    # we want to discard that, but without stripping
                    # a corresponding parent
                    path_parts = path_parts[1:]
                else:
                    break
            p = ut.Path(
                op.join(
                    *(pwd_parts[:-leading_parents if leading_parents else None]
                      + path_parts)))
        # note that we will not "normpath()" the result, check the
        # pathlib docs for why this is the only sane choice in the
        # face of the possibility of symlinks in the path
        out.append(p)
    return out[0] if isinstance(path, (str, PurePath)) else out


def path_under_rev_dataset(ds, path):
    ds_path = ds.pathobj
    try:
        rpath = str(ut.Path(path).relative_to(ds_path))
        if not rpath.startswith(op.pardir):
            # path is already underneath the dataset
            return path
    except Exception:
        # whatever went wrong, we gotta play save
        pass

    root = rev_get_dataset_root(str(path))
    while root is not None and not ds_path.samefile(root):
        # path and therefore root could be relative paths,
        # hence in the next round we cannot use dirname()
        # to jump in the the next directory up, but we have
        # to use ./.. and get_dataset_root() will handle
        # the rest just fine
        root = rev_get_dataset_root(op.join(root, op.pardir))
    if root is None:
        return None
    return ds_path / op.relpath(str(path), root)


# XXX this is a copy of the change proposed in
# https://github.com/datalad/datalad/pull/2944
def rev_get_dataset_root(path):
    """Return the root of an existent dataset containing a given path

    The root path is returned in the same absolute or relative form
    as the input argument. If no associated dataset exists, or the
    input path doesn't exist, None is returned.

    If `path` is a symlink or something other than a directory, its
    the root dataset containing its parent directory will be reported.
    If none can be found, at a symlink at `path` is pointing to a
    dataset, `path` itself will be reported as the root.
    """
    suffix = '.git'
    altered = None
    if op.islink(path) or not op.isdir(path):
        altered = path
        path = op.dirname(path)
    apath = op.abspath(path)
    # while we can still go up
    while op.split(apath)[1]:
        if op.exists(op.join(path, suffix)):
            return path
        # new test path in the format we got it
        path = op.normpath(op.join(path, os.pardir))
        # no luck, next round
        apath = op.abspath(path)
    # if we applied dirname() at the top, we give it another go with
    # the actual path, if it was itself a symlink, it could be the
    # top-level dataset itself
    if altered and op.exists(op.join(altered, suffix)):
        return altered

    return None


lgr.log(5, "Done importing dataset")
