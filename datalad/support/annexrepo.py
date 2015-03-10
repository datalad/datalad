# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
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

from os.path import join, exists
import glob
import logging

from gitrepo import GitRepo
import datalad.log

from datalad.cmd import Runner as Runner

lgr = logging.getLogger('datalad.annex')


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    """

    def __init__(self, path, url=None, runner=None):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters:
        -----------
        path: str
          path to git-annex repository
        url: str
          url to the to-be-cloned repository.
          valid git url according to http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS required.

        """
        super(AnnexRepo, self).__init__(path, url)

        self.cmd_call_wrapper = runner or Runner()
        # TODO: Concept of when to set to "dry". Includes: What to do in gitrepo class?
        #       Now: setting "dry" means to give a dry-runner to constructor.
        #       => Do it similar in gitrepo/dataset. Still we need a concept of when to set it
        #       and whether this should be a single instance collecting everything or more
        #       fine grained.

        # Check whether an annex already exists at destination
        if not exists(join(self.path, '.git', 'annex')):
            lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self._annex_init()

    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        status = self.cmd_call_wrapper.run('cd %s && git annex init' % self.path)
        if status not in [0, None]:
            lgr.error('git annex init returned status %d.' % status)


    def annex_get(self, pattern, **kwargs):
        """Get the actual content of files

        Parameters:
        -----------
        pattern: str
            glob pattern defining what files to get

        kwargs: options for the git annex get command. For example `from='myremote'` translates to annex option
            "--from=myremote"
        """

        paths = glob.glob(pattern)
        #TODO: regexp + may be ext. glob zsh-style

        pathlist = ''
        for path in paths:
            pathlist += ' ' + path

        optlist = ''
        for key in kwargs.keys():
            optlist += " --%s=%s" % (key, kwargs.get(key))
        #TODO: May be this should go in a decorator for use in every command.

        cmd_str = 'cd %s && git annex get %s %s' % (self.path, optlist, pathlist)
        # TODO: Do we want to cd to self.path first? This would lead to expand paths, if
        # cwd is deeper in repo.


        #don't capture stderr, since it provides progress display
        status = self.cmd_call_wrapper.run(cmd_str, log_stderr=False)

        if status not in [0, None]:
            # TODO: Actually this doesn't make sense. Runner raises exception in this case,
            # which leads to: Runner doesn't have to return it at all.
            lgr.error('git annex get returned status: %s' % status)
            raise RuntimeError
