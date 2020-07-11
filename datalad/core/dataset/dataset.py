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
)
from weakref import WeakValueDictionary

from datalad import cfg
from datalad.config import ConfigManager
from datalad.core.dataset.utils import repo_from_path
from datalad.core.dataset.annexrepo import AnnexRepo
from datalad.core.dataset import (
    path_based_str_repr,
    PathBasedFlyweight,
)
from datalad.core.dataset.gitrepo import GitRepo
from datalad.support import path as op

from datalad.utils import (
    get_dataset_root,
    Path,
    PurePath,
)

lgr = logging.getLogger('datalad.core.dataset.dataset')


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
        if path == '^':
            # get the topmost dataset from current location. Note that 'zsh'
            # might have its ideas on what to do with ^, so better use as -d^
            path_ = Dataset(get_dataset_root(curdir)).get_superdataset(
                topmost=True).path
        elif path == '^.':
            # get the dataset containing current directory
            path_ = get_dataset_root(curdir)
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
        self._pathobj = path if isinstance(path, Path) else None
        if isinstance(path, PurePath):
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
            self._pathobj = Path(self._path)
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

        return self._repo

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
                self._cfg = ConfigManager(dataset=None, dataset_only=False)
                self._cfg_bound = False

        else:
            self._cfg = repo.config
            self._cfg_bound = True

        return self._cfg
