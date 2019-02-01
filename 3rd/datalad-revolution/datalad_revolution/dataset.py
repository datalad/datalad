"""Amendment of the DataLad `Dataset` base class"""
__docformat__ = 'restructuredtext'

import os
import os.path as op
from six import (
    PY2,
    text_type,
)
import wrapt
from weakref import WeakValueDictionary
import logging
from . import utils as ut

from datalad.distribution.dataset import (
    Dataset as _Dataset,
    require_dataset as _require_dataset,
    EnsureDataset as _EnsureDataset,
)
from datalad.dochelpers import exc_str
from datalad.support.gitrepo import (
    InvalidGitRepositoryError,
    NoSuchPathError,
)

from datalad.utils import (
    optional_args,
    getpwd,
)

from .gitrepo import RevolutionGitRepo
from .annexrepo import RevolutionAnnexRepo

lgr = logging.getLogger('datalad.revolution.dataset')


class RevolutionDataset(_Dataset):

    # Begin Flyweight:
    _unique_instances = WeakValueDictionary()
    # End Flyweight:

    @property
    def pathobj(self):
        """pathobj for the dataset"""
        # XXX this relies on the assumption that self._path as managed
        # by the base class is always a native path
        return ut.Path(self._path)

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

        for cls, ckw, kw in (
                # TODO: Do we really want to allow_noninitialized=True here?
                # And if so, leave a proper comment!
                (RevolutionAnnexRepo, {'allow_noninitialized': True}, {'init': False}),
                (RevolutionGitRepo, {}, {})
        ):
            if cls.is_valid_repo(self._path, **ckw):
                try:
                    lgr.log(5, "Detected %s at %s", cls, self._path)
                    self._repo = cls(self._path, create=False, **kw)
                    break
                except (InvalidGitRepositoryError, NoSuchPathError) as exc:
                    lgr.log(5,
                            "Oops -- guess on repo type was wrong?: %s",
                            exc_str(exc))
                    pass
                # version problems come as RuntimeError: DO NOT CATCH!
        if self._repo is None:
            # Often .repo is requested to 'sense' if anything is installed
            # under, and if so -- to proceed forward. Thus log here only
            # at DEBUG level and if necessary "complaint upstairs"
            lgr.log(5, "Failed to detect a valid repo at %s", self.path)

        return self._repo


# remove deprecated method from API
setattr(RevolutionDataset, 'get_subdatasets', ut.nothere)


@optional_args
def rev_datasetmethod(f, name=None, dataset_argname='dataset'):
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

    setattr(RevolutionDataset, name, apply_func(f))
    return f


# minimal wrapper to ensure a revolution dataset is coming out
class EnsureRevDataset(_EnsureDataset):
    def __call__(self, value):
        return RevolutionDataset(
            super(_EnsureDataset, self).__call__(value).path)


# minimal wrapper to ensure a revolution dataset is coming out
def require_rev_dataset(dataset, check_installed=True, purpose=None):
    return RevolutionDataset(_require_dataset(
        dataset,
        check_installed,
        purpose).path)

def rev_resolve_path(path, ds=None):
    """Resolve a path specification (against a Dataset location)

    Any explicit path (absolute or relative) is returned as an absolute path.
    In case of an explicit relative path (e.g. "./some", or ".\\some" on
    windows), the current working directory is used as reference. Any
    non-explicit relative path is resolved against as dataset location, i.e.
    considered relative to the location of the dataset. If no dataset is
    provided, the current working directory is used.

    Note however, that this function is not able to resolve arbitrarily
    obfuscated path specifications. All operations are purely lexical, and no
    actual path resolution against the filesystem content is performed.
    Consequently, common relative path arguments like '../something' (relative
    to PWD) can be handled properly, but things like 'down/../under' cannot, as
    resolving this path properly depends on the actual target of any
    (potential) symlink leading up to '..'.

    Parameters
    ----------
    path : str or PathLike
      Platform-specific path specific path specification.
    ds : Dataset or None
      Dataset instance to resolve non-explicit relative paths against.

    Returns
    -------
    `pathlib.Path` object
    """
    if ds is not None and not isinstance(ds, _Dataset):
        ds = require_rev_dataset(ds, check_installed=False, purpose='path resolution')
    if ds is None:
        # CWD is the reference
        path = ut.Path(path)
    # we have a dataset
    # stringify in case a pathobj came in
    elif not op.isabs(str(path)) and \
            not (str(path).startswith(os.curdir + os.sep) or
                 str(path).startswith(os.pardir + os.sep)):
        # we have a dataset and no abspath nor an explicit relative path ->
        # resolve it against the dataset
        path = ds.pathobj / path
    else:
        # CWD is the reference
        path = ut.Path(path)

    # make sure we return an absolute path, but without actually
    # resolving anything
    if not path.is_absolute():
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
        path_parts = path.parts
        leading_parents = 0
        for p in path.parts:
            if p == op.pardir:
                leading_parents += 1
                path_parts = path_parts[1:]
            elif p == op.curdir:
                # we want to discard that, but without stripping
                # a corresponding parent
                path_parts = path_parts[1:]
            else:
                break
        path = ut.Path(
            op.join(
                *(pwd_parts[:-leading_parents if leading_parents else None]
                  + path_parts)))
    # note that we will not "normpath()" the result, check the
    # pathlib docs for why this is the only sane choice in the
    # face of the possibility of symlinks in the path
    return path


def path_under_rev_dataset(ds, path):
    ds_path = ds.pathobj
    try:
        rpath = text_type(ut.Path(path).relative_to(ds_path))
        if not rpath.startswith(op.pardir):
            # path is already underneath the dataset
            return path
    except Exception:
        # whatever went wrong, we gotta play save
        pass

    root = rev_get_dataset_root(text_type(path))
    while root is not None and not ds_path.samefile(root):
        # path and therefore root could be relative paths,
        # hence in the next round we cannot use dirname()
        # to jump in the the next directory up, but we have
        # to use ./.. and get_dataset_root() will handle
        # the rest just fine
        root = rev_get_dataset_root(op.join(root, op.pardir))
    if root is None:
        return None
    return ds_path / op.relpath(text_type(path), root)


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


# this is here to make it easier for extensions that use this already
# TODO remove when merged into datalad-core, but keep in extension code
datasetmethod = rev_datasetmethod
require_dataset = require_rev_dataset
path_under_dataset = path_under_rev_dataset
resolve_path = rev_resolve_path
get_dataset_root = rev_get_dataset_root
EnsureDataset = EnsureRevDataset


