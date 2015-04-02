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
import logging

from ConfigParser import NoOptionError

from gitrepo import GitRepo
from datalad.cmd import Runner as Runner
from exceptions import CommandNotAvailableError, CommandError, FileNotInAnnexError, FileInGitError

lgr = logging.getLogger('datalad.annex')


class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    """

    def __init__(self, path, url=None, runner=None, direct=False):
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

        runner: Runner
           Provide a Runner in case AnnexRepo shall not create it's own. This is especially needed in case of
           desired dry runs.

        direct: bool
           If True, force git-annex to use direct mode
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

        if direct and not self.is_direct_mode():  # only force direct mode; don't force indirect mode
            self.set_direct_mode()

    def is_direct_mode(self):
        """Indicates whether or not annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """

        try:
            dm = self.repo.config_reader().get_value("annex", "direct")
        except NoOptionError, e:
            #If .git/config lacks an entry "direct" it's actually indirect mode.
            dm = False

        return dm

    def is_crippled_fs(self):
        """Indicates whether or not git-annex considers current filesystem 'crippled'.

        Returns
        -------
        True if on crippled filesystem, False otherwise
        """

        try:
            cr_fs = self.repo.config_reader().get_value("annex", "crippledfilesystem")
        except NoOptionError, e:
            #If .git/config lacks an entry "crippledfilesystem" it's actually not crippled.
            cr_fs = False

        return cr_fs

    def set_direct_mode(self, enable_direct_mode=True):
        """Switch to direct or indirect mode

        Parameters
        ----------
        enable_direct_mode: bool
            True means switch to direct mode,
            False switches to indirect mode

        Raises
        ------
        CommandNotAvailableError
            in case you try to switch to indirect mode on a crippled filesystem
        """

        if enable_direct_mode:
            self.cmd_call_wrapper.run(['git', 'annex', 'direct'], cwd=self.path)
        elif not self.is_crippled_fs():
            self.cmd_call_wrapper.run(['git', 'annex', 'indirect'], cwd=self.path)
        else:
            raise CommandNotAvailableError(cmd="git-annex indirect",
                                                msg="Can't switch to indirect mode on that filesystem.")


    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        status = self.cmd_call_wrapper.run(['git', 'annex', 'init'], cwd=self.path)
        # TODO: When to expect stderr? on crippled filesystem for example (think so)?
        if status not in [0, None]:
            lgr.error('git annex init returned status %d.' % status)


    def annex_get(self, files, **kwargs):
        """Get the actual content of files

        Parameters:
        -----------
        files: list
            list of paths to get

        kwargs: options for the git annex get command. For example `from='myremote'` translates to annex option
            "--from=myremote"
        """

        # Since files is a list of paths, we have to care for escaping special characters, etc.
        # at this point. For now just quote all of them (at least this should handle spaces):
        paths = '"' + '" "'.join(files) + '"'
        #TODO: May be this should go in a decorator for use in every command.

        options = ''
        for key in kwargs.keys():
            options += " --%s=%s" % (key, kwargs.get(key))
        #TODO: May be this should go in a decorator for use in every command.

        cmd_str = 'git annex get %s %s' % (options, paths)
        # TODO: make it a list instead of a string
        # TODO: Do we want to cd to self.path first? This would lead to expand paths, if
        # cwd is deeper in repo.


        #don't capture stderr, since it provides progress display
        status = self.cmd_call_wrapper.run(cmd_str, log_stdout=True, log_stderr=False, log_online=True, expect_stderr=False)

        if status not in [0, None]:
            # TODO: Actually this doesn't make sense. Runner raises exception in this case,
            # which leads to: Runner doesn't have to return it at all.
            lgr.error('git annex get returned status: %s' % status)
            raise CommandError(cmd=cmd_str)

    def annex_add(self, files):
        """Add file(s) to the annex.

        Parameters
        ----------
        files: list
            list of paths to add to the annex
        """

        # Since files is a list of paths, we have to care for escaping special characters, etc.
        # at this point. For now just quote all of them (at least this should handle spaces):
        paths = '"' + '" "'.join(files) + '"'
        # TODO: May be this should go in a decorator for use in every command.
        #
        # TODO: When using a list and not shell=True, some quoting is already done.
        # Figure out how this works on different platforms before changing the runner calls.

        cmd_str = 'git annex add %s' % paths


        status = self.cmd_call_wrapper.run(cmd_str, shell=True)

        if status not in [0, None]:
            lgr.error("git annex add returned status: %s" % status)
            raise CommandError(cmd="git-annex add %s" % paths, msg="", code=status)

    def annex_proxy(self, git_cmd):
        """Use git-annex as a proxy to git

        This is needed in case we are in direct mode, since there's no git working tree, that git can handle.

        Parameters:
        -----------
        git_cmd: str
            the actual git command

        Returns:
        --------
        output: tuple
            a tuple constisting of the lines of the output to stdout
            Note: This may change. See TODO.
        """

        cmd_str = "git annex proxy -- %s" % git_cmd
        # TODO: By now git_cmd is expected to be string. Figure out how to deal with a list here.

        if not self.is_direct_mode():
            lgr.warning("annex_proxy called in indirect mode: %s" % git_cmd)
            raise CommandNotAvailableError(cmd=cmd_str, msg="Proxy doesn't make sense if not in direct mode.")

        status, output = self.cmd_call_wrapper(cmd_str, shell=True, return_output=True)
        # TODO: For now return output for testing. This may change later on.

        if status not in [0, None]:
            lgr.error("git annex proxy returned status: %s" % status)
            raise CommandError(cmd=cmd_str, msg="", code=status)

        return output

    def get_file_key(self, path_to_file):
        """Get key of an annexed file

        Parameters:
        -----------
        path_to_file: str
            file to look up

        Returns:
        --------
        key: str

        """

        cmd_str = "git annex lookupkey %s" % path_to_file

        try:
            status, output = self.cmd_call_wrapper.run(cmd_str, shell=True, return_output=True)
        except RuntimeError, e:
            if e.message.find("Failed to run '%s'" % cmd_str) > -1 and e.message.find("Exit code=1") > -1:
                # if annex command fails we don't get the status directly
                # nor does git-annex propagate IOError (file not found) or sth.
                # So, we have to find out:

                f = open(path_to_file, 'r')  # raise possible IOErrors
                f.close()

                # if we got here, the file is present and accessible, but not in the annex

                if path_to_file in self.get_indexed_files():
                    raise FileInGitError(cmd=cmd_str, msg="File not in annex, but git: %s" % path_to_file,
                                              filename=path_to_file)

                raise FileNotInAnnexError(cmd=cmd_str, msg="File not in annex: %s" % path_to_file,
                                               filename=path_to_file)

        key = output[0].split()[0]

        return key