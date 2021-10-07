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

import logging
import re
import traceback
from os import linesep
from pathlib import Path
from pprint import pformat

from datalad.runner.exception import CommandError

lgr = logging.getLogger('datalad.support.exceptions')


class CapturedException(object):
    """This class represents information about an occurred exception (including
    its traceback), while not holding any references to the actual exception
    object or its traceback, frame references, etc.

    Just keep the textual information for logging or whatever other kind of
    reporting.
    """

    def __init__(self, exc, limit=None, capture_locals=False,
                 level=8, logger=None):
        """Capture an exception and its traceback for logging.

        Clears the exception's traceback frame references afterwards.

        Parameters
        ----------
        exc: Exception
        limit: int
          Note, that this is limiting the capturing of the exception's
          traceback depth. Formatting for output comes with it's own limit.
        capture_locals: bool
          Whether or not to capture the local context of traceback frames.
        """
        # Note, that with lookup_lines=False the lookup is deferred,
        # not disabled. Unclear to me ATM, whether that means to keep frame
        # references around, but prob. not. TODO: Test that.
        self.tb = traceback.TracebackException.from_exception(
            exc,
            limit=limit,
            lookup_lines=True,
            capture_locals=capture_locals
        )
        traceback.clear_frames(exc.__traceback__)

        # log the captured exception
        logger = logger or lgr
        logger.log(level, "%r", self)

    def format_oneline_tb(self, limit=None, include_str=True):
        """Format an exception traceback as a one-line summary

        Returns a string of the form [filename:contextname:linenumber, ...].
        If include_str is True (default), this is prepended with the string
        representation of the exception.
        """

        # Note: No import at module level, since ConfigManager imports
        # dochelpers -> circular import when creating datalad.cfg instance at
        # startup.
        from datalad import cfg

        if include_str:
            # try exc message else exception type
            leading = self.message or self.name
            out = "{} ".format(leading)
        else:
            out = ""

        entries = []
        entries.extend(self.tb.stack)
        if self.tb.__cause__:
            entries.extend(self.tb.__cause__.stack)
        elif self.tb.__context__ and not self.tb.__suppress_context__:
            entries.extend(self.tb.__context__.stack)

        if limit is None:
            limit = int(cfg.obtain('datalad.exc.str.tblimit',
                                   default=len(entries)))
        if entries:
            tb_str = "[%s]" % (','.join(
                "{}:{}:{}".format(
                    Path(frame_summary.filename).name,
                    frame_summary.name,
                    frame_summary.lineno)
                for frame_summary in entries[-limit:])
            )
            out += "{}".format(tb_str)

        return out

    def format_standard(self):
        """Returns python's standard formatted traceback output

        Returns
        -------
        str
        """
        # TODO: Intended for introducing a decent debug mode later when this
        #       can be used fromm within log formatter / result renderer.
        #       For now: a one-liner is free
        return ''.join(self.tb.format())

    def format_short(self):
        """Returns a short representation of the original exception

        Form: ExceptionName(exception message)

        Returns
        -------
        str
        """
        return self.name + '(' + self.message + ')'

    @property
    def message(self):
        """Returns only the message of the original exception

        Returns
        -------
        str
        """
        return str(self.tb)

    @property
    def name(self):
        """Returns the class name of the original exception

        Returns
        -------
        str
        """
        return self.tb.exc_type.__qualname__

    def __str__(self):
        return self.format_short()

    def __repr__(self):
        return self.format_oneline_tb(limit=None, include_str=True)


class MissingExternalDependency(RuntimeError):
    """External dependency is missing error"""

    def __init__(self, name, ver=None, msg=""):
        super(MissingExternalDependency, self).__init__()
        self.name = name
        self.ver = ver
        self.msg = msg

    def __str__(self):
        to_str = 'No working {} installation'.format(self.name)
        if self.ver:
            to_str += " of version >= %s" % self.ver
        to_str += "."
        if self.msg:
            to_str += " %s" % self.msg
        return to_str


class BrokenExternalDependency(RuntimeError):
    """Some particular functionality is broken with this dependency."""


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
        # MissingExternalDependency ends with a period unless msg is
        # given, in which case it's up to the msg and no callers in
        # our code base currently give a msg ending with a period.
        to_str += "." if self.msg else ""
        to_str += " You have version %s" % self.ver_present \
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

    def to_str(self, include_output=True):
        return "%s\n%s" % (
            CommandError.to_str(self, include_output=include_output),
            IOError.__str__(self))


class FileInGitError(FileNotInAnnexError):
    """Thrown if a file is not under control of git-annex, but git itself.
    """
    pass


class FileNotInRepositoryError(FileNotInAnnexError):
    """Thrown if a file is not under control of the repository at all.
    """
    pass


class InvalidGitReferenceError(ValueError):
    """Thrown if provided git reference is invalid
    """
    def __init__(self, ref, *args, **kwargs):
        super(InvalidGitReferenceError, self).__init__(*args, **kwargs)
        self.ref = ref

    def __str__(self):
        return u"Git reference '{}' invalid".format(self.ref)


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
        re.compile(r'ignored by one of your .gitignore files:\s*(.*)'
                   r'^(?:hint: )?Use -f.*$',
                   flags=re.MULTILINE | re.DOTALL)

    def __init__(self, cmd="", msg="", code=None, stdout="", stderr="",
                 paths=None):
        super(GitIgnoreError, self).__init__(
            cmd=cmd, msg=msg, code=code, stdout=stdout, stderr=stderr)
        self.paths = paths

    def to_str(self, include_output=True):
        # Override CommandError.to_str(), ignoring include_output.
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


class PathKnownToRepositoryError(Exception):
    """Thrown if file/path is under Git control, and attempted operation
    must not be ran"""
    pass


class GitError(Exception):
    """ Base class for all package exceptions """


class NoSuchPathError(GitError, OSError):
    """ Thrown if a path could not be access by the system. """


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


class NoDatasetFound(NoDatasetArgumentFound):
    """Raised whenever a dataset is required, but none could be determined"""
    pass


class OutOfSpaceError(CommandError):
    """To be raised whenever a command fails if we have no sufficient space

    Example is  annex get command
    """

    def __init__(self, sizemore_msg=None, **kwargs):
        super(OutOfSpaceError, self).__init__(**kwargs)
        self.sizemore_msg = sizemore_msg

    def to_str(self, include_output=True):
        super_str = super().to_str(
            include_output=include_output).rstrip(linesep + '.')
        return "%s needs %s more" % (super_str, self.sizemore_msg)


class RemoteNotAvailableError(CommandError):
    """To be raised whenever a required remote is not available

    Example is "annex get somefile --from=MyRemote",
    where 'MyRemote' doesn't exist.
    """

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

    def to_str(self, include_output=True):
        super_str = super().to_str(include_output=include_output)
        return "Remote '{0}' is not available. Command failed:{1}{2}" \
               "".format(self.remote, linesep, super_str)


class InvalidInstanceRequestError(RuntimeError):
    """Thrown if a request to create a (flyweight) instance is invalid"""

    def __init__(self, id_, msg=None):
        super(InvalidInstanceRequestError, self).__init__(msg)
        self.id = id_
        self.msg = msg


class InvalidGitRepositoryError(GitError):
    """ Thrown if the given repository appears to have an invalid format.  """


class InvalidAnnexRepositoryError(RuntimeError):
    """Thrown if AnnexRepo was instantiated on a non-annex and
    without init=True"""


class DirectModeNoLongerSupportedError(NotImplementedError):
    """direct mode is no longer supported"""

    def __init__(self, repo, msg=None):
        super(DirectModeNoLongerSupportedError, self).__init__(
            ((" " + msg + ", but ") if msg else '')
            +
             "direct mode of operation is being deprecated in git-annex and "
             "no longer supported by DataLad. "
             "Please use 'git annex upgrade' under %s to upgrade your direct "
             "mode repository to annex v6 (or later)." % repo.path
            )
        self.repo = repo  # might come handy


class IncompleteResultsError(RuntimeError):
    """Exception to be raised whenever results are incomplete.

    Any results produced nevertheless are to be passed as `results`,
    and become available via the `results` attribute.
    """
    # TODO passing completed results doesn't fit in a generator paradigm
    # such results have been yielded already at the time this exception is
    # raised, little point in collecting them just for the sake of a possible
    # exception
    # MIH+YOH: AnnexRepo.copy_to and @eval_results are the last
    # remaining user of this functionality.
    # General use (as in AnnexRepo) of it discouraged but use in @eval_results
    # is warranted
    def __init__(self, results=None, failed=None, msg=None):
        super(IncompleteResultsError, self).__init__(msg)
        self.results = results
        self.failed = failed

    def __str__(self):
        super_str = super(IncompleteResultsError, self).__str__()
        return "{}{}{}".format(
            super_str,
            ". {} result(s)".format(len(self.results)) if self.results else "",
            ". {} failed:{}{}".format(
                len(self.failed),
                linesep,
                pformat(self.failed)) if self.failed else "")


class InstallFailedError(CommandError):
    """Generic exception to raise whenever `install` command fails"""
    pass


class ConnectionOpenFailedError(CommandError):
    """Exception to raise whenever opening a network connection fails"""
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
    def __init__(self, msg=None, supported_types=None, **kwargs):
        super(AccessDeniedError, self).__init__(msg, **kwargs)
        self.supported_types = supported_types


class AnonymousAccessDeniedError(AccessDeniedError):
    pass


class AccessPermissionExpiredError(AccessDeniedError):
    """To raise when there is a belief that it is due to expiration of a credential

    which we might possibly be able to refresh, like in the case of CompositeCredential
    """
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


#
# Warnings
#

class DataLadWarning(Warning):
    pass


# We have an exception OutdatedExternalDependency, but it is intended for
# an instance being raised.  `warnings` module requires a class to be provided
# as a category, so here is a dedicated Warning class
class OutdatedExternalDependencyWarning(DataLadWarning):
    """Warning "category" to use to report about outdated"""
    pass
