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
import requests.auth
# at some point was trying to be too specific about which exceptions to
# catch for a retry of a download.
# from urllib3.exceptions import MaxRetryError, NewConnectionError

import io
from six import BytesIO
from time import sleep

from ..utils import assure_list_from_str, assure_dict_from_str
from ..dochelpers import borrowkwargs

from ..ui import ui
from ..utils import auto_repr
from ..dochelpers import exc_str
from ..support.network import get_url_filename
from ..support.network import get_response_disposition_filename
from ..support.network import rfc2822_to_epoch
from ..support.cookies import cookies_db
from ..support.status import FileStatus

from .base import Authenticator
from .base import BaseDownloader, DownloaderSession
from .base import DownloadError, AccessDeniedError, AccessFailedError, UnhandledRedirectError

from logging import getLogger
from ..log import LoggerHelper
lgr = getLogger('datalad.http')

try:
    import requests_ftp
    requests_ftp.monkeypatch_session()
except ImportError as e:
    lgr.debug("Failed to import requests_ftp, thus no ftp support: %s" % exc_str(e))
    pass

if lgr.getEffectiveLevel() <= 1:
    # Let's also enable requests etc debugging

    # These two lines enable debugging at httplib level (requests->urllib3->http.client)
    # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
    # The only thing missing will be the response.body which is not logged.
    from six.moves import http_client
    # TODO: nohow wrapped with logging, plain prints (heh heh), so formatting will not be consistent
    http_client.HTTPConnection.debuglevel = 1

    # for requests we can define logging properly
    requests_log = LoggerHelper(logtarget="requests.packages.urllib3").get_initialized_logger()
    requests_log.setLevel(lgr.getEffectiveLevel())
    requests_log.propagate = True

__docformat__ = 'restructuredtext'


def check_response_status(response, err_prefix="", session=None):
    """Check if response's status_code signals problem with authentication etc

    ATM succeeds only if response code was 200
    """
    if not err_prefix:
        err_prefix = "Access to %s has failed: " % response.url
    # 401 would be for digest authentication mechanism, or if we first ask which mechanisms are
    # supported.... must be linked into the logic if we decide to automagically detect which
    # mechanism or to give more sensible error message
    err_msg = err_prefix + "status code %d" % response.status_code
    if response.status_code in {404}:
        # It could have been that form_url is wrong, so let's just say that
        # TODO: actually may be that is where we could use tagid and actually determine the form submission url
        raise DownloadError(err_prefix + "not found")
    elif 400 <= response.status_code < 500:
        raise AccessDeniedError(err_msg)
    elif response.status_code in {200}:
        pass
    elif response.status_code in {301, 302, 307}:
        # TODO: apparently tests do not excercise this one yet
        if session is None:
            raise AccessFailedError(err_msg + " no session was provided")
        redirs = list(session.resolve_redirects(response, response.request))
        if len(redirs) > 1:
            lgr.warning("Multiple redirects aren't supported yet.  Taking first")
        elif len(redirs) == 0:
            raise AccessFailedError("No redirects were resolved")
        raise UnhandledRedirectError(err_msg, url=redirs[0].url)
    else:
        raise AccessFailedError(err_msg)


@auto_repr
class HTTPBaseAuthenticator(Authenticator):
    """Base class for html_form and http_auth authenticators
    """
    def __init__(self, url=None, failure_re=None, success_re=None,
                 session_cookies=None, **kwargs):
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
        session_cookies : str or list of str, optional
          Session cookies to store (besides auth response cookies)
        """
        super(HTTPBaseAuthenticator, self).__init__(**kwargs)
        self.url = url
        self.failure_re = assure_list_from_str(failure_re)
        self.success_re = assure_list_from_str(success_re)
        self.session_cookies = assure_list_from_str(session_cookies)

    def authenticate(self, url, credential, session, update=False):
        # we should use specified URL for this authentication first
        lgr.info("http session: Authenticating into session for %s", url)
        post_url = self.url if self.url else url
        credentials = credential()

        # TODO: With digestauth there is no POST strictly necessary.
        # The whole thing relies on server first spitting out 401
        # and client GETing again with 'Authentication:' header
        # So we need custom handling for those, while keeping track not
        # of cookies per se, but of 'Authentication:' header which is
        # to be used in subsequent GETs
        response = self._post_credential(credentials, post_url, session)

        err_prefix = "Authentication to %s failed: " % post_url
        try:
            check_response_status(response, err_prefix, session=session)
        except DownloadError:
            # It might have happened that the return code was 'incorrect'
            # and we did get some feedback, which we could analyze to
            # figure out actual problem.  E.g. in case of nersc of crcns
            # it returns 404 (not found) with text in the html
            if response is not None and response.text:
                self.check_for_auth_failure(response.text, err_prefix)
            raise

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

        cookies_dict = {}
        if response.cookies:
            cookies_dict = requests.utils.dict_from_cookiejar(response.cookies)
        if self.session_cookies:
            # any session cookies to store
            cookies_dict.update({k: session.cookies[k] for k in self.session_cookies})

        if cookies_dict:
            if (url in cookies_db) and update:
                cookies_db[url].update(cookies_dict)
            else:
                cookies_db[url] = cookies_dict
            # assign cookies for this session
            for c, v in cookies_dict.items():
                if c not in session.cookies or session.cookies[c] != v:
                    session.cookies[c] = v  # .update(cookies_dict)
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
        lgr.debug("Posted to %s fields %s, got response %s with headers %s",
                  post_url, list(post_fields.keys()), response, list(response.headers.keys()))
        return response


@auto_repr
class HTTPRequestsAuthenticator(HTTPBaseAuthenticator):
    """Base class for various authenticators using requests pre-crafted ones
    """

    REQUESTS_AUTHENTICATOR = None

    def __init__(self, **kwargs):
        # so we have __init__ solely for a custom docstring
        super(HTTPRequestsAuthenticator, self).__init__(**kwargs)

    def _post_credential(self, credentials, post_url, session):
        response = session.post(post_url, data={},
                                auth=self.REQUESTS_AUTHENTICATOR(credentials['user'], credentials['password']))
        return response


@auto_repr
class HTTPBasicAuthAuthenticator(HTTPRequestsAuthenticator):
    """Authenticate via basic HTTP authentication

    Example specification in the .ini config file
    [provider:hcp-db]
    ...
    credential = hcp-db
    authentication_type = http_auth
    http_auth_url = .... TODO

    Parameters
    ----------
    **kwargs : dict, optional
      Passed to super class HTTPBaseAuthenticator
    """

    REQUESTS_AUTHENTICATOR = requests.auth.HTTPBasicAuth


@auto_repr
class HTTPDigestAuthAuthenticator(HTTPRequestsAuthenticator):
    """Authenticate via HTTP digest authentication
    """

    REQUESTS_AUTHENTICATOR = requests.auth.HTTPDigestAuth

    def _post_credential(self, *args, **kwargs):
        raise NotImplementedError("not yet functioning, see https://github.com/kennethreitz/requests/issues/2934")


@auto_repr
class HTTPDownloaderSession(DownloaderSession):
    def __init__(self, size=None, filename=None,  url=None, headers=None,
                 response=None, chunk_size=1024 ** 2):
        super(HTTPDownloaderSession, self).__init__(
            size=size, filename=filename, url=url, headers=headers,
        )
        self.chunk_size = chunk_size
        self.response = response

    def download(self, f=None, pbar=None, size=None):
        response = self.response
        # content_gzipped = 'gzip' in response.headers.get('content-encoding', '').split(',')
        # if content_gzipped:
        #     raise NotImplemented("We do not support (yet) gzipped content")
        #     # see https://rationalpie.wordpress.com/2010/06/02/python-streaming-gzip-decompression/
        #     # for ways to implement in python 2 and 3.2's gzip is working better with streams

        total = 0
        return_content = f is None
        if f is None:
            # no file to download to
            # TODO: actually strange since it should have been decoded then...
            f = BytesIO()

        # must use .raw to be able avoiding decoding/decompression while downloading
        # to a file
        chunk_size_ = min(self.chunk_size, size) if size is not None else self.chunk_size

        # XXX With requests_ftp BytesIO is provided as response.raw for ftp urls,
        # which has no .stream, so let's do ducktyping and provide our custom stream
        # via BufferedReader for such cases, while maintaining the rest of code
        # intact.  TODO: figure it all out, since doesn't scale for any sizeable download
        if not hasattr(response.raw, 'stream'):
            def _stream():
                buf = io.BufferedReader(response.raw)
                v = True
                while v:
                    v = buf.read(chunk_size_)
                    yield v

            stream = _stream()
        else:
            # XXX TODO -- it must be just a dirty workaround
            # As we discovered with downloads from NITRC all headers come with
            # Content-Encoding: gzip which leads  requests to decode them.  But the point
            # is that ftp links (yoh doesn't think) are gzip compressed for the transfer
            decode_content = not response.url.startswith('ftp://')
            stream = response.raw.stream(chunk_size_, decode_content=decode_content)

        for chunk in stream:
            if chunk:  # filter out keep-alive new chunks
                chunk_len = len(chunk)
                if size is not None and total + chunk_len > size:
                    # trim the download to match target size
                    chunk = chunk[:size - total]
                    chunk_len = len(chunk)
                total += chunk_len
                f.write(chunk)
                try:
                    # TODO: pbar is not robust ATM against > 100% performance ;)
                    if pbar:
                        pbar.update(total)
                except Exception as e:
                    lgr.warning("Failed to update progressbar: %s" % exc_str(e))
                # TEMP
                # see https://github.com/niltonvolpato/python-progressbar/pull/44
                ui.out.flush()
                if size is not None and total >= size:
                    break  # we have done as much as we were asked

        if return_content:
            out = f.getvalue()
            return out


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
                cookie_dict = cookies_db[url]
                lgr.debug("http session: Creating new with old cookies %s", list(cookie_dict.keys()))
                self._session = requests.Session()
                # not sure what happens if cookie is expired (need check to that or exception will prolly get thrown)

                # TODO dict_to_cookiejar doesn't preserve all fields when reversed
                self._session.cookies = requests.utils.cookiejar_from_dict(cookie_dict)
                # TODO cookie could be expired w/ something like (but docs say it should be expired automatically):
                # http://docs.python-requests.org/en/latest/api/#requests.cookies.RequestsCookieJar.clear_expired_cookies
                # self._session.cookies.clear_expired_cookies()
                return True

        lgr.debug("http session: Creating brand new session")
        self._session = requests.Session()
        if self.authenticator:
            self.authenticator.authenticate(url, self.credential, self._session)

        return False

    def get_downloader_session(self, url,
                               allow_redirects=True,
                               use_redirected_url=True,
                               headers=None):
        # TODO: possibly make chunk size adaptive
        # TODO: make it not this ugly -- but at the moment we are testing end-file size
        # while can't know for sure if content was gunziped and either it all went ok.
        # So safer option -- just request to not have it gzipped
        if headers is None:
            headers = {}
        if 'Accept-Encoding' not in headers:
            headers['Accept-Encoding'] = ''
        # TODO: our tests ATM aren't ready for retries, thus altogether disabled for now
        nretries = 1
        for retry in range(1, nretries+1):
            try:
                response = self._session.get(url, stream=True, allow_redirects=allow_redirects, headers=headers)
            #except (MaxRetryError, NewConnectionError) as exc:
            except Exception as exc:
                # happen to run into those with urls pointing to Amazon, so let's rest and try again
                if retry >= nretries:
                    #import epdb; epdb.serve()
                    raise AccessFailedError("Failed to establish a new session %d times. Last exception was: %s"
                                            % (nretries, exc_str(exc)))
                lgr.warning("Caught exception %s. Will retry %d out of %d times", exc_str(exc), retry+1, nretries)
                sleep(2**retry)

        check_response_status(response, session=self._session)
        headers = response.headers
        lgr.debug("Establishing session for url %s, response headers: %s", url, headers)
        target_size = int(headers.get('Content-Length', '0').strip()) or None
        if use_redirected_url and response.url and response.url != url:
            lgr.debug("URL %s was redirected to %s and thus the later will be used"
                      % (url, response.url))
            url = response.url
        # Consult about filename.  Since we already have headers,
        # should not result in an additional request
        url_filename = get_url_filename(url, headers=headers)

        headers['Url-Filename'] = url_filename
        return HTTPDownloaderSession(
            size=target_size,
            url=response.url,
            filename=url_filename,
            headers=headers,
            response=response
        )

    @classmethod
    def get_status_from_headers(cls, headers):
        """Given HTTP headers, return 'status' record to assess later if link content was changed
        """
        # used for quick checks for HTTP or S3?
        # TODO:  So we will base all statuses on this set? e.g. for Last-Modified if to be
        # mapping from field to its type converter
        HTTP_HEADERS_TO_STATUS = {
            'Content-Length': int,
            'Content-Disposition': str,
            'Last-Modified': rfc2822_to_epoch,
            'Url-Filename': str,
        }
        # Allow for webserver to return them in other casing
        HTTP_HEADERS_TO_STATUS_lower = {s.lower(): (s, t) for s, t in HTTP_HEADERS_TO_STATUS.items()}
        status = {}
        if headers:
            for header_key in headers:
                try:
                    k, t = HTTP_HEADERS_TO_STATUS_lower[header_key.lower()]
                except KeyError:
                    continue
                status[k] = t(headers[header_key])

        # convert to FileStatus
        return FileStatus(
            size=status.get('Content-Length'),
            mtime=status.get('Last-Modified'),
            filename=get_response_disposition_filename(
                status.get('Content-Disposition')) or status.get('Url-Filename')
        )
