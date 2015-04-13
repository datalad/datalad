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

from os import getcwd
from os.path import join as p_join, exists, normpath, isabs, commonprefix, relpath
import logging

from ConfigParser import NoOptionError

from gitrepo import GitRepo, files_decorator
from datalad.cmd import Runner as Runner
from exceptions import CommandNotAvailableError, CommandError, FileNotInAnnexError, FileInGitError

lgr = logging.getLogger('datalad.annex')


def _options_decorator(func):
    """Decorator to provide convenient way to pass options to command calls.

    Any keyword argument "foo='bar'" translates to " --foo=bar".
    All of these are collected in a list and then passed to keyword argument `options`
    of the decorated function.
    Note: This is meant to especially decorate the methods of AnnexRepo-class and therefore
    returns a class method.
    """

    def newfunc(self, *args, **kwargs):
        option_list=[]
        for key in kwargs.keys():
            option_list.extend([" --%s=%s" % (key, kwargs.get(key))])

        return func(self, *args, options=option_list)
    return newfunc



class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.


    Paths given to any of the class methods will be interpreted as relative to os.getcwd(),
    in case this is currently beneath AnnexRepo's base dir (`self.path`). If os.getcwd() is outside of the repository,
    relative paths will be interpreted as relative to `self.path`.
    Absolute paths will be accepted either way.
    """
    # TODO: Check exceptions for the latter and find a workaround. For example: git annex lookupkey doesn't accept
    # absolute paths. So, build relative paths from absolute ones and may be include checking whether or not they
    # result in a path inside the repo.
    # How to expand paths, if cwd is deeper in repo?
    # git annex proxy will need additional work regarding paths.
    def __init__(self, path, url=None, runner=None, direct=False):
        """Creates representation of git-annex repository at `path`.

        AnnexRepo is initialized by giving a path to the annex.
        If no annex exists at that location, a new one is created.
        Optionally give url to clone from.

        Parameters:
        -----------
        path: str
          path to git-annex repository. In case it's not an absolute path, it's relative to os.getcwd()

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
        if not exists(p_join(self.path, '.git', 'annex')):
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
        if self.is_crippled_fs() and not enable_direct_mode:
            raise CommandNotAvailableError(cmd="git-annex indirect",
                                           msg="Can't switch to indirect mode on that filesystem.")
        mode = 'direct' if enable_direct_mode else 'indirect'
        self.cmd_call_wrapper.run(['git', 'annex', mode], cwd=self.path,
                                  expect_stderr=True)
        #TODO: 1. Where to handle failure? 2. On crippled filesystem don't even try.

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

    @_options_decorator
    @files_decorator
    def annex_get(self, files, options=[]):
        """Get the actual content of files

        Parameters:
        -----------
        files: list
            list of paths to get

        kwargs: options for the git annex get command. For example `from='myremote'` translates to annex option
            "--from=myremote"
        """

        cmd_list = ['git', 'annex', 'get']
        cmd_list.extend(options)
        cmd_list.extend(files)

        #don't capture stderr, since it provides progress display
        status = self.cmd_call_wrapper.run(cmd_list, log_stdout=True, log_stderr=False, log_online=True,
                                           expect_stderr=False, cwd=self.path)

        if status not in [0, None]:
            # TODO: Actually this doesn't make sense. Runner raises exception in this case,
            # which leads to: Runner doesn't have to return it at all.
            lgr.error('git annex get returned status: %s' % status)
            raise CommandError(cmd=' '.join(cmd_list))

    @_options_decorator
    @files_decorator
    def annex_add(self, files, options=[]):
        """Add file(s) to the annex.

        Parameters
        ----------
        files: list
            list of paths to add to the annex
        """

        cmd_list = ['git', 'annex', 'add']
        cmd_list.extend(options)
        cmd_list.extend(files)

        status = self.cmd_call_wrapper.run(cmd_list, cwd=self.path)

        if status not in [0, None]:
            lgr.error("git annex add returned status: %s" % status)
            raise CommandError(cmd=' '.join(cmd_list), msg="", code=status)

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

        status, output = self.cmd_call_wrapper(cmd_str, shell=True, return_output=True, cwd=self.path)
        # TODO: For now return output for testing. This may change later on.

        if status not in [0, None]:
            lgr.error("git annex proxy returned status: %s" % status)
            raise CommandError(cmd=cmd_str, msg="", code=status)

        return output

    @files_decorator
    def get_file_key(self, files):
        """Get key of an annexed file.

        Parameters:
        -----------
        files: list, str
            file to look up

        Returns:
        --------
        str
            key used by git-annex for `path`
        """

        if len(files) > 1:
            raise NotImplementedError("No handling of multiple files implemented yet for get_file_key()!")
        path = files[0]

        cmd_list = ['git', 'annex', 'lookupkey', path]
        cmd_str = ' '.join(cmd_list)  # have a string for messages

        output = None
        try:
            status, output = self.cmd_call_wrapper.run(cmd_list, return_output=True, cwd=self.path)
        except RuntimeError, e:
            # TODO: This has to be changed, due to PR #103, anyway.
            if e.message.find("Failed to run %s" % cmd_list) > -1 and e.message.find("Exit code=1") > -1:
                # if annex command fails we don't get the status directly
                # nor does git-annex propagate IOError (file not found) or sth.
                # So, we have to find out:

                f = open(p_join(self.path, path), 'r')  # raise possible IOErrors
                f.close()

                # if we got here, the file is present and accessible, but not in the annex

                if path in self.get_indexed_files():
                    raise FileInGitError(cmd=cmd_str, msg="File not in annex, but git: %s" % path,
                                              filename=path)

                raise FileNotInAnnexError(cmd=cmd_str, msg="File not in annex: %s" % path,
                                               filename=path)

        key = output[0].split()[0]

        return key

    @files_decorator
    def file_has_content(self, files):
        """ Check whether `files` are present with their content.

        Note: Handling of multiple files not yet implemented!
        TODO: Decide how to behave in case of multiple files, with some of them not present.

        Parameters:
        -----------
        files: list
            file(s) to check for being actually present.
        """
        # TODO: Also provide option to look for key instead of path
        if len(files) > 1:
            raise NotImplementedError("No handling of multiple files implemented yet for file_has_content()!")

        cmd_list = ['git', 'annex', 'find']
        cmd_list.extend(files)

        try:
            status, output = self.cmd_call_wrapper.run(cmd_list, return_output=True, cwd=self.path)
            # TODO: Proper exception/exitcode handling after that topic is reworked in Runner-class
        except RuntimeError, e:
            status = 1

        if status not in [0, None] or output[0] == '':
            is_present = False
        else:
            is_present = output[0].split()[0] == files[0]

        return is_present

    @files_decorator
    def annex_add_to_git(self, files):
        """Add file(s) directly to git

        Parameters
        ----------
        files: list
            list of paths to add to git
        """

        if self.is_direct_mode():
            cmd_list = ['git', '-c', 'core.bare=false', 'add']
            cmd_list.extend(files)

            status = self.cmd_call_wrapper.run(cmd_list, cwd=self.path)
            # TODO: Error handling after Runner's error handling is reworked!

        else:
            self.git_add(files)