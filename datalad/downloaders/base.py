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

from abc import ABCMeta, abstractmethod, abstractproperty
from os.path import exists, join as opj, isdir
from six import string_types, PY2


from .. import cfg
from ..ui import ui
from ..utils import auto_repr
from ..dochelpers import exc_str
from ..dochelpers import borrowkwargs

from logging import getLogger
lgr = getLogger('datalad.downloaders')

@auto_repr
class BaseDownloader(object):
    """Base class for the downloaders"""

    _DEFAULT_AUTHENTICATOR = None
    _DOWNLOAD_SIZE_TO_VERIFY_AUTH = 10000

    __metaclass__ = ABCMeta

    def __init__(self, credential=None, authenticator=None):
        """

        Parameters
        ----------
        credential: Credential, optional
          Provides necessary credential fields to be used by authenticator
        authenticator: Authenticator, optional
          Authenticator to use for authentication.
        """
        self.credential = credential
        if not authenticator and self._DEFAULT_AUTHENTICATOR:
            authenticator = self._DEFAULT_AUTHENTICATOR()

        if authenticator:
            if not credential:
                raise ValueError(
                    "Both authenticator and credentials must be provided."
                    " Got only authenticator %s" % repr(authenticator))

        self.authenticator = authenticator
        self._cache = None  # for fetches, not downloads


    def _access(self, method, url, allow_old_session=True, **kwargs):
        """Fetch content as pointed by the URL optionally into a file

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
    def _get_download_details(self, url):
        """

        Parameters
        ----------
        url : str

        Returns
        -------
        downloader_into_fp: callable
           Which takes two parameters: file, pbar
        target_size: int or None (if uknown)
        url_filename: str or None
           Filename as decided from the url
        headers : dict or None
        """
        raise NotImplementedError("Must be implemented in the subclass")

    def _verify_download(self, url, downloaded_size, target_size, file_=None, content=None):
        """Verify that download finished correctly"""

        if (self.authenticator and downloaded_size < self._DOWNLOAD_SIZE_TO_VERIFY_AUTH) and \
            hasattr(self.authenticator, 'failure_re') and self.authenticator.failure_re:
            assert hasattr(self.authenticator, 'check_for_auth_failure'), \
                "%s has failure_re defined but no check_for_auth_failure" \
                % self.authenticator

            if file_:
                with open(file_) as fp:
                    content = fp.read()
            else:
                assert(content is not None)

            self.authenticator.check_for_auth_failure(
                content, "Download of the url %s has failed: " % url)

        if target_size and target_size != downloaded_size:
            raise IncompleteDownloadError("Downloaded size %d differs from originally announced %d"
                                          % (downloaded_size, target_size))


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

        downloader, target_size, url_filename, headers = self._get_download_details(url)
        status = self.get_status_from_headers(headers)

        if size is not None:
            target_size = min(target_size, size)

        #### Specific to download
        if path:
            if isdir(path):
                # provided path is a directory under which to save
                filename = url_filename
                filepath = opj(path, filename)
            else:
                filepath = path
        else:
            filepath = url_filename

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
                pbar = ui.get_progressbar(label=url, fill_text=filepath, maxval=target_size)
                t0 = time.time()
                downloader(fp, pbar, size=size)
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
        return self._access(self._download, url, path=path, **kwargs)


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
            cache_dir = opj(cfg.dirs.user_cache_dir)
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
        if cache is None:
            cache = cfg.getboolean('crawl', 'cache', False)

        if cache:
            cache_key = msgpack.dumps(url)
            res = self.cache.get(cache_key)
            if res is not None:
                try:
                    return msgpack.loads(res, encoding='utf-8')
                except Exception as exc:
                    lgr.warning("Failed to unpack loaded from cache for %s: %s",
                                url, exc_str(exc))

        downloader, target_size, url_filename, headers = self._get_download_details(url, allow_redirects=allow_redirects)

        if size is not None:
            if size == 0:
                # no download of the content was requested -- just return headers and be done
                return None, headers
            target_size = min(size, target_size)

        # FETCH CONTENT
        try:
            # Consider to improve to make it animated as well, or shorten here
            #pbar = ui.get_progressbar(label=url, fill_text=filepath, maxval=target_size)
            content = downloader(size=size)
            #pbar.finish()
            downloaded_size = len(content)
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
            self.cache[cache_key] = msgpack.dumps((content, dict(headers)))

        return content, headers


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
        out = self._access(self._fetch, url, **kwargs)
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
        return self._access(self._get_status, url, old_status=old_status, **kwargs)


    # TODO: borrow from itself... ?
    # @borrowkwargs(BaseDownloader, 'get_status')
    def _get_status(self, url, old_status=None):

        # the tricky part is only to make sure that we are getting the target URL
        # and not some page saying to login, that is why we need to fetch some content
        # in those cases, and not just check the headers
        download_size = self._DOWNLOAD_SIZE_TO_VERIFY_AUTH \
            if self.authenticator and \
                hasattr(self.authenticator, 'failure_re') and self.authenticator.failure_re \
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

# Exceptions.  might migrate elsewhere

class DownloadError(Exception):
    pass

class IncompleteDownloadError(DownloadError):
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
# Authenticators    XXX might go into authenticators.py
#

class Authenticator(object):
    """Abstract common class for different types of authentication

    Derived classes should get parameterized with options from the config files
    from "provider:" sections
    """
    requires_authentication = True
    # TODO: figure out interface

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

