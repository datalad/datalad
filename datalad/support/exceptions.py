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


class FileNotInAnnexError(CommandError, IOError):
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


class PathOutsideRepositoryError(Exception):
    """Thrown if a path points outside the repository that was requested to
    deal with that path."""

    # TODO: use it in GitRepo/AnnexRepo!
    def __init__(self, file_, repo):
        self.file_ = file_
        self.repo = repo

    def __str__(self):
        return "path {0} not within repository {1}".format(self.file_, self.repo)


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


class IncompleteResultsError(RuntimeError):
    """Exception to be raised whenever results are incomplete.

    Any results produced nevertheless are to be passed as `results`,
    and become available via the `results` attribute.
    """
    def __init__(self, results=None, failed=None, msg=None):
        super(IncompleteResultsError, self).__init__(msg)
        self.results = results
        self.failed = failed


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
