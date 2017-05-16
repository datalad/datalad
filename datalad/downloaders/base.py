# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to stuff (html, data files) via HTTP and HTTPS

"""

__docformat__ = 'restructuredtext'

import msgpack
import os
import time

from abc import ABCMeta, abstractmethod
from os.path import exists, join as opj, isdir
from six import PY2
from six import binary_type, PY3
from six import add_metaclass


from .. import cfg
from ..ui import ui
from ..utils import auto_repr
from ..dochelpers import exc_str
from .credentials import CREDENTIAL_TYPES

from logging import getLogger
lgr = getLogger('datalad.downloaders')


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
@add_metaclass(ABCMeta)
class BaseDownloader(object):
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

        if authenticator:
            if not credential:
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
        needs_authentication = authenticator and authenticator.requires_authentication

        attempt, incomplete_attempt = 0, 0
        while True:
            attempt += 1
            if attempt > 20:
                # are we stuck in a loop somehow? I think logic doesn't allow this atm
                raise RuntimeError("Got to the %d'th iteration while trying to download %s" % (attempt, url))

            try:
                used_old_session = False
                access_denied = False
                used_old_session = self._establish_session(url, allow_old=allow_old_session)
                if not allow_old_session:
                    assert(not used_old_session)
                lgr.log(5, "Calling out into %s for %s" % (method, url))
                result = method(url, **kwargs)
                # assume success if no puke etc
                break
            except AccessDeniedError as e:
                lgr.debug("Access was denied: %s", exc_str(e))
                access_denied = True
            except IncompleteDownloadError as e:
                incomplete_attempt += 1
                if incomplete_attempt > 5:
                    # give up
                    raise
                lgr.debug("Failed to download fully, will try again: %s", exc_str(e))
                # TODO: may be fail ealier than after 20 attempts in such a case?
            except DownloadError:
                # TODO Handle some known ones, possibly allow for a few retries, otherwise just let it go!
                raise

            if access_denied:  # moved logic outside of except for clarity
                if needs_authentication:
                    # so we knew it needs authentication
                    if used_old_session:
                        # Let's try with fresh ones
                        allow_old_session = False
                        continue
                    else:
                        # we did use new cookies, we knew that authentication is needed
                        # but still failed. So possible cases:
                        #  1. authentication credentials changed/were revoked
                        #     - allow user to re-enter credentials
                        #  2. authentication mechanisms changed
                        #     - we can't do anything here about that
                        #  3. bug in out code which would render authentication/cookie handling
                        #     ineffective
                        #     - not sure what to do about it
                        if ui.yesno(
                                title="Authentication to access {url} has failed".format(url=url),
                                text="Do you want to enter other credentials in case they were updated?"):
                            self.credential.enter_new()
                            allow_old_session = False
                            continue
                        else:
                            raise DownloadError("Failed to download from %s given available credentials" % url)
                else:  # None or False
                    if needs_authentication is False:
                        # those urls must or should NOT require authentication but we got denied
                        raise DownloadError("Failed to download from %s, which must be available without "
                                            "authentication but access was denied" % url)
                    else:
                        assert(needs_authentication is None)
                        # So we didn't know if authentication necessary, and it seems to be necessary, so
                        # Let's ask the user to setup authentication mechanism for this website
                        raise AccessDeniedError(
                            "Access to %s was denied but we don't know about this data provider. "
                            "You would need to configure data provider authentication using TODO " % url)

        return result

    @staticmethod
    def _get_temp_download_filename(filepath):
        """Given a filepath, return the one to use as temp file during download
        """
        # TODO: might better reside somewhere under .datalad/tmp or .git/datalad/tmp
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
                with open(file_) as fp:
                    content = fp.read(self._DOWNLOAD_SIZE_TO_VERIFY_AUTH)
            else:
                assert(content is not None)

            self.authenticator.check_for_auth_failure(
                content, "Download of the url %s has failed: " % url)

        if target_size and target_size != downloaded_size:
            raise (IncompleteDownloadError if target_size > downloaded_size else UnaccountedDownloadError)(
                "Downloaded size %d differs from originally announced %d" % (downloaded_size, target_size))

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
            if isdir(path):
                # provided path is a directory under which to save
                filename = downloader_session.filename
                filepath = opj(path, filename)
            else:
                filepath = path
        else:
            filepath = downloader_session.filename

        existed = exists(filepath)
        if existed and not overwrite:
            raise DownloadError("File %s already exists" % filepath)

        # FETCH CONTENT
        # TODO: pbar = ui.get_progressbar(size=response.headers['size'])
        try:
            temp_filepath = self._get_temp_download_filename(filepath)
            if exists(temp_filepath):
                # eventually we might want to continue the download
                lgr.warning(
                    "Temporary file %s from the previous download was found. "
                    "It will be overriden" % temp_filepath)
                # TODO.  also logic below would clean it up atm

            with open(temp_filepath, 'wb') as fp:
                # TODO: url might be a bit too long for the beast.
                # Consider to improve to make it animated as well, or shorten here
                pbar = ui.get_progressbar(label=url, fill_text=filepath, total=target_size)
                t0 = time.time()
                downloader_session.download(fp, pbar, size=size)
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
            os.rename(temp_filepath, filepath)

            if stats:
                stats.downloaded += 1
                stats.overwritten += int(existed)
                stats.downloaded_size += downloaded_size
                stats.downloaded_time += downloaded_time
        except (AccessDeniedError, IncompleteDownloadError) as e:
            raise
        except Exception as e:
            e_str = exc_str(e, limit=5)
            lgr.error("Failed to download {url} into {filepath}: {e_str}".format(
                **locals()
            ))
            raise DownloadError(exc_str(e))  # for now
        finally:
            if exists(temp_filepath):
                # clean up
                lgr.debug("Removing a temporary download %s", temp_filepath)
                os.unlink(temp_filepath)

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
            if PY2:
                import anydbm as dbm
            else:
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

    def _fetch(self, url, cache=None, size=None, allow_redirects=True):
        """Fetch content from a url into a file.

        Very similar to _download but lacks any "file" management and decodes
        content

        Parameters
        ----------
        url: str
          URL to download
        cache: bool, optional
          If None, config is consulted either results should be cached.
          Cache is operating based on url, so no verification of any kind
          is carried out

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
                    lgr.warning("Failed to unpack loaded from cache for %s: %s",
                                url, exc_str(exc))

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
            if PY3 and isinstance(content, binary_type):
                content = content.decode()
            # downloaded_size = os.stat(temp_filepath).st_size

            self._verify_download(url, downloaded_size, target_size, None, content=content)

        except (AccessDeniedError, IncompleteDownloadError) as e:
            raise
        except Exception as e:
            e_str = exc_str(e, limit=5)
            lgr.error("Failed to fetch {url}: {e_str}".format(**locals()))
            raise DownloadError(exc_str(e, limit=8))  # for now

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
        lgr.info("Fetching %r", url)
        # Do not return headers, just content
        out = self.access(self._fetch, url, **kwargs)
        # import pdb; pdb.set_trace()
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

        _, headers = self._fetch(url, cache=False, size=download_size)

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


# Exceptions.  might migrate elsewhere
# MIH: Completely non-obvious why this is here
from ..support.exceptions import *


#
# Authenticators    XXX might go into authenticators.py
#

class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """
    requires_authentication = True
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
