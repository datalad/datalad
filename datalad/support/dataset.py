# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""
This layer makes the difference between an arbitrary annex and a datalad-managed dataset.

"""

import os
from os.path import join, exists
import logging

from annexrepo import AnnexRepo

lgr = logging.getLogger('datalad.dataset')


class Dataset(AnnexRepo):
    """Representation of a dataset handled by datalad.

    Implementations of datalad commands are supposed to use this rather than AnnexRepo or GitRepo directly,
    since any restrictions on annexes required by datalad due to its cross-platform distribution approach are handled
    within this class. Also an AnnexRepo has no idea of any datalad configuration needs, of course.

    """

    def __init__(self, path, url=None, direct=False):
        """Creates a dataset representation from path.

        If `path` is empty, it creates an new repository.
        If `url` is given, it is expected to point to a git repository to create a clone from.

        Parameters
        ----------
        path : str
          path to repository
        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.
        direct: bool
          if True, force git-annex to operate in direct mode

        """

        super(Dataset, self).__init__(path, url, direct=direct)
        # TODO: what about runner? (dry runs ...)

        # TODO: should work with path (deeper) inside repo! => gitrepo/annexrepo

        dataladPath = join(self.path, '.datalad')
        if not exists(dataladPath):
            os.mkdir(dataladPath)

    def get(self, list):
        """get the actual content of files

        This command gets the actual content of the files in `list`.
        """
        super(Dataset, self).annex_get(list)
        # For now just pass
        # TODO:

    def _commit(self, msg):
        """Commit changes to repository

        Parameters:
        -----------
        msg: str
            commit-message
        """

        if self.is_direct_mode():
            self.annex_proxy('git commit -m "%s"' % msg)
        else:
            self.git_commit(msg)

    def add_to_annex(self, files, commit_msg="Added file(s) to annex."):
        """Add file(s) to the annex


        Parameters
        ----------
        files: list
            list of paths to add to the annex
        """

        self.annex_add(files)
        self._commit(commit_msg)

    def add_to_git(self, files, commit_msg="Added file(s) to git."):
        """Add file(s) to git


        Parameters
        ----------
        files: list
            list of paths to add to git
        """
        # TODO: See issue #97!


        # TODO: Rethink, whether or not the whole direct mode dependent handling should go into AnnexRepo anyway.
        # But remember: committing after adding should be done here, so the methods are needed either way.

        if self.is_direct_mode():
            # Since files is a list of paths, we have to care for escaping special characters, etc.
            # at this point. For now just quote all of them (at least this should handle spaces):
            filelist = '"' + '" "'.join(files) + '"'
            # TODO: May be this should go in a decorator for use in every command.

            self.annex_proxy('git add %s' % filelist)
        else:
            self.git_add(files)

        self._commit(commit_msg)