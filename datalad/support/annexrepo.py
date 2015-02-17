"""
Interface to git-annex by Joey Hess.
See https://git-annex.branchable.com/.
"""
__author__ = 'Benjamin Poldrack'

from os.path import join, exists

from gitrepo import GitRepo

from ..cmd import Runner


class AnnexRepo(object):
    """
    Representation of an git-annex repository.

    """

    def __init__(self, destination):
        """
        AnnexRepo can be initialized alternatively by giving a path to the annex or an object of class GitRepo, that points to the underlying Git repository
        If a path is given, a GitRepo will be created.
        :param destination: path to git-annex repository
        :return:
        """

        # check argument:
        if isinstance(destination, GitRepo):
            self.gitrepo = destination
        elif isinstance(destination, basestring):
            self.gitrepo = GitRepo(destination)
        else:
            raise TypeError

        self.path = self.gitrepo.get_path()

        # Check whether an annex already exists at destination
        if not exists(join(self.path, '.git', 'annex')):
            self.annex_init()

    def annex_init(self):
        os.chdir(self.path)
        # TODO: change back afterwards?

        os.system('git annex init')
        # TODO: use the "Runner" for dry runs and getting output

    def dummy_annex_command(self):
        """

        :return:
        """
        raise NotImplementedError
