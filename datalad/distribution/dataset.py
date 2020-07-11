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
from os.path import (
    curdir,
    exists,
    join as opj,
    normpath,
    pardir,
)
import wrapt

from datalad.core.dataset.dataset import Dataset as CoreDataset
from datalad.support.constraints import Constraint
# DueCredit
from datalad.support.due_utils import duecredit_dataset
from datalad.support.exceptions import (
    NoDatasetFound,
)
from datalad.support import path as op

import datalad.utils as ut
from datalad.utils import (
    getpwd,
    optional_args,
    get_dataset_root,
    # TODO remove after a while, when external consumers have adjusted
    # to use get_dataset_root()
    get_dataset_root as rev_get_dataset_root,
    Path,
    PurePath,
    ensure_list,
    quote_cmdlinearg,
)


lgr = logging.getLogger('datalad.dataset')
lgr.log(5, "Importing dataset")


class Dataset(CoreDataset):
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
    @classmethod
    def _flyweight_preproc_path(cls, path):
        """Custom handling for few special abbreviations for datasets"""
        # special-case of '^' which needs the get_superdataset() method
        # which in turn needs the subdatasets() command, which is not
        # in core.
        if path == '^':
            # get the topmost dataset from current location. Note that 'zsh'
            # might have its ideas on what to do with ^, so better use as -d^
            path_ = Dataset(get_dataset_root(curdir)).get_superdataset(
                topmost=True).path
            if path != path_:
                lgr.debug("Resolved dataset alias %r to path %r", path, path_)
            return path_

        # everything else is handled by the base class
        return CoreDataset._flyweight_preproc_path(path)

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
        path = self.path
        sds_path = path if topmost else None

        def res_filter(res):
            return res.get('status') == 'ok' and res.get('type') == 'dataset'

        def subds_contains_path(ds, path):
            return path in sds.subdatasets(recursive=False,
                                           contains=path,
                                           result_filter=res_filter,
                                           on_failure='ignore',
                                           result_xfm='paths')

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
        dspath = get_dataset_root(getpwd())
        if not dspath:
            raise NoDatasetFound(
                "No dataset found at '{}'.  Specify a dataset to work with "
                "by providing its path via the `dataset` option, "
                "or change the current working directory to be in a "
                "dataset.".format(getpwd()))
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


def resolve_path(path, ds=None):
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
