# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Implements class DataSet
"""

import logging
from os.path import exists
from six import string_types

from datalad.support.gitrepo import GitRepo, InvalidGitRepositoryError
from datalad.support.constraints import EnsureStr, EnsureNone, \
    EnsureHandleAbsolutePath, Constraint
from datalad.utils import optional_args


lgr = logging.getLogger('datalad.dataset')


class DataSet(object):

    def __init__(self, path=None, source=None):
        self._path = (EnsureHandleAbsolutePath() | EnsureNone())(path)
        self._src = (EnsureStr() | EnsureNone())(source)

    def get_path(self):
        """Query the path to the location of a dataset in the filesystem.
        If there is nothing in the filesystem (yet), None is returned.
        """
        # TODO: Do we care for whether or not there is a vcs already?
        return self._path if exists(self._path) else None

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

        Returns
        -------

        """

        raise NotImplementedError("TODO")

    def get_dataset_handles(self, pattern=None, fulfilled=None):
        """Get paths to all known dataset_handles (subdatasets),
        optionally matching a specific name pattern.

        If fulfilled is True, only paths to fullfiled handles are returned,
        if False, only paths to unfulfilled handles are returned.


        Parameters
        ----------
        pattern
        fulfilled

        Returns
        -------
        list of str
          (paths)
        """
        raise NotImplementedError("TODO")

    def get_file_handles(self, pattern=None, fulfilled=None):
        """Get paths to all known file_handles, optionally matching a specific
        name pattern.

        If fulfilled is True, only paths to fullfiled handles are returned,
        if False, only paths to unfulfilled handles are returned.

        Parameters
        ----------
        pattern: str
        fulfilled: bool

        Returns
        -------
        list of str
          (paths)
        """
        raise NotImplementedError("TODO")

    def record_state(self, auto_add_changes=True, message=str,
                     update_superdataset=False, version=None):
        """

        Parameters
        ----------
        auto_add_changes: bool
        message: str
        update_superdataset: bool
        version: str
        """
        raise NotImplementedError("TODO")

    def set_state(self, whereto):
        """Something that can be used to checkout a particular state
        (tag, commit) to "undo" a change or switch to a otherwise desired
        previous state.

        Parameters
        ----------
        whereto: str
        """
        raise NotImplementedError("TODO")

    def get_vcs(self):
        """Get an instance of the version control system/repo for this dataset,
        or None if there is none yet.

        If creating an instance of GitRepo is guaranteed to be really cheap
        this could also serve as a test whether a repo is present.

        Returns
        -------
        GitRepo
        """
        if self._vcs is None:
            try:
                self._vcs = GitRepo(self._path, create=False)
            except InvalidGitRepositoryError:
                return None

        return self._vcs

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
        if self.get_path() is not None and self.get_vcs() is not None:
            return True
        else:
            return False


@optional_args
def datasetmethod(f, name=None):
    """Decorator to bind functions to DataSet class.
    """
    if not name:
        name = f.func_name
    setattr(DataSet, name, f)
    return f


# Note: Cannot be defined with constraints.py, since then dataset.py needs to
# be imported from constraints.py, which needs to be imported from dataset.py
# for another constraint
class EnsureDataSet(Constraint):

    def __init__(self):
        self._name_resolver = EnsureHandleAbsolutePath()

    def __call__(self, value):
        if isinstance(value, DataSet):
            return value
        elif isinstance(value, string_types):
            return DataSet(path=self._name_resolver(value))
        else:
            raise ValueError("Can't create DataSet from %s." % type(value))

    # TODO: Proper description
    def short_description(self):
        pass

    def long_description(self):
        return "Some handle creation description"

