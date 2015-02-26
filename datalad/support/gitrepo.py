# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
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

from git import Repo
from git.exc import GitCommandError

import datalad.log

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
                datalad.log.lgr.error(str(e))
                raise

        if not exists(join(path, '.git')):
            try:
                self.repo = Repo.init(path, True)
            except GitCommandError as e:
                datalad.log.lgr.error(str(e))
                raise
        else:
            try:
                self.repo = Repo(path)
            except GitCommandError as e:
                # TODO: Creating Repo-object from existing git repository might raise other Exceptions
                datalad.log.lgr.error(str(e))
                raise

    def git_dummy_command(self):
        """Just a dummy

        No params, nothing to explain, should raise NotImplementedError.

        """
        raise NotImplementedError