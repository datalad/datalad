# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to git-annex by Joey Hess.

For further information on git-annex see https://git-annex.branchable.com/.

"""
__author__ = 'Benjamin Poldrack'

from os.path import join, exists

from gitrepo import GitRepo
import datalad.log

from datalad.cmd import Runner


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    """

    def __init__(self, path, url=None):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        path: str
              path to git-annex repository
        url: str
             url to the to-be-cloned repository.
             valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        """
        super(AnnexRepo, self).__init__(path, url)

        self.cmd_call_wrapper = Runner()
        # TODO: Concept of when to set to "dry". Includes: What to do in gitrepo class?


        # Check whether an annex already exists at destination
        if not exists(join(self.path, '.git', 'annex')):
            datalad.log.lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self.annex_init()

    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.
        
        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        status, output = self.cmd_call_wrapper.getstatusoutput('cd %s && git annex init' % self.path)
        datalad.log.lgr.info('\"git annex init\" outputs:\n %s' % output)
        if status != 0:
            datalad.log.lgr.error('git annex init returned status %d.' % status)


    def dummy_annex_command(self):
        """Just a dummy

        No params, nothing to explain, should raise NotImplementedError.

        """
        raise NotImplementedError
