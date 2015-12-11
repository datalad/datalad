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
import functools
import re
import requests

from ..utils import assure_list_from_str, assure_dict_from_str
from ..dochelpers import borrowkwargs

from ..ui import ui
from ..utils import auto_repr
from ..dochelpers import exc_str
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
        lgr.info("http session: Authenticating into session for %s", url)
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

    @borrowkwargs(BaseDownloader)
    def __init__(self, **kwargs):
        super(HTTPDownloader, self).__init__(**kwargs)
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

    def _get_download_details(self, url, chunk_size=1024**2):
        # TODO: possibly make chunk size adaptive
        response = self._session.get(url, stream=True)
        check_response_status(response)
        headers = response.headers
        target_size = int(headers.get('Content-Length', '0').strip()) or None
        # Consult about filename.  Since we already have headers,
        # should not result in an additional request
        url_filename = get_url_filename(url, headers=headers)

        def download_into_fp(f, pbar):
            total = 0
            # must use .raw to be able avoiding decoding/decompression
            for chunk in response.raw.stream(chunk_size, decode_content=False):
                if chunk:  # filter out keep-alive new chunks
                    total += len(chunk)
                    f.write(chunk)
                    try:
                        # TODO: pbar is not robust ATM against > 100% performance ;)
                        pbar.update(total)
                    except Exception as e:
                        lgr.warning("Failed to update progressbar: %s" % exc_str(e))
                    # TEMP
                    # see https://github.com/niltonvolpato/python-progressbar/pull/44
                    ui.out.flush()

        return download_into_fp, target_size, url_filename

    def _check(self, url):
        raise NotImplementedError("check is not yet implemented")

