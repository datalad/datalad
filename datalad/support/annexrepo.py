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

from os import linesep
from os.path import join as opj, exists, normpath, isabs, commonprefix, relpath
import logging

from functools import wraps

from ConfigParser import NoOptionError

from gitrepo import GitRepo, normalize_paths
from datalad.cmd import Runner as Runner
from exceptions import CommandNotAvailableError, CommandError, \
    FileNotInAnnexError, FileInGitError

lgr = logging.getLogger('datalad.annex')


def kwargs_to_options(func):
    """Decorator to provide convenient way to pass options to command calls.

    Any keyword argument "foo='bar'" translates to " --foo=bar".
    All of these are collected in a list and then passed to keyword argument
    `options` of the decorated function.

    Note
    ----

    This is meant to especially decorate the methods of AnnexRepo-class and
    therefore returns a class method.
    """

    @wraps(func)
    def newfunc(self, *args, **kwargs):
        option_list = []
        for key in kwargs.keys():
            option_list.extend([" --%s=%s" % (key, kwargs.get(key))])

        return func(self, *args, options=option_list)
    return newfunc



class AnnexRepo(GitRepo):
    """Representation of an git-annex repository.

    Paths given to any of the class methods will be interpreted as relative
    to os.getcwd(), in case this is currently beneath AnnexRepo's base dir
    (`self.path`). If os.getcwd() is outside of the repository, relative paths
    will be interpreted as relative to `self.path`. Absolute paths will be
    accepted either way.
    """
    # TODO: Check exceptions for the latter and find a workaround. For
    # example: git annex lookupkey doesn't accept absolute paths. So,
    # build relative paths from absolute ones and may be include checking
    # whether or not they result in a path inside the repo.
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
          path to git-annex repository. In case it's not an absolute path, it's
          relative to os.getcwd()

        url: str
          url to the to-be-cloned repository. Requires valid git url according to
          http://www.kernel.org/pub/software/scm/git/docs/git-clone.html#URLS .

        runner: Runner
           Provide a Runner in case AnnexRepo shall not create it's own. This is
           especially needed in case of desired dry runs.

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
        if not exists(opj(self.path, '.git', 'annex')):
            lgr.debug('No annex found in %s. Creating a new one ...' % self.path)
            self._annex_init()

        # only force direct mode; don't force indirect mode
        if direct and not self.is_direct_mode():
            self.set_direct_mode()


    def is_direct_mode(self):
        """Indicates whether or not annex is in direct mode

        Returns
        -------
        True if in direct mode, False otherwise.
        """

        try:
            return self.repo.config_reader().get_value("annex", "direct")
        except NoOptionError, e:
            # If .git/config lacks an entry "direct" it's actually indirect mode.
            return False


    def is_crippled_fs(self):
        """Indicates whether or not git-annex considers current filesystem 'crippled'.

        Returns
        -------
        True if on crippled filesystem, False otherwise
        """

        try:
            return self.repo.config_reader().get_value("annex", "crippledfilesystem")
        except NoOptionError, e:
            # If .git/config lacks an entry "crippledfilesystem" it's actually not crippled.
            return False


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
        # TODO: 1. Where to handle failure?


    def _annex_init(self):
        """Initializes an annex repository.

        Note: This is intended for private use in this class by now.
        If you have an object of this class already, there shouldn't be a need to 'init' again.

        """
        # TODO: provide git and git-annex options.
        # TODO: Document (or implement respectively) behaviour in special cases like direct mode (if it's different),
        # not existing paths, etc.

        self.cmd_call_wrapper.run(['git', 'annex', 'init'], cwd=self.path)
        # TODO: When to expect stderr? on crippled filesystem for example (think so)?


    @kwargs_to_options
    @normalize_paths
    def annex_get(self, files, options=[]):
        """Get the actual content of files

        Parameters:
        -----------
        files: list
            list of paths to get

        kwargs: options for the git annex get command. For example `from='myremote'`
         translates to annex option "--from=myremote"
        """

        cmd_list = ['git', 'annex', 'get'] + options + files

        #don't capture stderr, since it provides progress display
        self.cmd_call_wrapper.run(cmd_list, log_stdout=True, log_stderr=False,
                                  log_online=True, expect_stderr=True,
                                  cwd=self.path)


    @kwargs_to_options
    @normalize_paths
    def annex_add(self, files, options=[]):
        """Add file(s) to the annex.

        Parameters
        ----------
        files: list
            list of paths to add to the annex
        """

        cmd_list = ['git', 'annex', 'add'] + options + files
        self.cmd_call_wrapper.run(cmd_list, cwd=self.path)


    def annex_proxy(self, git_cmd):
        """Use git-annex as a proxy to git

        This is needed in case we are in direct mode, since there's no git
        working tree, that git can handle.

        Parameters:
        -----------
        git_cmd: str
            the actual git command

        Returns:
        --------
        str containing stdout of the command
        """

        cmd_str = "git annex proxy -- %s" % git_cmd
        # TODO: By now git_cmd is expected to be string. Figure out how to deal with a list here.

        if not self.is_direct_mode():
            lgr.warning("annex_proxy() called in indirect mode: %s" % git_cmd)
            raise CommandNotAvailableError(cmd=cmd_str, msg="Proxy doesn't make sense if not in direct mode.")
        try:
            out = self.cmd_call_wrapper(cmd_str, shell=True, cwd=self.path)
        except CommandError, e:
            if "Unknown command" in e.stderr:
                raise CommandNotAvailableError(cmd=cmd_str, msg=e.msg,
                                               stderr=e.stderr, stdout=e.stdout)
            else:
                raise e
        return out


    @normalize_paths
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

        try:
            output = self.cmd_call_wrapper.run(cmd_list, cwd=self.path)
        except CommandError, e:
            if e.code == 1:
                if not exists(opj(self.path, path)):
                    raise IOError(e.code, "File not found.", path)
                elif path in self.get_indexed_files():
                    # if we got here, the file is present and in git, but not in the annex
                    raise FileInGitError(cmd=cmd_str, msg="File not in annex, but git: %s" % path,
                                              filename=path)
                else:
                    raise FileNotInAnnexError(cmd=cmd_str, msg="File not in annex: %s" % path,
                                               filename=path)
            else:
                # Not sure, whether or not this can actually happen
                raise e

        return output[0].split(linesep)[0]


    @normalize_paths
    def file_has_content(self, files):
        """ Check whether `files` are present with their content.

        Parameters:
        -----------
        files: list
            file(s) to check for being actually present.

        Returns:
        --------
        list of (str, bool)
            list with a tuple per file in `files`.
        """
        # TODO: Also provide option to look for key instead of path

        cmd_list = ['git', 'annex', 'find'] + files

        try:
            output = self.cmd_call_wrapper.run(cmd_list, cwd=self.path)
        except CommandError, e:
            if e.code == 1 and \
                    "%s not found" % files[0] in e.stderr:
                return False
            else:
                raise

        return [(f, f in set(output[0].split(linesep))) for f in files]

    @normalize_paths
    def annex_add_to_git(self, files):
        """Add file(s) directly to git

        Parameters
        ----------
        files: list
            list of paths to add to git
        """

        if self.is_direct_mode():
            cmd_list = ['git', '-c', 'core.bare=false', 'add'] + files
            self.cmd_call_wrapper.run(cmd_list, cwd=self.path)
        else:
            self.git_add(files)

    def annex_initremote(self, name, options):
        """Creates a new special remote

        Parameters:
        -----------
        name: str
            name of the special remote
        """
        # TODO: figure out consistent way for passing options + document

        cmd_list = ['git', 'annex', 'initremote', name] + options
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    def annex_enableremote(self, name):
        """Enables use of an existing special remote

        Parameters:
        -----------
        name: str
            name, the special remote was created with
        """

        cmd_list = ['git', 'annex', 'enableremote', name]
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    @normalize_paths
    def annex_addurl_to_file(self, file, url, options=[]):
        """Add file from url to the annex.

        Downloads `file` from `url` and add it to the annex.
        If annex knows `file` already, records that it can be downloaded from `url`.

        Parameters:
        -----------
        file: str
            technically it's a list, but conversion is done by the decorator and
            only a single string will work here.
            TODO: figure out, how to document this behaviour properly everywhere

        url: str
        """

        cmd_list = ['git', 'annex', 'addurl', '--file=%s' % file[0]] + options + [url]
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    def annex_addurl(self, urls, options=[]):
        """Downloads each url to its own file, which is added to the annex.

        Parameters:
        -----------
        urls: list
        """

        cmd_list = ['git', 'annex', 'addurl'] + options + urls
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    @normalize_paths
    def annex_rmurl(self, file, url):
        """Record that the file is no longer available at the url.
        """

        cmd_list = ['git', 'annex', 'rmurl', file[0], url]
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    @normalize_paths
    def annex_drop(self, files):
        """Drops the content of annexed files from this repository, when possible.
        """
        # TODO: options needed

        cmd_list = ['git', 'annex', 'drop'] + files
        self.cmd_call_wrapper(cmd_list, cwd=self.path)

    def annex_whereis(self, files):
        """Lists repositories that have file content
        """
        # TODO: May be use JSON-output (--json) to parse it
        # TODO: What to return? Just a list of names?
        raise NotImplementedError("git-annex 'whereis' not yet implemented.")