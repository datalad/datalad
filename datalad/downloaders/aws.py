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

import boto  # TODO should be moved into the class for lazy load
import re
import os
from os.path import exists, join as opj, isdir

from ..utils import assure_list_from_str, assure_dict_from_str

from ..ui import ui
from ..utils import auto_repr
from ..support.network import get_url_filename
from ..support.cookies import cookies_db

from .base import Authenticator
from .base import BaseDownloader
from .base import DownloadError, AccessDeniedError

from logging import getLogger
lgr = getLogger('datalad.http')

__docformat__ = 'restructuredtext'

@auto_repr
class S3Authenticator(Authenticator):
    """Authenticator for S3 AWS
    """

    #def authenticate(self, url, credential, session, update=False):
    def authenticate(self, bucket_name, credential):
        lgr.debug("S3 session: Authenticating into session for %s" % url)
        post_url = self.url if self.url else url
        credentials = credential()

        response = self._post_credential(credentials, post_url, session)

        err_prefix = "Authentication to %s failed: " % post_url
        check_response_status(response, err_prefix)

        response_text = response.text
        self.check_for_auth_failure(response_text, err_prefix)

        if self.success_re:
            # the one which must be used to verify success
            # verify that we actually logged in
            for success_re in self.success_re:
                if not re.search(success_re, response_text):
                    raise AccessDeniedError(
                        err_prefix + " returned output did not match 'success' regular expression %s" % success_re
                    )

        return response

    def _post_credential(self, credentials, post_url, session):
        raise NotImplementedError("Must be implemented in subclass")

    def check_for_auth_failure(self, content, err_prefix=""):
        if self.failure_re:
            # verify that we actually logged in
            for failure_re in self.failure_re:
                if re.search(failure_re, content):
                    raise AccessDeniedError(
                        err_prefix + "returned output which matches regular expression %s" % failure_re
                    )


@auto_repr
class HTTPAuthAuthenticator(HTTPBaseAuthenticator):
    """Authenticate by opening a session via POSTing authentication data via HTTP
    """

    def __init__(self, **kwargs):
        """

        Example specification in the .ini config file
        [provider:hcp-db]
        ...
        credential = hcp-db ; is not given to authenticator as is
        authentication_type = http_auth
        http_auth_url = .... TODO

        Parameters
        ----------
        **kwargs : dict, optional
          Passed to super class HTTPBaseAuthenticator
        """
        # so we have __init__ solely for a custom docstring
        super(HTTPAuthAuthenticator, self).__init__(**kwargs)

    def _post_credential(self, credentials, post_url, session):
        response = session.post(post_url, data={}, auth=(credentials['user'], credentials['password']))
        return response


@auto_repr
class HTTPDownloader(BaseDownloader):
    """A stateful downloader to maintain a session to the website
    """

    def __init__(self, credential=None, authenticator=None):
        """

        Parameters
        ----------
        TODO
        """
        self.credential = credential
        self.authenticator = authenticator

        if self.authenticator:
            if not self.credential:
                raise ValueError(
                    "Both authenticator and credentials must be provided."
                    " Got only authenticator %s" % repr(authenticator))

        self._session = None

    def _establish_session(self, url, allow_old=True):
        """

        Parameters
        ----------
        allow_old: bool, optional
          If a Downloader allows for persistent sessions by some means -- flag
          instructs either to use previous session, or establish a new one

        Returns
        -------
        bool
          To state if old instance of a session/authentication was used
        """
        if allow_old:
            if self._session:
                lgr.debug("http session: Reusing previous")
                return True  # we used old
            elif url in cookies_db:
                lgr.debug("http session: Creating new with old cookies")
                self._session = requests.Session()
                # not sure what happens if cookie is expired (need check to that or exception will prolly get thrown)
                cookie_dict = cookies_db[url]
                self._session.cookies = requests.utils.cookiejar_from_dict(cookie_dict)
                return True

        lgr.debug("http session: Creating brand new session")
        self._session = requests.Session()
        if self.authenticator:
            self.authenticator.authenticate(url, self.credential, self._session)

        return False


    def _download(self, url, path=None, overwrite=False):
        """

        Parameters
        ----------
        url: str
          URL to download
        path: str, optional
          Path to file where to store the downloaded content.  If None, downloaded
          content provided back in the return value (not decoded???)

        Returns
        -------
        None or bytes

        """

        response = self._session.get(url, stream=True)
        check_response_status(response)

        headers = response.headers

        #### Specific to download
        # Consult about filename
        if path:
            if isdir(path):
                # provided path is a directory under which to save
                filename = get_url_filename(url, headers=headers)
                filepath = opj(path, filename)
            else:
                filepath = path
        else:
            filepath = get_url_filename(url, headers=headers)

        if exists(filepath) and not overwrite:
            raise DownloadError("File %s already exists" % filepath)

        # FETCH CONTENT
        # TODO: pbar = ui.get_progressbar(size=response.headers['size'])
        # TODO: logic to fetch into a nearby temp file, move into target
        #     reason: detect aborted downloads etc
        try:
            temp_filepath = self._get_temp_download_filename(filepath)
            if exists(temp_filepath):
                # eventually we might want to continue the download
                lgr.warning(
                    "Temporary file %s from the previous download was found. "
                    "It will be overriden" % temp_filepath)
                # TODO.  also logic below would clean it up atm

            target_size = int(headers.get('Content-Length', '0').strip()) or None
            with open(temp_filepath, 'wb') as f:
                # TODO: url might be a bit too long for the beast.
                # Consider to improve to make it animated as well, or shorten here
                pbar = ui.get_progressbar(label=url, fill_text=filepath, maxval=target_size)
                total = 0
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        total += len(chunk)
                        f.write(chunk)
                        pbar.update(total)
                        # TEMP
                        # see https://github.com/niltonvolpato/python-progressbar/pull/44
                        ui.out.flush()
                pbar.finish()
            downloaded_size = os.stat(temp_filepath).st_size

            if (headers.get('Content-type', "") or headers.get('Content-Type', "")).startswith('text/html') \
                    and downloaded_size < 10000 \
                    and self.authenticator:  # and self.authenticator.html_form_failure_re: # TODO: use information in authenticator
                with open(temp_filepath) as f:
                    self.authenticator.check_for_auth_failure(
                        f.read(), "Download of file %s has failed: " % filepath)

            if target_size and target_size != downloaded_size:
                lgr.error("Downloaded file size %d differs from originally announced %d",
                          downloaded_size, target_size)

            # place successfully downloaded over the filepath
            os.rename(temp_filepath, filepath)
        except AccessDeniedError as e:
            raise
        except Exception as e:
            lgr.error("Failed to download {url} into {filepath}: {e}".format(
                **locals()
            ))
            raise DownloadError  # for now
        finally:
            if exists(temp_filepath):
                # clean up
                lgr.debug("Removing a temporary download %s", temp_filepath)
                os.unlink(temp_filepath)


        # TODO: adjust ctime/mtime according to headers
        # TODO: not hardcoded size, and probably we should check header

        return filepath

    def _check(self, url):
        raise NotImplementedError("check is not yet implemented")
