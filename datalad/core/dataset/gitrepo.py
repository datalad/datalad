# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Internal low-level interface to Git repositories

"""

import logging
from weakref import WeakValueDictionary

from datalad.config import (
    ConfigManager,
)
from datalad.core.dataset import (
    PathBasedFlyweight,
    RepoInterface,
    path_based_str_repr,
)
from datalad.utils import (
    Path,
)
from datalad.support.exceptions import (
    InvalidGitRepositoryError,
)

lgr = logging.getLogger('datalad.core.dataset.gitrepo')


@path_based_str_repr
class GitRepo(RepoInterface, metaclass=PathBasedFlyweight):
    """Representation of a git repository

    """
    # We must check git config to have name and email set, but
    # should do it once
    _config_checked = False

    # Begin Flyweight:

    _unique_instances = WeakValueDictionary()

    GIT_MIN_VERSION = "2.19.1"
    git_version = None

    def _flyweight_invalid(self):
        return not self.is_valid_git()

    @classmethod
    def _flyweight_reject(cls, id_, *args, **kwargs):
        # TODO:
        # This is a temporary approach. See PR # ...
        # create = kwargs.pop('create', None)
        # kwargs.pop('path', None)
        # if create and kwargs:
        #     # we have `create` plus options other than `path`
        #     return "Call to {0}() with args {1} and kwargs {2} conflicts " \
        #            "with existing instance {3}." \
        #            "This is likely to be caused by inconsistent logic in " \
        #            "your code." \
        #            "".format(cls, args, kwargs, cls._unique_instances[id_])
        pass

    # End Flyweight

    def __init__(self, path):
        """Creates representation of git repository at `path`.

        Parameters
        ----------
        path: str
          path to the git repository; In case it's not an absolute path,
          it's relative to PWD
        """
        self.path = path
        self.pathobj = Path(path)
        self._cfg = None

        # Note, that the following objects are used often and therefore are
        # stored for performance. Path object creation comes with a cost. Most
        # noteably, this is used for validity checking of the repository.
        self.dot_git = self._get_dot_git(self.pathobj, ok_missing=True)
        self._valid_git_test_path = self.dot_git / 'HEAD'

        # Could be used to e.g. disable automatic garbage and autopacking
        # ['-c', 'receive.autogc=0', '-c', 'gc.auto=0']
        self._GIT_COMMON_OPTIONS = []

    def __hash__(self):
        # the flyweight key is already determining unique instances
        # add the class name to distinguish from strings of a path
        return hash((self.__class__.__name__, self.__weakref__.key))

    def __del__(self):
        # unbind possibly bound ConfigManager, to prevent all kinds of weird
        # stalls etc
        self._cfg = None

    def __eq__(self, obj):
        """Decides whether or not two instances of this class are equal.

        This is done by comparing the base repository path.
        """
        return self.path == obj.path

    @property
    def config(self):
        """Get an instance of the parser for the persistent repository
        configuration.

        Note: This allows to also read/write .datalad/config,
        not just .git/config

        Returns
        -------
        ConfigManager
        """
        if self._cfg is None:
            # associate with this dataset and read the entire config hierarchy
            self._cfg = ConfigManager(dataset=self, source='any')
        return self._cfg

    @staticmethod
    def _get_dot_git(pathobj, *, ok_missing=False, maybe_relative=False):
        """Given a pathobj to a repository return path to .git/ directory

        Parameters
        ----------
        pathobj: Path
        ok_missing: bool, optional
          Allow for .git to be missing (useful while sensing before repo is initialized)
        maybe_relative: bool, optional
          Return path relative to pathobj

        Raises
        ------
        RuntimeError
          When ok_missing is False and .git path does not exist

        Returns
        -------
        Path
          Absolute (unless maybe_relative=True) path to resolved .git/ directory
        """
        dot_git = pathobj / '.git'
        if dot_git.is_file():
            with dot_git.open() as f:
                line = f.readline()
                if line.startswith("gitdir: "):
                    dot_git = pathobj / line[7:].strip()
                else:
                    raise InvalidGitRepositoryError("Invalid .git file")
        elif dot_git.is_symlink():
            dot_git = dot_git.resolve()
        elif not (ok_missing or dot_git.exists()):
            raise RuntimeError("Missing .git in %s." % pathobj)
        # Primarily a compat kludge for get_git_dir, remove when it is deprecated
        if maybe_relative:
            try:
                dot_git = dot_git.relative_to(pathobj)
            except ValueError:
                # is not a subpath, return as is
                lgr.debug("Path %r is not subpath of %r", dot_git, pathobj)
        return dot_git

    def is_valid_git(self):
        """Returns whether the underlying repository appears to be still valid

        Note, that this almost identical to the classmethod
        GitRepo.is_valid_repo().  However, if we are testing an existing
        instance, we can save Path object creations. Since this testing is done
        a lot, this is relevant.  Creation of the Path objects in

        Also note, that this method is bound to an instance but still
        class-dependent, meaning that a subclass cannot simply overwrite it.
        This is particularly important for the call from within __init__(),
        which in turn is called by the subclasses' __init__. Using an overwrite
        would lead to the wrong thing being called.
        """

        return self.dot_git.exists() and (
            not self.dot_git.is_dir() or self._valid_git_test_path.exists()
        )
