"""
Interface to git-annex by Joey Hess.
See https://git-annex.branchable.com/.
"""
__author__ = 'Benjamin Poldrack'

import os
from os.path import join, exists

from gitrepo import GitRepo
import datalad.log

from datalad.cmd import Runner


class AnnexRepo(GitRepo):
    """
    Representation of an git-annex repository.

    """

    def __init__(self, path, url=None):
        """
        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        :param path: path to git-annex repository
        :param url: valid git url. See http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS
        :return:
        """
        super(AnnexRepo, self).__init__(path, url)

        self.cmd_call_wrapper = Runner()
        # TODO: Concept of when to set to "dry". Includes: What to do in gitrepo class?


        # Check whether an annex already exists at destination
        if not exists(join(self.path, '.git', 'annex')):
            datalad.log.lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self.annex_init()

    def annex_init(self):
        """
        Invokes command 'git annex init'.

        :return:
        """

        os.chdir(self.path)
        # TODO: change back afterwards?

        status, output = self.cmd_call_wrapper.getstatusoutput('git annex init')
        datalad.log.lgr.info('\"git annex init\" outputs:\n %s' % output)
        if status != 0:
            datalad.log.lgr.error('git annex init returned status %d.' % status)


    def dummy_annex_command(self):
        """

        :return:
        """
        raise NotImplementedError
