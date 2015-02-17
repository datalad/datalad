"""
Interface to Git via GitPython
See http://gitpython.readthedocs.org/
"""
__author__ = 'Benjamin Poldrack'

from git import Repo
from os.path import join, exists


class GitRepo(object):
    """
    Representation of a git repository

    Not sure if needed yet, since there is GitPython. By now, wrap it to have control.
    """

    def __init__(self, path, url=None):
        """
        Creates representation of git repository at path. If there is no git repository at this location, git init is invoked.
        Additionally the directory is created if it doesn't exist.
        If url is given, a clone is created at path

        :param path: path to git repository.
        :param url: valid git url. See http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS
        :return:
        """

        assert isinstance(path, basestring)
        self.path = path

        if url is not None:
            Repo.clone_from(url, path)  # more arguments possible: ObjectDB etc.


        if not exists(join(path, '.git')):
            self.repo = Repo.init(path, True)
        else:
            self.repo = Repo(path)
        assert(isinstance(self.repo, Repo))

    def dummy_git_command(self):
        raise NotImplementedError