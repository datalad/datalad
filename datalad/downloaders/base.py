# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to stuff (html, data files) via HTTP and HTTPS

"""

__docformat__ = 'restructuredtext'

import errno
import os
import os.path as op
import shutil
import sys
import time
from abc import (
    ABCMeta,
    abstractmethod,
)
from http.client import IncompleteRead
from logging import getLogger
from os.path import (
    exists,
    isdir,
)
from os.path import join as opj

import msgpack
from humanize import naturalsize

from datalad.downloaders import CREDENTIAL_TYPES

from .. import cfg
from ..support.exceptions import (
    AccessDeniedError,
    AccessFailedError,
    AccessPermissionExpiredError,
    AnonymousAccessDeniedError,
    CapturedException,
    DownloadError,
    IncompleteDownloadError,
    UnaccountedDownloadError,
)
from ..support.locking import (
    InterProcessLock,
    try_lock,
    try_lock_informatively,
)
from ..ui import ui
from ..utils import (
    auto_repr,
    ensure_unicode,
    unlink,
)
from .credentials import CompositeCredential

lgr = getLogger('datalad.downloaders')

def _errnos(*names):
    """Errnos for those of `names` which are known on this platform"""
    return {getattr(errno, name) for name in names if hasattr(errno, name)}


# Errnos of OSErrors which signal a transient problem with the connection
_TRANSIENT_ERRNOS = _errnos(
    'ECONNABORTED', 'ECONNRESET', 'EHOSTUNREACH', 'ENETDOWN', 'ENETRESET',
    'ENETUNREACH', 'EPIPE', 'ETIMEDOUT',
)

# Errnos of OSErrors which signal that there is no room for the content
_OUT_OF_SPACE_ERRNOS = _errnos('ENOSPC', 'EDQUOT', 'EFBIG')

# Names of exception classes which signal a transient problem with the
# connection or the transfer.  Matched by name, since they come from 3rd party
# libraries used by the individual downloaders (requests/urllib3 for http,
# botocore for S3), which this module has no business importing.
_TRANSIENT_EXCEPTION_NAMES = {
    # requests
    'ChunkedEncodingError',
    'ConnectionError',
    'ConnectTimeout',
    'ReadTimeout',
    'Timeout',
    # urllib3
    'ConnectTimeoutError',
    'NewConnectionError',
    'ProtocolError',
    'ReadTimeoutError',
    # botocore
    'ConnectionClosedError',
    'EndpointConnectionError',
    'IncompleteReadError',
    'ResponseStreamingError',
    # ssl -- only the ones which mean "the peer went away", not e.g. a
    # certificate which will not become valid by trying again
    'SSLEOFError',
    'SSLZeroReturnError',
}


def _iter_exception_chain(exc):
    """Yield `exc` and every exception it was caused by or raised during"""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or (
            None if exc.__suppress_context__ else exc.__context__)


def is_transient_download_error(exc):
    """Whether a failed transfer is worth retrying

    A dropped connection, a reset, or a read timeout say nothing about whether
    the content is obtainable, so downloads failing that way are retried (see
    `BaseDownloader.access`), while e.g. a full disk is not.

    Parameters
    ----------
    exc: BaseException
      Exception to judge.  Its ``__cause__``/``__context__`` chain is
      considered as well, since the libraries used by the downloaders tend to
      wrap the original error a few times over.

    Returns
    -------
    bool
    """
    for e in _iter_exception_chain(exc):
        # ConnectionError covers ConnectionReset/Aborted/Refused and
        # BrokenPipe, TimeoutError also the former socket.timeout
        if isinstance(e, (ConnectionError, TimeoutError, IncompleteRead)):
            return True
        if isinstance(e, OSError) and e.errno in _TRANSIENT_ERRNOS:
            return True
        if type(e).__name__ in _TRANSIENT_EXCEPTION_NAMES:
            return True
    return False


def _is_out_of_space_error(exc):
    """Whether a failed transfer ran out of room to store the content"""
    return any(
        isinstance(e, OSError) and e.errno in _OUT_OF_SPACE_ERRNOS
        for e in _iter_exception_chain(exc)
    )


def _get_free_space(path):
    """Free space (bytes) on the file system `path` resides on, None if unknown
    """
    try:
        return shutil.disk_usage(op.dirname(op.abspath(path))).free
    except OSError as e:
        lgr.debug("Could not determine free space for %s: %s",
                  path, CapturedException(e))
        return None


def _describe_transfer(path, downloaded_size=None, target_size=None):
    """Summarize how far a download got, and how much room was left for it

    Both are reported since the difference between a truncated response and a
    full file system is otherwise not apparent from the failure alone.

    Parameters
    ----------
    path: str or None
      Path the content was being downloaded into.  If None, no information on
      free space is included.
    downloaded_size: int, optional
      Bytes received so far.  Determined from `path` if not given.
    target_size: int, optional
      Total size of the download, if it was announced.

    Returns
    -------
    str
      Human readable summary.  Aspects which could not be determined are
      omitted.
    """
    if downloaded_size is None and path:
        try:
            downloaded_size = os.stat(path).st_size
        except OSError as e:
            lgr.debug("Could not stat %s to report on the transfer: %s",
                      path, CapturedException(e))
    parts = []
    if downloaded_size is not None:
        parts.append(
            "%s out of %s downloaded"
            % (naturalsize(downloaded_size),
               naturalsize(target_size) if target_size else "an unknown total"))
    free_space = _get_free_space(path) if path else None
    if free_space is not None:
        parts.append("%s free on the file system of %s"
                     % (naturalsize(free_space), path))
    return ', '.join(parts) if parts else "no further information available"


# TODO: remove headers, HTTP specific
@auto_repr
class DownloaderSession(object):
    """Base class to encapsulate information and possibly a session to download the content

    The idea is that corresponding downloader provides all necessary
    information and if necessary some kind of session to facilitate
    .download method
    """

    def __init__(self, size=None, filename=None, url=None, headers=None):
        self.size = size
        self.filename = filename
        self.headers = headers
        self.url = url

    def download(self, f=None, pbar=None, size=None):
        raise NotImplementedError("must be implemented in subclases")

        # TODO: get_status ?


@auto_repr
class BaseDownloader(object, metaclass=ABCMeta):
    """Base class for the downloaders"""

    _DEFAULT_AUTHENTICATOR = None
    _DOWNLOAD_SIZE_TO_VERIFY_AUTH = 10000

    def __init__(self, credential=None, authenticator=None):
        """

        Parameters
        ----------
        credential: Credential, optional
          Provides necessary credential fields to be used by authenticator
        authenticator: Authenticator, optional
          Authenticator to use for authentication.
        """
        if not authenticator and self._DEFAULT_AUTHENTICATOR:
            authenticator = self._DEFAULT_AUTHENTICATOR()

        if authenticator and authenticator.requires_authentication:
            if not credential and not authenticator.allows_anonymous:
                msg = "Both authenticator and credentials must be provided." \
                      " Got only authenticator %s" % repr(authenticator)
                if ui.yesno(
                    title=msg,
                    text="Do you want to enter %s credentials to be used?" % authenticator.DEFAULT_CREDENTIAL_TYPE
                ):
                    credential = CREDENTIAL_TYPES[authenticator.DEFAULT_CREDENTIAL_TYPE](
                        "session-only-for-%s" % id(authenticator))
                    credential.enter_new()
                    # TODO: give an option to store those credentials, and generate a basic provider
                    # record?
                else:
                    raise ValueError(msg)
        self.credential = credential
        self.authenticator = authenticator
        self._cache = None  # for fetches, not downloads

    def access(self, method, url, allow_old_session=True, **kwargs):
        """Generic decorator to manage access to the URL via some method

        Parameters
        ----------
        method : callable
          A callable, usually a method of the same class, which we decorate
          with access handling, and pass url as the first argument
        url : string
          URL to access
        *args, **kwargs
          Passed into the method call

        Returns
        -------
        None or bytes
        """
        # TODO: possibly wrap this logic outside within a decorator, which
        # would just call the corresponding method
        authenticator = self.authenticator
        if authenticator:
            needs_authentication = authenticator.requires_authentication
        else:
            needs_authentication = self.credential

        # TODO: not sure yet, where is/are the right spot(s) to pass the URL:
        if hasattr(self.credential, 'set_context'):
            lgr.debug("set credential context as %s", url)
            self.credential.set_context(auth_url=url)

        retries = cfg.obtain('datalad.downloaders.retry')
        attempt, incomplete_attempt, server_error_attempt = 0, 0, 0
        result = None
        credential_was_refreshed = False
        # a ceiling for the whole loop, to not get stuck should the logic below
        # ever fail to converge -- generous enough to accommodate `retries`
        # retries of each individually retried failure mode
        max_attempts = max(20, 4 * retries)
        while True:
            attempt += 1
            if attempt > max_attempts:
                # are we stuck in a loop somehow? I think logic doesn't allow this atm
                raise RuntimeError("Got to the %d'th iteration while trying to download %s" % (attempt, url))
            exc_info = None
            msg_types = ''
            supported_auth_types = []
            used_old_session = False
            # Lock must be instantiated here, within each thread to avoid problems
            # when used in our parallel.ProducerConsumer
            # see https://github.com/datalad/datalad/issues/6483
            interp_lock = InterProcessLock(
                op.join(cfg.obtain('datalad.locations.locks'),
                        'downloader-auth.lck')
            )

            try:
                # Try to lock since it might desire to ask for credentials, but still allow to time out at 5 minutes
                # while providing informative message on what other process might be holding it.
                with try_lock_informatively(interp_lock, purpose="establish download session", proceed_unlocked=False):
                    used_old_session = self._establish_session(url, allow_old=allow_old_session)
                if not allow_old_session:
                    assert(not used_old_session)
                lgr.log(5, "Calling out into %s for %s", method, url)
                result = method(url, **kwargs)
                # assume success if no puke etc
                break
            except AccessDeniedError as e:
                ce = CapturedException(e)
                if hasattr(e, 'status') and e.status == 429:
                    # Too many requests.
                    # We can retry by continuing the loop.
                    time.sleep(0.5*(attempt**1.2))
                    continue

                if isinstance(e, AnonymousAccessDeniedError):
                    access_denied = "Anonymous access"
                else:
                    access_denied = "Access"
                lgr.debug("%s was denied: %s", access_denied, ce)
                supported_auth_types = e.supported_types
                exc_info = sys.exc_info()

                if supported_auth_types:
                    msg_types = \
                        " The failure response indicated that following " \
                        "authentication types should be used: %s" % (
                            ', '.join(supported_auth_types))
                # keep inside except https://github.com/datalad/datalad/issues/3621
                # TODO: what if it was anonimous attempt without authentication,
                #     so it is not "requires_authentication" but rather
                #     "supports_authentication"?  We should not report below in
                # _get_new_credential that authentication has failed then since there
                # were no authentication.  We might need a custom exception to
                # be caught above about that

                allow_old_session = False  # we will either raise or auth
                # in case of parallel downloaders, one would succeed to get the
                # lock, ask user if necessary and other processes would just wait
                # got it to return back
                with try_lock(interp_lock) as got_lock:
                    if got_lock:
                        if isinstance(e, AccessPermissionExpiredError) \
                                and not credential_was_refreshed \
                                and self.credential \
                                and isinstance(self.credential, CompositeCredential):
                            lgr.debug("Requesting refresh of the credential (once)")
                            self.credential.refresh()
                            # to avoid a loop of refreshes without giving a chance to
                            # enter a new one, we will allow only a single refresh
                            credential_was_refreshed = True
                        else:
                            self._handle_authentication(url, needs_authentication, e, ce,
                                                        access_denied, msg_types,
                                                        supported_auth_types,
                                                        used_old_session)
                    else:
                        lgr.debug("The lock for downloader authentication was not available.")
                        # We will just wait for the lock to become available,
                        # and redo connect/download attempt
                continue

            except IncompleteDownloadError as e:
                ce = CapturedException(e)
                exc_info = sys.exc_info()
                incomplete_attempt += 1
                if incomplete_attempt > retries:
                    lgr.debug(
                        "Download of %s did not complete in %d attempts, "
                        "giving up", url, incomplete_attempt)
                    raise
                # a partial transfer says nothing about whether the content is
                # obtainable, so back off and start over. Note that there is no
                # resume: the retry re-downloads from the beginning
                self._sleep_before_retry(ce, incomplete_attempt, retries)
            except AccessFailedError as e:
                # Handle retryable server errors (5xx)
                if hasattr(e, 'status') and e.status is not None and 500 <= e.status < 600:
                    ce = CapturedException(e)
                    server_error_attempt += 1
                    if server_error_attempt > retries:
                        lgr.debug(
                            "Access to %s kept failing with a server error in "
                            "%d attempts, giving up", url, server_error_attempt)
                        raise
                    self._sleep_before_retry(ce, server_error_attempt, retries)
                    continue
                # Non-retryable AccessFailedError
                raise
            except DownloadError:
                raise

        return result

    @staticmethod
    def _sleep_before_retry(ce, attempt, retries):
        """Report an imminent retry of a failed access, and back off before it

        Parameters
        ----------
        ce: CapturedException
          The failure.  Its message is expected to identify the URL and to
          describe the failure, so that it can lead the report on its own.
        attempt: int
          Number of the retry which is about to be made (1-based).
        retries: int
          Total number of retries which will be made before giving up.
        """
        # same progression as used for 429 (too many requests) responses
        delay = 0.5 * (attempt ** 1.2)
        lgr.info("%s. Retrying (%d out of %d) in %.1f seconds",
                 ce.message or str(ce), attempt, retries, delay)
        time.sleep(delay)

    def _handle_authentication(self, url, needs_authentication, e, ce,
                               access_denied, msg_types, supported_auth_types,
                               used_old_session):
        if needs_authentication:
            # so we knew it needs authentication
            if not used_old_session:
                # we did use new cookies, we knew that authentication is needed
                # but still failed. So possible cases:
                #  1. authentication credentials changed/were revoked
                #     - allow user to re-enter credentials
                #  2. authentication mechanisms changed
                #     - we can't do anything here about that
                #  3. bug in out code which would render
                #  authentication/cookie handling
                #     ineffective
                #     - not sure what to do about it
                if not ui.is_interactive:
                    lgr.error(
                        "Interface is non interactive, so we are "
                        "reraising: %s", ce)
                    raise e
                self._enter_credentials(
                    url,
                    denied_msg=access_denied,
                    auth_types=supported_auth_types,
                    new_provider=False)
        else:  # None or False
            if needs_authentication is False:
                # those urls must or should NOT require authentication
                # but we got denied
                raise DownloadError(
                    "Failed to download from %s, which must be available"
                    "without authentication but access was denied. "
                    "Adjust your configuration for the provider.%s"
                    % (url, msg_types))
            else:
                # how could be None or any other non-False bool(False)
                assert (needs_authentication is None)
                # So we didn't know if authentication necessary, and it
                # seems to be necessary, so Let's ask the user to setup
                # authentication mechanism for this website
                if not ui.is_interactive:
                    # no way to prompt, so surface the original failure
                    # instead of dying inside the credentials dialog
                    lgr.error(
                        "Interface is non interactive, so we are "
                        "reraising: %s", ce)
                    raise e
                self._enter_credentials(
                    url,
                    denied_msg=access_denied,
                    auth_types=supported_auth_types,
                    new_provider=True)

    def _setup_new_provider(self, title, url, auth_types=None):
        # Full new provider (TODO move into Providers?)
        from .providers import Providers
        providers = Providers.from_config_files()
        while True:
            provider = providers.enter_new(url, auth_types=auth_types)
            if not provider:
                if ui.yesno(
                    title="Re-enter provider?",
                    text="You haven't entered or saved provider, would you like to retry?",
                    default=True
                ):
                    continue
            break
        return provider

    def _enter_credentials(
            self, url, denied_msg,
            auth_types=[], new_provider=True):
        """Use when authentication fails to set new credentials for url

        Raises
        ------
        DownloadError
          If no known credentials type or user refuses to update
        """
        title = f"{denied_msg} to {url} has failed."

        if new_provider:
            # No credential was known, we need to create an
            # appropriate one
            if not ui.yesno(
                    title=title,
                    text="Would you like to setup a new provider configuration"
                         " to access url?",
                    default=True
            ):
                assert not self.authenticator, "bug: incorrect assumption"
                raise DownloadError(
                    title +
                    " No authenticator is known, cannot set any credential")
            else:
                provider = self._setup_new_provider(
                    title, url, auth_types=auth_types)
                self.authenticator = provider.authenticator
                self.credential = provider.credential
                if not (self.credential and self.credential.is_known):
                    # TODO: or should we ask to re-enter?
                    self.credential.enter_new()
        else:
            action_msg = "enter other credentials in case they were updated?"

            if self.credential and ui.yesno(
                    title=title,
                    text="Do you want to %s" % action_msg):
                self.credential.enter_new()
            else:
                raise DownloadError(
                    "Failed to download from %s given available credentials"
                    % url)

        lgr.debug("set credential context as %s", url)
        self.credential.set_context(auth_url=url)

    @staticmethod
    def _warn_if_not_enough_space(url, path, target_size):
        """Warn if `path` cannot possibly hold `target_size` bytes

        Running out of space manifests as a download which breaks off at a
        different offset every time, which is easily mistaken for a flaky
        server (https://github.com/ReproNim/containers/issues/169).
        """
        if not target_size:
            return
        free_space = _get_free_space(path)
        if free_space is not None and free_space < target_size:
            lgr.warning(
                "Downloading %s requires %s, but only %s is free on the file "
                "system of %s -- the download is likely to fail",
                url, naturalsize(target_size), naturalsize(free_space), path)

    @staticmethod
    def _get_transfer_error(exc, url, temp_filepath, fp=None, target_size=None):
        """Return the `DownloadError` to raise for a failure during a transfer

        Transient connection problems are reported as `IncompleteDownloadError`
        so that `access()` retries them, everything else as a plain
        `DownloadError`.  Either way the message states how far the download
        got and how much room was left for it, to tell a truncated response
        apart from a file system which ran out of space.

        Parameters
        ----------
        exc: BaseException
          The failure.  It is not rendered into the message -- it is to be
          attached as the ``__cause__`` of the returned exception instead.
        url: str
          URL being downloaded.
        temp_filepath: str
          Path the content was being downloaded into.
        fp: file-like, optional
          Still open handle of `temp_filepath`, to determine how much was
          written without having to flush it first.
        target_size: int, optional
          Total size of the download, if it was announced.

        Returns
        -------
        DownloadError
        """
        downloaded_size = None
        if fp is not None:
            try:
                downloaded_size = fp.tell()
            except (OSError, ValueError) as e:
                lgr.debug("Could not determine how much of %s was written: %s",
                          temp_filepath, CapturedException(e))
        transfer = _describe_transfer(temp_filepath, downloaded_size,
                                      target_size)
        if _is_out_of_space_error(exc):
            return DownloadError(
                "Ran out of space while downloading %s into %s (%s)"
                % (url, temp_filepath, transfer))
        if is_transient_download_error(exc):
            return IncompleteDownloadError(
                "Transfer of %s was interrupted (%s)" % (url, transfer))
        return DownloadError(
            "Failed to download %s into %s (%s)"
            % (url, temp_filepath, transfer))

    @staticmethod
    def _get_temp_download_filename(filepath):
        """Given a filepath, return the one to use as temp file during download
        """
        # TODO: might better reside somewhere under .datalad/tmp or
        # .git/datalad/tmp
        return filepath + ".datalad-download-temp"

    @abstractmethod
    def get_downloader_session(self, url):
        """

        Parameters
        ----------
        url : str

        Returns
        -------
        downloader_into_fp: callable
           Which takes two parameters: file, pbar
        target_size: int or None (if unknown)
        url: str
           Possibly redirected url
        url_filename: str or None
           Filename as decided from the (redirected) url
        headers : dict or None
        """
        raise NotImplementedError("Must be implemented in the subclass")

    def _verify_download(self, url, downloaded_size, target_size, file_=None, content=None):
        """Verify that download finished correctly"""

        if (self.authenticator
                and downloaded_size < self._DOWNLOAD_SIZE_TO_VERIFY_AUTH) \
                and hasattr(self.authenticator, 'failure_re') \
                and self.authenticator.failure_re:
            assert hasattr(self.authenticator, 'check_for_auth_failure'), \
                "%s has failure_re defined but no check_for_auth_failure" \
                % self.authenticator

            if file_:
                # just read bytes and pass to check_for_auth_failure which
                # will then encode regex into bytes (assuming utf-8 though)
                with open(file_, 'rb') as fp:
                    content = fp.read(self._DOWNLOAD_SIZE_TO_VERIFY_AUTH)
            else:
                assert(content is not None)

            self.authenticator.check_for_auth_failure(
                content, "Download of the url %s has failed: " % url)

        if target_size and target_size != downloaded_size:
            raise (IncompleteDownloadError if target_size > downloaded_size else UnaccountedDownloadError)(
                "Downloaded size %d differs from originally announced %d (%s)"
                % (downloaded_size, target_size,
                   _describe_transfer(file_, downloaded_size, target_size)))

    def _download(self, url, path=None, overwrite=False, size=None, stats=None):
        """Download content into a file

        Parameters
        ----------
        url: str
          URL to download
        path: str, optional
          Path to file where to store the downloaded content.  If None,
          filename deduced from the url and saved in curdir
        size: int, optional
          Limit in size to be downloaded

        Returns
        -------
        None or string
          Returns downloaded filename

        """

        downloader_session = self.get_downloader_session(url)
        status = self.get_status_from_headers(downloader_session.headers)

        target_size = downloader_session.size
        if size is not None:
            target_size = min(target_size, size)

        #### Specific to download
        if path:
            download_dir = op.dirname(path)
            if download_dir:
                os.makedirs(download_dir, exist_ok=True)
            if isdir(path):
                # provided path is a directory under which to save
                filename = downloader_session.filename
                if not filename:
                    raise DownloadError(
                        "File name could not be determined from {}".format(url))
                filepath = opj(path, filename)
            else:
                filepath = path
        else:
            filepath = downloader_session.filename

        existed = op.lexists(filepath)
        if existed and not overwrite:
            raise DownloadError("Path %s already exists" % filepath)

        # FETCH CONTENT
        # TODO: pbar = ui.get_progressbar(size=response.headers['size'])
        temp_filepath = self._get_temp_download_filename(filepath)
        self._warn_if_not_enough_space(url, temp_filepath, target_size)
        try:
            if exists(temp_filepath):
                # eventually we might want to continue the download
                lgr.warning(
                    "Temporary file %s from the previous download was found. "
                    "It will be overridden" % temp_filepath)
                # TODO.  also logic below would clean it up atm

            with open(temp_filepath, 'wb') as fp:
                # TODO: url might be a bit too long for the beast.
                # Consider to improve to make it animated as well, or shorten here
                pbar = ui.get_progressbar(label=url, fill_text=filepath, total=target_size)
                t0 = time.time()
                try:
                    downloader_session.download(fp, pbar, size=size)
                except Exception as e:
                    raise self._get_transfer_error(
                        e, url, temp_filepath, fp=fp,
                        target_size=target_size) from e
                downloaded_time = time.time() - t0
                pbar.finish()
            downloaded_size = os.stat(temp_filepath).st_size

            # (headers.get('Content-type', "") and headers.get('Content-Type')).startswith('text/html')
            #  and self.authenticator.html_form_failure_re: # TODO: use information in authenticator
            self._verify_download(url, downloaded_size, target_size, temp_filepath)

            # adjust atime/mtime according to headers/status
            if status.mtime:
                lgr.log(5, "Setting mtime for %s to be %s", temp_filepath, status.mtime)
                os.utime(temp_filepath, (time.time(), status.mtime))

            # place successfully downloaded over the filepath
            os.replace(temp_filepath, filepath)

            if stats:
                stats.downloaded += 1
                stats.overwritten += int(existed)
                stats.downloaded_size += downloaded_size
                stats.downloaded_time += downloaded_time
        except DownloadError:
            # already a well described download failure -- reporting it once
            # more here would only duplicate it in the rendering of the chain
            raise
        except Exception as e:
            ce = CapturedException(e)
            lgr.debug("Failed to download %s into %s: %s", url, filepath, ce)
            # deliberately not rendering `e` into the message: it is available
            # as the cause of this exception, and rendering it in both places
            # is what made these reports hard to read
            # (https://github.com/ReproNim/containers/issues/169)
            raise DownloadError(
                "Failed to download %s into %s" % (url, filepath)) from e
        finally:
            if exists(temp_filepath):
                # clean up
                lgr.debug("Removing a temporary download %s", temp_filepath)
                unlink(temp_filepath)

        return filepath

    def download(self, url, path=None, **kwargs):
        """Fetch content as pointed by the URL optionally into a file

        Parameters
        ----------
        url : string
          URL to access
        path : string, optional
          Filename or existing directory to store downloaded content under.
          If not provided -- deduced from the url

        Returns
        -------
        string
          file path
        """
        # TODO: may be move all the path dealing logic here
        # but then it might require sending request anyways for Content-Disposition
        # so probably nah
        lgr.info("Downloading %r into %r", url, path)
        return self.access(self._download, url, path=path, **kwargs)

    @property
    def cache(self):
        if self._cache is None:
            # TODO: move this all logic outside into a dedicated caching beast
            lgr.info("Initializing cache for fetches")
            import dbm

            # Initiate cache.
            # Very rudimentary caching for now, might fail many ways
            cache_dir = cfg.obtain('datalad.locations.cache')
            if not exists(cache_dir):
                os.makedirs(cache_dir)
            cache_path = opj(cache_dir, 'crawl_cache.dbm')
            self._cache = dbm.open(cache_path, 'c')
            import atexit
            atexit.register(self._cache.close)
        return self._cache

    def _fetch(self, url, cache=None, size=None, allow_redirects=True, decode=True):
        """Fetch content from a url into a file.

        Very similar to _download but lacks any "file" management and decodes
        content

        Parameters
        ----------
        url: str
          URL to download
        cache: bool, optional
          If None, config is consulted to determine whether results should be
          cached. Cache is operating based on url, so no verification of any
          kind is carried out

        Returns
        -------
        bytes, dict
          content, headers
        """
        lgr.log(3, "_fetch(%r, cache=%r, size=%r, allow_redirects=%r)",
                url, cache, size, allow_redirects)
        if cache is None:
            cache = cfg.obtain('datalad.crawl.cache', default=False)

        if cache:
            cache_key = msgpack.dumps(url)
            lgr.debug("Loading content for url %s from cache", url)
            res = self.cache.get(cache_key)
            if res is not None:
                try:
                    return msgpack.loads(res, encoding='utf-8')
                except Exception as exc:
                    ce = CapturedException(exc)
                    lgr.warning("Failed to unpack loaded from cache for %s: %s",
                                url, ce)

        downloader_session = self.get_downloader_session(url, allow_redirects=allow_redirects)

        target_size = downloader_session.size
        if size is not None:
            if size == 0:
                # no download of the content was requested -- just return headers and be done
                return None, downloader_session.headers
            target_size = min(size, target_size)

        # FETCH CONTENT
        try:
            # Consider to improve to make it animated as well, or shorten here
            #pbar = ui.get_progressbar(label=url, fill_text=filepath, total=target_size)
            content = downloader_session.download(size=size)
            #pbar.finish()
            downloaded_size = len(content)

            # now that we know size based on encoded content, let's decode into string type
            if isinstance(content, bytes) and decode:
                content = ensure_unicode(content)
            # downloaded_size = os.stat(temp_filepath).st_size

            self._verify_download(url, downloaded_size, target_size, None, content=content)

        except DownloadError:
            # already a well described download failure -- reporting it once
            # more here would only duplicate it in the rendering of the chain
            raise
        except Exception as e:
            ce = CapturedException(e)
            lgr.debug("Failed to fetch %s: %s", url, ce)
            # as in _download(): `e` is attached as the cause instead of being
            # rendered into the message a second time
            if is_transient_download_error(e):
                raise IncompleteDownloadError(
                    "Transfer of %s was interrupted" % url) from e
            raise DownloadError("Failed to fetch %s" % url) from e

        if cache:
            # apparently requests' CaseInsensitiveDict is not serialazable
            # TODO:  may be we should reuse that type everywhere, to avoid
            # out own handling for case-handling
            self.cache[cache_key] = msgpack.dumps((content, dict(downloader_session.headers)))

        return content, downloader_session.headers

    def fetch(self, url, **kwargs):
        """Fetch and return content (not decoded) as pointed by the URL

        Parameters
        ----------
        url : string
          URL to access

        Returns
        -------
        bytes
          content
        """
        lgr.debug("Fetching %r", url)
        # Do not return headers, just content
        out = self.access(self._fetch, url, **kwargs)
        return out[0]

    def get_status(self, url, old_status=None, **kwargs):
        """Return status of the url as a dict, None if N/A

        Parameters
        ----------
        url : string
          URL to access
        old_status : FileStatus, optional
          Previous status record.  If provided, might serve as a shortcut
          to assess if status has changed, and if not -- return the same
          record

        Returns
        -------
        dict
          dict-like beast depicting the status of the URL if accessible.
          Returned value should be sufficient to tell if the URL content
          has changed by comparing to previously obtained value.
          If URL is not reachable, None would be returned
        """
        return self.access(self._get_status, url, old_status=old_status, **kwargs)

    # TODO: borrow from itself... ?
    # @borrowkwargs(BaseDownloader, 'get_status')
    def _get_status(self, url, old_status=None):

        # the tricky part is only to make sure that we are getting the target URL
        # and not some page saying to login, that is why we need to fetch some content
        # in those cases, and not just check the headers
        download_size = self._DOWNLOAD_SIZE_TO_VERIFY_AUTH \
            if self.authenticator \
            and hasattr(self.authenticator, 'failure_re') \
            and self.authenticator.failure_re \
            else 0

        _, headers = self._fetch(url, cache=False, size=download_size, decode=False)

        # extract from headers information to depict the status of the url
        status = self.get_status_from_headers(headers)

        if old_status is not None:
            raise NotImplementedError("Do not know yet how to deal with old_status. TODO")

        return status

    @classmethod
    @abstractmethod
    def get_status_from_headers(cls, headers):
        raise NotImplementedError("Implement in the subclass: %s" % cls)

    def get_target_url(self, url):
        """Return url after possible redirections

        Parameters
        ----------
        url : string
          URL to access

        Returns
        -------
        str
        """
        return self.access(self._get_target_url, url)

    def _get_target_url(self, url):
        return self.get_downloader_session(url).url


#
# Authenticators    XXX might go into authenticators.py
#

class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """
    requires_authentication = True
    allows_anonymous = False
    # TODO: figure out interface

    DEFAULT_CREDENTIAL_TYPE = 'user_password'

    def authenticate(self, *args, **kwargs):
        """Derived classes will provide specific implementation
        """
        if self.requires_authentication:
            raise NotImplementedError("Authentication for %s not yet implemented" % self.__class__)


class NotImplementedAuthenticator(Authenticator):
    pass


class NoneAuthenticator(Authenticator):
    """Whenever no authentication is necessary and that is stated explicitly"""
    requires_authentication = False
    pass
