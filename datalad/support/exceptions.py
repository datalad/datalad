# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" datalad exceptions
"""

import re
from os import linesep


class CommandError(RuntimeError):
    """Thrown if a command call fails.
    """

    def __init__(self, cmd="", msg="", code=None, stdout="", stderr=""):
        RuntimeError.__init__(self, msg)
        self.cmd = cmd
        self.msg = msg
        self.code = code
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        to_str = "%s: " % self.__class__.__name__
        if self.cmd:
            to_str += "command '%s'" % (self.cmd,)
        if self.code:
            to_str += " failed with exitcode %d" % self.code
        to_str += "\n%s" % self.msg
        return to_str


class MissingExternalDependency(RuntimeError):
    """External dependency is missing error"""

    def __init__(self, name, ver=None, msg=""):
        super(MissingExternalDependency, self).__init__()
        self.name = name
        self.ver = ver
        self.msg = msg

    def __str__(self):
        to_str = str(self.name)
        if self.ver:
            to_str += " of version >= %s" % self.ver
        to_str += " is missing."
        if self.msg:
            to_str += " %s" % self.msg
        return to_str


class DeprecatedError(RuntimeError):
    """To raise whenever a deprecated entirely feature is used"""
    def __init__(self, new=None, version=None, msg=''):
        """

        Parameters
        ----------
        new : str, optional
          What new construct to use
        version : str, optional
          Since which version is deprecated
        kwargs
        """
        super(DeprecatedError, self).__init__()
        self.version = version
        self.new = new
        self.msg = msg

    def __str__(self):
        s = self.msg if self.msg else ''
        if self.version:
            s += (" is deprecated" if s else "Deprecated") + " since version %s." % self.version
        if self.new:
            s += " Use %s instead." % self.new
        return s


class OutdatedExternalDependency(MissingExternalDependency):
    """External dependency is present but outdated"""

    def __init__(self, name, ver=None, ver_present=None, msg=""):
        super(OutdatedExternalDependency, self).__init__(name, ver=ver, msg=msg)
        self.ver_present = ver_present

    def __str__(self):
        to_str = super(OutdatedExternalDependency, self).__str__()
        to_str += ". You have version %s" % self.ver_present \
            if self.ver_present else \
            " Some unknown version of dependency found."
        return to_str


class AnnexBatchCommandError(CommandError):
    """Thrown if a batched command to annex fails

    """
    pass


class CommandNotAvailableError(CommandError):
    """Thrown if a command is not available due to certain circumstances.
    """
    pass


class FileNotInAnnexError(IOError, CommandError):
    """Thrown if a file is not under control of git-annex.
    """
    def __init__(self, cmd="", msg="", code=None, filename=""):
        CommandError.__init__(self, cmd=cmd, msg=msg, code=code)
        IOError.__init__(self, code, "%s: %s" % (cmd, msg), filename)

    def __str__(self):
        return "%s\n%s" % (CommandError.__str__(self), IOError.__str__(self))


class FileInGitError(FileNotInAnnexError):
    """Thrown if a file is not under control of git-annex, but git itself.
    """
    pass


class FileNotInRepositoryError(FileNotInAnnexError):
    """Thrown if a file is not under control of the repository at all.
    """
    pass


class GitIgnoreError(CommandError):
    """Thrown if a path was ignored by a git command due to .gitignore file

    Note, that this might be thrown to indicate what was ignored, while the
    actual operation was partially successful (regarding paths, not in .gitignore)

    Note/Todo:
    in case of a directory being ignored, git returns that directory as the
    ignored path, even if a path within that directory was passed to the command.
    That means, that in such cases the returned path might not match an item you
    passed!
    """

    pattern = \
        re.compile(r'ignored by one of your .gitignore files:\s*(.*)^Use -f.*$',
                   flags=re.MULTILINE | re.DOTALL)

    def __init__(self, cmd="", msg="", code=None, stdout="", stderr="",
                 paths=None):
        super(GitIgnoreError, self).__init__(
            cmd=cmd, msg=msg, code=code, stdout=stdout, stderr=stderr)
        self.paths = paths

    def __str__(self):
        return self.msg


class PathOutsideRepositoryError(Exception):
    """Thrown if a path points outside the repository that was requested to
    deal with that path."""

    # TODO: use it in GitRepo/AnnexRepo!
    def __init__(self, file_, repo):
        self.file_ = file_
        self.repo = repo

    def __str__(self):
        return "path {0} not within repository {1}".format(self.file_, self.repo)


class MissingBranchError(Exception):
    """Thrown if accessing a repository's branch, that is not available"""

    def __init__(self, repo, branch, available_branches=None, msg=None):
        self.repo = repo
        self.branch = branch
        self.branches = available_branches
        if msg is None:
            self.msg = "branch '{0}' missing in {1}." \
                       "".format(self.branch, self.repo)
            if self.branches:
                self.msg += " Available branches: {0}".format(self.branches)
        else:
            self.msg = msg

    def __str__(self):
        return self.msg


class InsufficientArgumentsError(ValueError):
    """To be raise instead of `ValueError` when use help output is desired"""
    pass


class NoDatasetArgumentFound(InsufficientArgumentsError):
    """To be raised when expecting having a dataset but none was provided"""
    pass


class OutOfSpaceError(CommandError):
    """To be raised whenever a command fails if we have no sufficient space

    Example is  annex get command
    """

    def __init__(self, sizemore_msg=None, **kwargs):
        super(OutOfSpaceError, self).__init__(**kwargs)
        self.sizemore_msg = sizemore_msg

    def __str__(self):
        super_str = super(OutOfSpaceError, self).__str__().rstrip(linesep + '.')
        return "%s needs %s more" % (super_str, self.sizemore_msg)


class RemoteNotAvailableError(CommandError):
    """To be raised whenever a required remote is not available

    Example is "annex get somefile --from=MyRemote",
    where 'MyRemote' doesn't exist.
    """

    # TODO: Raise this from GitRepo. Currently depends on method:
    # Either it's a direct git call
    #   => CommandError and stderr:
    #       fatal: 'notthere' does not appear to be a git repository
    #       fatal: Could not read from remote repository.
    # or it's a GitPython call
    #   => ValueError "Remote named 'NotExistingRemote' didn't exist"

    def __init__(self, remote, **kwargs):
        """

        Parameters
        ----------
        remote: str
          name of the remote
        kwargs:
          arguments from CommandError
        """
        super(RemoteNotAvailableError, self).__init__(**kwargs)
        self.remote = remote

    def __str__(self):
        super_str = super(RemoteNotAvailableError, self).__str__()
        return "Remote '{0}' is not available. Command failed:{1}{2}" \
               "".format(self.remote, linesep, super_str)


class InvalidInstanceRequestError(RuntimeError):
    """Thrown if a request to create a (flyweight) instance is invalid"""

    def __init__(self, id_, msg=None):
        super(InvalidInstanceRequestError, self).__init__(msg)
        self.id = id_
        self.msg = msg


class IncompleteResultsError(RuntimeError):
    """Exception to be raised whenever results are incomplete.

    Any results produced nevertheless are to be passed as `results`,
    and become available via the `results` attribute.
    """
    # TODO passing completed results doesn't fit in a generator paradigm
    # such results have been yielded already at the time this exception is
    # raised, little point in collecting them just for the sake of a possible
    # exception
    # MIH: AnnexRepo is the last remaining user of this functionality, in a
    # single context
    def __init__(self, results=None, failed=None, msg=None):
        super(IncompleteResultsError, self).__init__(msg)
        self.results = results
        self.failed = failed

    def __str__(self):
        super_str = super(IncompleteResultsError, self).__str__()
        return "{} {}" \
               "".format(super_str, self.failed)

class InstallFailedError(CommandError):
    """Generic exception to raise whenever `install` command fails"""
    pass


#
# Downloaders
#


class DownloadError(Exception):
    pass


class IncompleteDownloadError(DownloadError):
    pass


class UnaccountedDownloadError(IncompleteDownloadError):
    pass


class TargetFileAbsent(DownloadError):
    pass


class AccessDeniedError(DownloadError):
    pass


class AccessFailedError(DownloadError):
    pass


class UnhandledRedirectError(DownloadError):
    def __init__(self, msg=None, url=None, **kwargs):
        super(UnhandledRedirectError, self).__init__(msg, **kwargs)
        self.url = url

#
# Crawler
#


class CrawlerError(Exception):
    pass


class PipelineNotSpecifiedError(CrawlerError):
    pass
