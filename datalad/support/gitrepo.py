"""
Interface to Git via GitPython
See http://gitpython.readthedocs.org/
"""
__author__ = 'Benjamin Poldrack'

from os.path import join, exists

from git import Repo
from git.exc import GitCommandError

import datalad.log

# TODO: Figure out how GIT_PYTHON_TRACE ('full') is supposed to be used.
# Didn't work as expected on a first try. Probably there is a neatier way to log Exceptions from git commands.

class GitRepo(object):
    """
    Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have control.
    Convention: method's names starting with 'git_' to not be overridden accidentally by AnnexRepo.
    """

    def __init__(self, path, url=None):
        """
        Creates representation of git repository at path. If there is no git repository at this location,
        git init is invoked.
        Additionally the directory is created if it doesn't exist.
        If url is given, a clone is created at path

        :param path: path to git repository.
        :param url: valid git url. See http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS
        :return:
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
        raise NotImplementedError