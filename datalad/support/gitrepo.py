# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to Git via GitPython

For further information on GitPython see http://gitpython.readthedocs.org/

"""

from os.path import join, exists
import logging

from git import Repo
from git.exc import GitCommandError

lgr = logging.getLogger('datalad.gitrepo')

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to log Exceptions from git commands.

class GitRepo(object):
    """Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have control.
    Convention: method's names starting with 'git_' to not be overridden accidentally by AnnexRepo.

    """

    def __init__(self, path, url=None):
        """Creates representation of git repository at `path`.

        If there is no git repository at this location, it will create an empty one.
        Additionally the directory is created if it doesn't exist.
        If url is given, a clone is created at `path`.

        Parameters
        ----------
        path: str
          path to the git repository
        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        """

        self.path = path

        if url is not None:
            try:
                Repo.clone_from(url, path)
                # TODO: more arguments possible: ObjectDB etc.
            except GitCommandError as e:
                # log here but let caller decide what to do
                lgr.error(str(e))
                raise

        if not exists(join(path, '.git')):
            try:
                self.repo = Repo.init(path, True)
            except GitCommandError as e:
                lgr.error(str(e))
                raise
        else:
            try:
                self.repo = Repo(path)
            except GitCommandError as e:
                # TODO: Creating Repo-object from existing git repository might raise other Exceptions
                lgr.error(str(e))
                raise

    def git_add(self, files=None):
        """Adds file(s) to the repository.

        Parameters:
        -----------
        files: list
            list of paths to get
        """

        if files:
            try:
                self.repo.index.add(files, write=True)
                # TODO: May be make use of 'fprogress'-option to indicate progress
                #
                # TODO: Is write=True a reasonable way to do it?
                # May be should not write until success of operation is confirmed?
                # What's best in case of a list of files?
            except OSError, e:
                lgr.error("git_add: %s" % e)
                raise

        else:
            lgr.warning("git_add was called with empty file list.")

    def git_commit(self, msg=None, options=None):
        """Commit changes to git.

        Parameters:
        -----------
        msg: str
            commit-message
        options:
            to be implemented. See TODO in AnnexRepo regarding a decorator for this purpose.
        """

        if not msg:
            msg = "What would be a good default message?"

        self.repo.index.commit(msg)