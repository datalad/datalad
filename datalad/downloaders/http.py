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

import re
import requests
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


def check_response_status(response, err_prefix=""):
    """Check if response's status_code signals problem with authentication etc

    ATM succeeds only if response code was 200
    """
    if not err_prefix:
        err_prefix = "Access to %s has failed: " % response.url
    if response.status_code in {404}:
        # It could have been that form_url is wrong, so let's just say that
        # TODO: actually may be that is where we could use tagid and actually determine the form submission url
        raise DownloadError(err_prefix + "not found")
    elif 400 <= response.status_code < 500:
        raise AccessDeniedError(err_prefix + "status code %d" % response.status_code)
    elif response.status_code in {200}:
        pass
    else:
        raise AccessDeniedError(err_prefix + "status code %d" % response.status_code)


@auto_repr
class HTTPBaseAuthenticator(Authenticator):
    """Base class for html_form and http_auth authenticators
    """
    def __init__(self, url=None, failure_re=None, success_re=None, **kwargs):
        """
        Parameters
        ----------
        url : str, optional
          URL where to find the form/login to authenticate.  If not provided, an original query url
          which will be provided to the __call__ of the authenticator will be used
        failure_re : str or list of str, optional
        success_re : str or list of str, optional
          Regular expressions to determine either login has failed or succeeded.
          TODO: we might condition when it gets ran
        """
        super(HTTPBaseAuthenticator, self).__init__(**kwargs)
        self.url = url
        self.failure_re = assure_list_from_str(failure_re)
        self.success_re = assure_list_from_str(success_re)


    def authenticate(self, url, credential, session, update=False):
        # we should use specified URL for this authentication first
        lgr.debug("http session: Authenticating into session for %s" % url)
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

        if response.cookies:
            cookies_dict = requests.utils.dict_from_cookiejar(response.cookies)
            if (url in cookies_db) and update:
                cookies_db[url].update(cookies_dict)
            else:
                cookies_db[url] = cookies_dict
            # assign cookies for this session
            session.cookies = response.cookies
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
class HTMLFormAuthenticator(HTTPBaseAuthenticator):
    """Authenticate by opening a session via POSTing to HTML form
    """

    def __init__(self, fields, tagid=None, **kwargs):
        """

        Example specification in the .ini config file
        [provider:crcns]
        ...
        credential = crcns ; is not given to authenticator as is
        authentication_type = html_form
        # TODO: may be rename into post_url
        html_form_url = https://crcns.org/login_form
        # probably not needed actually since form_url
        # html_form_tagid = login_form
        html_form_fields = __ac_name={user}
                   __ac_password={password}
                   submit=Log in
                   form.submitted=1
                   js_enabled=0
                   cookies_enabled=
        html_form_failure_re = (Login failed|Please log in)
        html_form_success_re = You are now logged in

        Parameters
        ----------
        fields : str or dict
          String or a dictionary, which will be used (along with credential) information
          to feed into the form
        tagid : str, optional
          id of the HTML <form> in the document to use. If None, and page contains a single form,
          that one will be used.  If multiple forms -- error will be raise
        **kwargs : dict, optional
          Passed to super class HTTPBaseAuthenticator
        """
        super(HTMLFormAuthenticator, self).__init__(**kwargs)
        self.fields = assure_dict_from_str(fields)
        self.tagid = tagid

    def _post_credential(self, credentials, post_url, session):
        post_fields = {
            k: v.format(**credentials)
            for k, v in self.fields.items()
            }
        response = session.post(post_url, data=post_fields)
        return response


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

        attempt = 0
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
                #import pdb; pdb.set_trace()
                result = method(url, **kwargs)
                # assume success if no puke etc
                break
            except AccessDeniedError as e:
                lgr.debug("Access was denied: %s", e)
                access_denied = True
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


    def download(self, url, path=None, **kwargs):
        """Fetch content as pointed by the URL optionally into a file

        Parameters
        ----------
        url : string
          URL to access
        path : str, optional
          Either full path to the file, or if exists and a directory
          -- the directory to save under. If just a filename -- store
          under curdir. If None -- fetch and return the fetched content.

        Returns
        -------
        None or bytes
        """
        # TODO: may be move all the path dealing logic here
        # but then it might require sending request anyways for Content-Disposition
        # so probably nah
        lgr.info("Downloading %r into %r", url, path)
        return self._access(self._download, url, path=path, **kwargs)


    def _check(self, url):
        raise NotImplementedError("check is not yet implemented")

    def check(self, url):
        """
        Parameters
        ----------
        url : string
          URL to access
        """
        return self._access(self._check, url, **kwargs)
