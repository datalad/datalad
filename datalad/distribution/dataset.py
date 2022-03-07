# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements class Dataset
"""

import inspect
import logging
from functools import wraps
from os.path import (
    curdir,
    exists,
    join as opj,
    normpath,
    pardir,
)
from weakref import WeakValueDictionary

from datalad import cfg
from datalad.config import ConfigManager
from datalad.core.local.repo import repo_from_path
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import Constraint
# DueCredit
from datalad.support.due import due
from datalad.support.due_utils import duecredit_dataset
from datalad.support.exceptions import (
    NoDatasetFound,
)
from datalad.dataset.repo import (
    path_based_str_repr,
    PathBasedFlyweight,
)
from datalad.support.gitrepo import (
    GitRepo,
)
from datalad.support import path as op

import datalad.utils as ut
from datalad.utils import (
    getpwd,
    optional_args,
    get_dataset_root,
    get_sig_param_names,
    # TODO remove after a while, when external consumers have adjusted
    # to use get_dataset_root()
    get_dataset_root as rev_get_dataset_root,
    Path,
    PurePath,
    ensure_list,
)


lgr = logging.getLogger('datalad.dataset')
lgr.log(5, "Importing dataset")


@path_based_str_repr
class Dataset(object, metaclass=PathBasedFlyweight):
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
    def _flyweight_preproc_path(cls, path):
        """Custom handling for few special abbreviations for datasets"""
        path_ = path
        if path in ('^', '^.'):
            dsroot = get_dataset_root(curdir)
            if dsroot is None:
                raise NoDatasetFound('No dataset contains path: {}'.format(
                    str(Path.cwd())))
            if path == '^':
                # get the topmost dataset from current location. Note that 'zsh'
                # might have its ideas on what to do with ^, so better use as -d^
                path_ = Dataset(dsroot).get_superdataset(
                    topmost=True).path
            elif path == '^.':
                # the dataset containing current directory
                path_ = dsroot
        elif path == '///':
            # TODO: logic/UI on installing a default dataset could move here
            # from search?
            path_ = cfg.obtain('datalad.locations.default-dataset')
        if path != path_:
            lgr.debug("Resolved dataset alias %r to path %r", path, path_)
        return path_

    @classmethod
    def _flyweight_postproc_path(cls, path):
        # we want an absolute path, but no resolved symlinks
        if not op.isabs(path):
            path = op.join(op.getpwd(), path)

        # use canonical paths only:
        return op.normpath(path)

    def _flyweight_invalid(self):
        """Invalidation of Flyweight instance

        Dataset doesn't need to be invalidated during its lifetime at all. Instead the underlying *Repo instances are.
        Dataset itself can represent a not yet existing path.
        """
        return False
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
        self._pathobj = path if isinstance(path, ut.Path) else None
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
        if not self._pathobj:
            self._pathobj = ut.Path(self._path)
        return self._pathobj

    def __eq__(self, other):
        if not hasattr(other, 'pathobj'):
            return False
        # Ben: https://github.com/datalad/datalad/pull/4057#discussion_r370153586
        # It's pointing to the same thing, while not being the same object
        # (in opposition to the *Repo classes). So `ds1 == ds2`,
        # `but ds1 is not ds2.` I thought that's a useful distinction. On the
        # other hand, I don't think we use it anywhere outside tests yet.
        me_exists = self.pathobj.exists()
        other_exists = other.pathobj.exists()
        if me_exists != other_exists:
            # no chance this could be the same
            return False
        elif me_exists:
            # check on filesystem
            return self.pathobj.samefile(other.pathobj)
        else:
            # we can only do lexical comparison.
            # this will fail to compare a long and a shortpath.
            # on windows that could actually point to the same thing
            # if it would exists, but this is how far we go with this.
            return self.pathobj == other.pathobj

    def __getattr__(self, attr):
        # Assure that we are not just missing some late binding @datasetmethod .
        if not attr.startswith('_'):  # do not even consider those
            lgr.debug("Importing datalad.api to possibly discover possibly not yet bound method %r", attr)
            # load entire datalad.api which will also bind datasetmethods
            # from extensions.
            import datalad.api
            # which would bind all known interfaces as well.
            # Although adds overhead, good for UX
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
        if self._repo is not None and self.pathobj.resolve() == self._repo.pathobj:
            # we got a repo and path references still match
            if isinstance(self._repo, AnnexRepo):
                # it's supposed to be an annex
                # Here we do the same validation that Flyweight would do beforehand if there was a call to AnnexRepo()
                if self._repo is AnnexRepo._unique_instances.get(
                        self._repo.path, None) and not self._repo._flyweight_invalid():
                    # it's still the object registered as flyweight and it's a
                    # valid annex repo
                    return self._repo
            elif isinstance(self._repo, GitRepo):
                # it's supposed to be a plain git
                # same kind of checks as for AnnexRepo above, but additionally check whether it was changed to have an
                # annex now.
                # TODO: Instead of is_with_annex, we might want the cheaper check for an actually initialized annex.
                #       However, that's not completely clear. On the one hand, if it really changed to be an annex
                #       it seems likely that this happened locally and it would also be an initialized annex. On the
                #       other hand, we could have added (and fetched) a remote with an annex, which would turn it into
                #       our current notion of an uninitialized annex. Question is whether or not such a change really
                #       need to be detected. For now stay on the safe side and detect it.
                if self._repo is GitRepo._unique_instances.get(
                        self._repo.path, None) and not self._repo._flyweight_invalid() and not \
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
        try:
            self._repo = repo_from_path(self._path)
        except ValueError:
            lgr.log(5, "Failed to detect a valid repo at %s", self.path)
            self._repo = None
            return

        if due.active:
            # TODO: Figure out, when exactly this is needed. Don't think it
            #       makes sense to do this for every dataset,
            #       no matter what => we want .repo to be as cheap as it gets.
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
        # OPT: be "smart" and avoid re-resolving .repo -- expensive in DataLad
        repo = self.repo
        if repo is None:
            # if there's no repo (yet or anymore), we can't read/write config at
            # dataset level, but only at user/system level
            # However, if this was the case before as well, we don't want a new
            # instance of ConfigManager
            if self._cfg_bound in (True, None):
                self._cfg = ConfigManager(dataset=None)
                self._cfg_bound = False

        else:
            self._cfg = repo.config
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
        path = self.path
        sds_path = path if topmost else None

        def res_filter(res):
            return res.get('status') == 'ok' and res.get('type') == 'dataset'

        def subds_contains_path(ds, path):
            return path in sds.subdatasets(recursive=False,
                                           contains=path,
                                           result_filter=res_filter,
                                           on_failure='ignore',
                                           result_xfm='paths',
                                           result_renderer='disabled')

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
                if not subds_contains_path(sds, path):
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

    @wraps(f)
    def apply_func(instance, *args, **kwargs):
        # Wrapper function to assign arguments of the bound function to
        # original function.
        #
        # Note
        # ----
        # This wrapper is NOT returned by the decorator, but only used to bind
        # the function `f` to the Dataset class.
        kwargs = kwargs.copy()

        # due to use of functools.wraps and inability of of getarspec to get
        # those, we use .signature.
        # More information in de-wrapt PR https://github.com/datalad/datalad/pull/6190
        from datalad.utils import get_sig_param_names
        f_args, f_kwonlyargs = get_sig_param_names(f, ('pos_any', 'kw_only'))

        # If bound function is used with wrong signature (especially by
        # explicitly passing a dataset), let's raise a proper exception instead
        # of a 'list index out of range', that is not very telling to the user.
        # In case whenever kwonlyargs are used, 'dataset' would not be listed
        # among args, so we would account for it (possibly) be there.
        if len(args) >= len(f_args) + int(bool(f_kwonlyargs)):
            non_dataset_args = ["self"] + [a for a in f_args if a != dataset_argname]
            raise TypeError(
                f"{name}() takes at most {len(f_args)} arguments ({len(args)} given): "
                f"{non_dataset_args}")
        if dataset_argname in kwargs:
            raise TypeError(
                f"{name}() got an unexpected keyword argument {dataset_argname}")
        kwargs[dataset_argname] = instance
        if dataset_argname in f_kwonlyargs:
            # * was used to enforce kwargs, so we just would pass things as is
            pass
        else:
            # so it is "old" style, where it is a regular kwargs - we pass everything
            # via kwargs
            # TODO: issue a DX oriented warning that we advise to separate out kwargs,
            # dataset included, with * from positional args?
            ds_index = f_args.index(dataset_argname)
            for i in range(0, len(args)):
                if i < ds_index:
                    kwargs[f_args[i]] = args[i]
                elif i >= ds_index:
                    kwargs[f_args[i+1]] = args[i]
            args = []
        return f(*args, **kwargs)

    setattr(Dataset, name, apply_func)
    # set the ad-hoc attribute so that @build_doc could also bind built doc
    # to the dataset method
    if getattr(f, '_dataset_method', None):
        raise RuntimeError(f"_dataset_method of {f} is already set to {f._dataset_method}")
    setattr(f, '_dataset_method', apply_func)
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
      If a dataset could be determined.

    Raises
    ------
    NoDatasetFound
      If not dataset could be determined.
    """
    if dataset is not None and not isinstance(dataset, Dataset):
        dataset = Dataset(dataset)

    if dataset is None:  # possible scenario of cmdline calls
        dspath = get_dataset_root(getpwd())
        if not dspath:
            raise NoDatasetFound(
                "No dataset found at '{}'{}.  Specify a dataset to work with "
                "by providing its path via the `dataset` option, "
                "or change the current working directory to be in a "
                "dataset.".format(
                    getpwd(),
                    " for the purpose {!r}".format(purpose) if purpose else ''
                )
            )
        dataset = Dataset(dspath)

    assert(dataset is not None)
    lgr.debug(u"Resolved dataset%s: %s",
              u' to {}'.format(purpose) if purpose else '',
              dataset.path)

    if check_installed and not dataset.is_installed():
        raise NoDatasetFound(
            f"No installed dataset found at {dataset.path}")

    return dataset


# New helpers, courtesy of datalad-revolution.


# note: not thread safe if threads chdir - uses getpwd
def resolve_path(path, ds=None, ds_resolved=None):
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
    ds : Dataset or PathLike or None
      Dataset instance to resolve relative paths against.
    ds_resolved : Dataset or None
      A dataset instance that was created from `ds` outside can be provided
      to avoid multiple instantiation on repeated calls.

    Returns
    -------
    `pathlib.Path` object or list(Path)
      When a list was given as input a list is returned, a Path instance
      otherwise.
    """
    got_ds_instance = isinstance(ds, Dataset)
    if ds is not None and not got_ds_instance:
        ds = ds_resolved or require_dataset(
            ds, check_installed=False, purpose='path resolution')
    out = []
    pwd_parts = None  # get it upon first use but only once
    for p in ensure_list(path):
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
            # '../../some/that', whereas stuff like 'down/../someotherdown'
            # are intellectual exercises
            # ALGORITHM: match any number of leading '..' path components
            # and shorten the PWD by that number
            # NOT using ut.Path.cwd(), because it has symlinks resolved!!
            if not pwd_parts:
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

# TODO keep this around for a while so that extensions can be updated
rev_resolve_path = resolve_path


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

    root = get_dataset_root(str(path))
    while root is not None and not ds_path.samefile(root):
        # path and therefore root could be relative paths,
        # hence in the next round we cannot use dirname()
        # to jump in the the next directory up, but we have
        # to use ./.. and get_dataset_root() will handle
        # the rest just fine
        root = get_dataset_root(op.join(root, op.pardir))
    if root is None:
        return None
    return ds_path / op.relpath(str(path), root)


lgr.log(5, "Done importing dataset")
