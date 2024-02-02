# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for http downloader"""

import builtins
import os
import re
import time
from calendar import timegm
from os.path import join as opj

from datalad.downloaders.tests.utils import get_test_providers
from datalad.support.network import (
    download_url,
    get_url_straight_filename,
)
from datalad.utils import ensure_unicode

from ...support.exceptions import AccessFailedError
from ..base import (
    BaseDownloader,
    DownloadError,
    IncompleteDownloadError,
    NoneAuthenticator,
)
from ..credentials import (
    LORIS_Token,
    Token,
    UserPassword,
)
from ..http import (
    HTMLFormAuthenticator,
    HTTPBaseAuthenticator,
    HTTPBearerTokenAuthenticator,
    HTTPDownloader,
    HTTPTokenAuthenticator,
    process_www_authenticate,
)

# BTW -- mock_open is not in mock on wheezy (Debian 7.x)
try:
    import httpretty
except (ImportError, AttributeError):
    # Attribute Error happens with newer httpretty and older ssl module
    # https://github.com/datalad/datalad/pull/2623
    class NoHTTPPretty(object):
       __bool__ = lambda s: False
       activate = lambda s, t: t
    httpretty = NoHTTPPretty()

from unittest.mock import patch

from ...support.exceptions import (
    AccessDeniedError,
    AnonymousAccessDeniedError,
)
from ...support.network import get_url_disposition_filename
from ...support.status import FileStatus
from ...tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_false,
    assert_greater,
    assert_in,
    assert_not_in,
    assert_raises,
    known_failure_githubci_win,
    ok_file_has_content,
    serve_path_via_http,
    skip_if,
    skip_if_no_network,
    swallow_logs,
    swallow_outputs,
    use_cassette,
    with_fake_cookies_db,
    with_memory_keyring,
    with_tempfile,
    with_testsui,
    with_tree,
    without_http_proxy,
)
from ...utils import read_file


def test_docstring():
    doc = HTTPDownloader.__init__.__doc__
    assert_in("\ncredential: Credential", doc)


# XXX doesn't quite work as it should since doesn't provide context handling
# I guess... but at least causes the DownloadError ;)
_builtins_open = builtins.open


def fake_open(write_=None, skip_regex=None):
    class myfile(object):
        """file which does nothing"""
        if write_:
            def write(self, *args, **kwargs):
                write_(*args, **kwargs)
        def close(self):
            pass

    def myopen(path, *args, **kwargs):
        if skip_regex and re.search(skip_regex, ensure_unicode(path)):
            return _builtins_open(path, *args, **kwargs)
        else:
            return myfile
    return myopen


def _raise_IOError(*args, **kwargs):
    raise IOError("Testing here")


def test_process_www_authenticate():
    assert_equal(process_www_authenticate("Basic"),
                 ["http_basic_auth"])
    assert_equal(process_www_authenticate("Digest"),
                 ["http_digest_auth"])
    assert_equal(process_www_authenticate("Digest more"),
                 ["http_digest_auth"])
    assert_equal(process_www_authenticate("Unknown"),
                 [])


@with_tree(tree=[('file.dat', 'abc')])
@serve_path_via_http
def test_HTTPDownloader_basic(toppath=None, topurl=None):
    furl = "%sfile.dat" % topurl
    tfpath = opj(toppath, "file-downloaded.dat")
    downloader = HTTPDownloader()  # no auth/credentials needed
    download = downloader.download
    download(furl, tfpath)
    ok_file_has_content(tfpath, 'abc')

    # download() creates leading directories if needed for file targets...
    subdir_tfpath = opj(toppath, "l1", "l2", "file-downloaded.dat")
    download(furl, subdir_tfpath)
    ok_file_has_content(subdir_tfpath, 'abc')

    # ... and for directory targets.
    subdir_dirtarget = opj(toppath, "d1", "d2", "")
    download(furl, subdir_dirtarget)
    ok_file_has_content(opj(subdir_dirtarget, "file.dat"), "abc")

    # see if fetch works correctly
    assert_equal(downloader.fetch(furl), 'abc')

    # By default should not overwrite the file
    assert_raises(DownloadError, download, furl, tfpath)
    # but be able to redownload whenever overwrite==True
    downloaded_path = download(furl, tfpath, overwrite=True)
    assert_equal(downloaded_path, tfpath)
    ok_file_has_content(tfpath, 'abc')

    # Fail with an informative message if we're downloading into a directory
    # and the file name can't be determined from the URL.
    with assert_raises(DownloadError) as cm:
        download(topurl, toppath)
    assert_in("File name could not be determined", str(cm.value))

    # Some errors handling
    # XXX obscure mocking since impossible to mock write alone
    # and it still results in some warning being spit out
    # Note: we need to avoid mocking opening of the lock file!
    with swallow_logs(), \
         patch.object(builtins, 'open', fake_open(write_=_raise_IOError, skip_regex=r'.*\.lck$')):
        assert_raises(DownloadError, download, furl, tfpath, overwrite=True)

    # incomplete download scenario - should have 3 tries
    def _fail_verify_download(try_to_fail):
        try_ = [0]
        _orig_verify_download = BaseDownloader._verify_download
        def _verify_download(self, *args, **kwargs):
            try_[0] += 1
            if try_[0] >= try_to_fail:
                return _orig_verify_download(self, *args, **kwargs)
            raise IncompleteDownloadError()
        return _verify_download

    with patch.object(BaseDownloader, '_verify_download', _fail_verify_download(6)), \
        swallow_logs():
            # how was before the "fix":
            #assert_raises(DownloadError, downloader.fetch, furl)
            #assert_raises(DownloadError, downloader.fetch, furl)
            # now should download just fine
            assert_equal(downloader.fetch(furl), 'abc')
    # but should fail if keeps failing all 5 times and then on 11th should raise DownloadError
    with patch.object(BaseDownloader, '_verify_download', _fail_verify_download(7)), \
        swallow_logs():
            assert_raises(DownloadError, downloader.fetch, furl)

    # TODO: access denied scenario
    # TODO: access denied detection


@with_tree(tree=[('file.dat', 'abc')])
@serve_path_via_http
@with_memory_keyring
def test_access_denied(toppath=None, topurl=None, keyring=None):
    furl = topurl + "file.dat"

    def deny_access(*args, **kwargs):
        raise AccessDeniedError(supported_types=["http_basic_auth"])

    def deny_anon_access(*args, **kwargs):
        raise AnonymousAccessDeniedError(supported_types=["http_basic_auth"])

    downloader = HTTPDownloader()

    # Test different paths that should lead to a DownloadError.

    for denier in deny_access, deny_anon_access:
        @with_testsui(responses=["no"])
        def run_refuse_provider_setup():
            with patch.object(downloader, '_download', denier):
                downloader.download(furl)
        assert_raises(DownloadError, run_refuse_provider_setup)

    downloader_creds = HTTPDownloader(credential="irrelevant")

    @with_testsui(responses=["no"])
    def run_refuse_creds_update():
        with patch.object(downloader_creds, '_download', deny_access):
            downloader_creds.download(furl)
    assert_raises(DownloadError, run_refuse_creds_update)

    downloader_noauth = HTTPDownloader(authenticator=NoneAuthenticator())

    def run_noauth():
        with patch.object(downloader_noauth, '_download', deny_access):
            downloader_noauth.download(furl)
    assert_raises(DownloadError, run_noauth)

    # Complete setup for a new provider.

    @with_testsui(responses=[
        "yes",  # Set up provider?
        # Enter provider details, but then don't save ...
        "newprovider", re.escape(furl), "http_auth", "user_password", "no",
        # No provider, try again?
        "yes",
        # Enter same provider detains but save this time.
        "newprovider", re.escape(furl), "http_auth", "user_password", "yes",
        # Enter credentials.
        "me", "mypass"
    ])
    def run_set_up_provider():
        with patch.object(downloader, '_download', deny_access):
            downloader.download(furl)

    # We've forced an AccessDenied error and then set up bogus credentials,
    # leading to a 501 (not implemented) error.
    assert_raises(AccessFailedError, run_set_up_provider)


@with_tempfile(mkdir=True)
def check_download_external_url(url, failed_str, success_str, d, url_final=None, check_mtime=True):
    fpath = opj(d, get_url_straight_filename(url))
    providers = get_test_providers(url)  # url for check of credentials
    provider = providers.get_provider(url)
    downloader = provider.get_downloader(url)

    # we will load/fetch binary blobs
    success_bytes, failed_bytes = None, None
    if success_str is not None:
        success_bytes = success_str.encode()
    if failed_str is not None:
        failed_bytes = failed_str.encode()

    # Download way
    with swallow_outputs() as cmo:
        downloaded_path = downloader.download(url, path=d)
    assert_equal(fpath, downloaded_path)
    content = read_file(fpath, decode=False)
    if success_bytes is not None:
        assert_in(success_bytes, content)
    if failed_str is not None:
        assert_false(failed_bytes in content)

    # And if we specify size
    for s in [1, 2]:
        with swallow_outputs() as cmo:
            downloaded_path_ = downloader.download(url, path=d, size=s, overwrite=True)
        # should not be affected
        assert_equal(downloaded_path, downloaded_path_)
        content_ = read_file(fpath, decode=False)
        assert_equal(len(content_), s)
        assert_equal(content_, content[:s])

    # Fetch way
    content = downloader.fetch(url, decode=False)
    if success_bytes is not None:
        assert_in(success_bytes, content)
    if failed_bytes is not None:
        assert_false(failed_bytes in content)

    # And if we specify size
    for s in [1, 2]:
        with swallow_outputs() as cmo:
            content_ = downloader.fetch(url, size=s, decode=False)
        assert_equal(len(content_), s)
        assert_equal(content_, content[:s])

    # Verify status
    status = downloader.get_status(url)
    assert(isinstance(status, FileStatus))
    if not url.startswith('ftp://') and check_mtime:
        # TODO introduce support for mtime into requests_ftp?
        assert(status.mtime)
    assert(status.size)

    # Verify possible redirections
    if url_final is None:
        url_final = url
    assert_equal(downloader.get_target_url(url), url_final)

    # TODO -- more and more specific


def check_download_external_url_no_mtime(*args, **kwargs):
    """A helper to be used in generator tests

    since Yarik doesn't know if it is possible to pass optional args,
    and @with_tempfile sticks itself at the end of *args
    """
    kwargs['check_mtime'] = False
    return check_download_external_url(*args, **kwargs)


# TODO: @use_cassette is not playing nice with generators, causing
# troubles when trying to cause test skip if no network. So disabling for now
# https://github.com/datalad/datalad/issues/3158
# @use_cassette('test_authenticate_external_portals', record_mode='once')
def test_authenticate_external_portals():
    skip_if_no_network()
    check_download_external_url(
        "https://portal.nersc.gov/project/crcns/download/alm-1/checksums.md5",
        "<form action=",
        "datafiles/meta_data_files.tar.gz",
    )
    # seems to be gone
    # check_download_external_url(
    #       'https://db.humanconnectome.org/data/archive/projects/HCP_500/subjects/100307/experiments/100307_CREST/resources/100307_CREST/files/unprocessed/3T/Diffusion/100307_3T_DWI_dir97_LR.bval',
    #       "failed",
    #       "2000 1005 2000 3000",
    # )
    check_download_external_url(
        'https://db.humanconnectome.org/data/experiments/ConnectomeDB_E09797/resources/166768/files/filescans.csv',
        "failed",
        "'Scan','FilePath'",
    )

    check_download_external_url_no_mtime(
        "https://n5eil01u.ecs.nsidc.org/ICEBRIDGE/IDBMG4.004/1993.01.01/BedMachineGreenland-2021-04-20.nc.xml",
        'input type="password"',
        'DOCTYPE GranuleMetaDataFile',
    )

test_authenticate_external_portals.tags = ['external-portal', 'network']


@skip_if_no_network
@use_cassette('test_detect_login_error1')
def test_detect_login_error1():
    # we had unicode decode issue: https://github.com/datalad/datalad/issues/4951
    check_download_external_url(
          "https://portal.nersc.gov/project/crcns/download/ac-5/docs/data_analysis_instructions.txt",
          "<form action=",
          "DMR stimulus")
test_detect_login_error1.tags = ['external-portal', 'network']


@skip_if_no_network
@use_cassette('test_detect_login_error2')
def test_detect_login_error2():
    # a tiny binary file so we do fetch it but it cannot be decoded, we must not fail
    check_download_external_url(
          "https://portal.nersc.gov/project/crcns/download/mt-3/example_scripts.zip",
          "<form action=",
          None)
test_detect_login_error2.tags = ['external-portal', 'network']


@known_failure_githubci_win
@skip_if_no_network
def test_download_ftp():
    try:
        import requests_ftp
    except ImportError:
        raise SkipTest("need requests_ftp")  # TODO - make it not ad-hoc
    try:
        check_download_external_url(
                  "ftp://ftp.gnu.org/README",
                  None,
                  "This is ftp.gnu.org"
        )
    except AccessFailedError as exc:  # pragma: no cover
        if 'status code 503' in str(exc):
            raise SkipTest("ftp.gnu.org throws 503 when on travis (only?)")
        raise


# TODO: redo smart way with mocking, to avoid unnecessary CPU waste
@with_tree(tree={'file.dat': '1'})
@serve_path_via_http
@with_tempfile
def test_mtime(path=None, url=None, tempfile=None):
    # let's set custom mtime
    file_to_download = opj(path, 'file.dat')
    os.utime(file_to_download, (time.time(), 1000))
    assert_equal(os.stat(file_to_download).st_mtime, 1000)

    file_url = "%s/%s" % (url, 'file.dat')
    with swallow_outputs():
        get_test_providers().download(file_url, path=tempfile)
    assert_equal(os.stat(tempfile).st_mtime, 1000)


def test_get_status_from_headers():
    # function doesn't do any value transformation ATM
    headers = {
        'Content-Length': '123',
        # some other file record - we don't test content here yet
        'Content-Disposition': 'attachment; filename="bogus.txt"',
        'Last-Modified': 'Sat, 07 Nov 2015 05:23:36 GMT'
    }
    headers['bogus1'] = '123'

    assert_equal(
            HTTPDownloader.get_status_from_headers(headers),
            FileStatus(size=123, filename='bogus.txt', mtime=1446873816))

    assert_equal(HTTPDownloader.get_status_from_headers({'content-lengtH': '123'}),
                 FileStatus(size=123))

    filename = 'Glasser_et_al_2016_HCP_MMP1.0_RVVG.zip'
    headers_content_disposition = {
        'Content-Disposition':
            'Attachment;Filename="%s"' % filename, }
    assert_equal(
        HTTPDownloader.get_status_from_headers(headers_content_disposition).filename,
        filename)

    # since we are providing full headers -- irrelevant
    assert_equal(get_url_disposition_filename("http://irrelevant", headers_content_disposition),
                 filename)



# TODO: test that download fails (even if authentication credentials are right) if form_url
# is wrong!


class FakeCredential1(UserPassword):
    """Credential to test scenarios."""
    # to be reusable, and not leak across tests,
    # we should get _fixed_credentials per instance
    def __init__(self, *args, **kwargs):
        super(FakeCredential1, self).__init__(*args, **kwargs)
        self._fixed_credentials = [
            {'user': 'testlogin', 'password': 'testpassword'},
            {'user': 'testlogin2', 'password': 'testpassword2'},
            {'user': 'testlogin2', 'password': 'testpassword3'}
        ]
    def is_known(self):
        return True
    def __call__(self):
        return self._fixed_credentials[0]
    def enter_new(self):
        # pop last used credential, so we would use "new" ones
        del self._fixed_credentials[0]


url = "http://example.com/crap.txt"
test_cookie = 'somewebsite=testcookie'


@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db
def test_HTMLFormAuthenticator_httpretty(d=None):
    fpath = opj(d, 'crap.txt')

    credential = FakeCredential1(name='test', url=None)
    credentials = credential()

    def request_post_callback(request, uri, headers):
        post_params = request.parsed_body
        assert_equal(credentials['password'], post_params['password'][0])
        assert_equal(credentials['user'], post_params['username'][0])
        assert_not_in('Cookie', request.headers)
        return (200, headers, "Got {} response from {}".format(request.method, uri))

    def request_get_callback(request, uri, headers):
        assert_equal(request.body, b'')
        assert_in('Cookie', request.headers)
        assert_equal(request.headers['Cookie'], test_cookie)
        return (200, headers, "correct body")

    # SCENARIO 1
    # callback to verify that correct credentials are provided
    # and then returns the cookie to test again for 'GET'ing
    httpretty.register_uri(httpretty.POST, url,
                           body=request_post_callback,
                           set_cookie=test_cookie)
    # then in GET verify that correct cookie was provided and
    # that no credentials are there
    httpretty.register_uri(httpretty.GET, url,
                           body=request_get_callback)

    # SCENARIO 2
    # outdated cookie provided to GET -- must return 403 (access denied)
    # then our code should POST credentials again and get a new cookies
    # which is then provided to GET

    # SCENARIO 3
    # outdated cookie
    # outdated credentials
    # it should ask for new credentials (FakeCredential1 already mocks for that)
    # and then SCENARIO1 must work again

    # SCENARIO 4
    # cookie and credentials expired, user provided new bad credential

    # Also we want to test how would it work if cookie is available (may be)
    # TODO: check with correct and incorrect credential
    authenticator = HTMLFormAuthenticator(dict(username="{user}",
                                               password="{password}",
                                               submit="CustomLogin"))
    # TODO: with success_re etc
    # This is a "success test" which should be tested in various above scenarios
    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    downloader.download(url, path=d)

    content = read_file(fpath)
    assert_equal(content, "correct body")

    # Unsuccessful scenarios to test:
    # the provided URL at the end 404s, or another failure (e.g. interrupted download)


@with_memory_keyring
@with_testsui(responses=['no', 'yes', 'testlogin', 'testpassword'])
def test_auth_but_no_cred(keyring=None):
    authenticator = HTMLFormAuthenticator("")
    # Replying 'no' to the set credentials prompt should raise ValueError
    assert_raises(ValueError, HTTPDownloader, credential=None, authenticator=authenticator)
    # Reply 'yes' and set test user:pass at the next set credentials prompt
    downloader = HTTPDownloader(credential=None, authenticator=authenticator)
    # Verify credentials correctly set to test user:pass
    assert_equal(downloader.credential.get('user'), 'testlogin')
    assert_equal(downloader.credential.get('password'), 'testpassword')


@with_testsui(responses=['yes'])  # will request to reentry it
def test_authfail404_interactive():
    # we will firsts get 'failed' but then real 404 when trying new password
    check_httpretty_authfail404(['failed', '404'])


@with_testsui(interactive=False)  # no interactions -- blow!
def test_authfail404_noninteractive():
    # we do not get to the 2nd attempt so just get 'failed'
    # and exception thrown inside is not emerging all the way here but
    # caught in the check_
    check_httpretty_authfail404(['failed'])


@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_fake_cookies_db
@with_tempfile(mkdir=True)
def check_httpretty_authfail404(exp_called, d):
    # mimic behavior of nersc which 404s but provides feedback whenever
    # credentials are incorrect.  In our case we should fail properly
    credential = FakeCredential1(name='test', url=None)

    was_called = []

    def request_post_callback(request, uri, headers):
        post_params = request.parsed_body
        if post_params['password'][0] == 'testpassword2':
            was_called.append('404')
            return 404, headers, "Really 404"
        else:
            was_called.append('failed')
            return 404, headers, "Failed"

    httpretty.register_uri(httpretty.POST, url, body=request_post_callback)

    # Also we want to test how would it work if cookie is available (may be)
    authenticator = HTMLFormAuthenticator(dict(username="{user}",
                                               password="{password}",
                                               submit="CustomLogin"),
                                          failure_re="Failed")

    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    # first one goes with regular DownloadError -- was 404 with not matching content
    assert_raises(DownloadError, downloader.download, url, path=d)
    assert_equal(was_called, exp_called)


def test_auth_bytes_content():
    # Our regexes are strings, but we can get content in bytes:
    # I am not sure yet either we shouldn't just skip then testing for regex,
    # but we definitely should not crash.
    authenticator = HTTPBaseAuthenticator(failure_re="Failed")
    authenticator.check_for_auth_failure(b"bytes")
    # but ATM we do test bytes content, let's ENSURE that!
    with assert_raises(AccessDeniedError):
        authenticator.check_for_auth_failure(b"Failed")


class FakeCredential2(UserPassword):
    """Credential to test scenarios."""
    _fixed_credentials = {'user': 'testlogin', 'password': 'testpassword'}
    def is_known(self):
        return True
    def __call__(self):
        return self._fixed_credentials
    def enter_new(self):
        return self._fixed_credentials


@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db(cookies={'example.com': dict(some_site_id='idsomething', expires='Tue, 15 Jan 2013 21:47:38 GMT')})
def test_scenario_2(d=None):
    fpath = opj(d, 'crap.txt')

    credential = FakeCredential2(name='test', url=None)
    credentials = credential()
    authenticator = HTMLFormAuthenticator(dict(username="{user}",
                                               password="{password}",
                                               submit="CustomLogin"))

    def request_get_with_expired_cookie_callback(request, uri, headers):
        assert_in('Cookie', request.headers)
        cookie_vals = request.headers['Cookie'].split('; ')
        for v in cookie_vals:
            if v.startswith('expires'):
                expiration_date = v.split('=')[1]
                expiration_epoch_time = timegm(time.strptime(expiration_date, "%a, %d %b %Y %H:%M:%S GMT"))
                assert_greater(time.time(), expiration_epoch_time)
        return (403, headers, "cookie was expired")

    def request_post_callback(request, uri, headers):
        post_params = request.parsed_body
        assert_equal(credentials['password'], post_params['password'][0])
        assert_equal(credentials['user'], post_params['username'][0])
        assert_not_in('Cookie', request.headers)
        return (200, headers, "Got {} response from {}".format(request.method, uri))

    def request_get_callback(request, uri, headers):
        assert_equal(request.body, b'')
        assert_in('Cookie', request.headers)
        assert_equal(request.headers['Cookie'], test_cookie)
        return (200, headers, "correct body")

    # SCENARIO 2
    # outdated cookie provided to GET, return 403 (access denied)
    # then like SCENARIO 1 again:
    # POST credentials and get a new cookie
    # which is then provided to a GET request
    httpretty.register_uri(httpretty.GET, url,
                           responses=[httpretty.Response(body=request_get_with_expired_cookie_callback),
                                      httpretty.Response(body=request_get_callback),
                                     ])

    # callback to verify that correct credentials are provided
    # and then returns the cookie to test again for 'GET'ing
    httpretty.register_uri(httpretty.POST, url,
                           body=request_post_callback,
                           set_cookie=test_cookie)
    # then in another GET is performed to verify that correct cookie was provided and
    # that no credentials are there

    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    downloader.download(url, path=d)

    content = read_file(fpath)
    assert_equal(content, "correct body")


class FakeCredential3(Token):
    """Credential to test scenarios."""
    _fixed_credentials = {'token' : 'testtoken' }
    def is_known(self):
        return True
    def __call__(self):
        return self._fixed_credentials
    def enter_new(self):
        return self._fixed_credentials

@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db
def test_HTTPBearerTokenAuthenticator(d=None):
    fpath = opj(d, 'crap.txt')

    def request_get_callback(request, uri, headers):
        # We can't assert inside the callback, or running the
        # test give "Connection aborted" errors instead of telling
        # us that the assertion failed. So instead, we make
        # the request object available outside of the callback
        # and do the assertions in the main test, not the callback
        request_get_callback.req = request
        return (200, headers, "correct body")

    httpretty.register_uri(httpretty.GET, url,
                           body=request_get_callback)



    credential = FakeCredential3(name='test', url=None)
    authenticator = HTTPBearerTokenAuthenticator()
    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    downloader.download(url, path=d)

    # Perform assertions. See note above.
    r = request_get_callback.req
    assert_equal(r.body, b'')
    assert_in('Authorization', r.headers)
    assert_equal(r.headers['Authorization'], "Bearer testtoken")

    content = read_file(fpath)
    assert_equal(content, "correct body")

    # While having this test case setup, test the the odd brother
    downloader = HTTPDownloader(credential=credential, authenticator=HTTPTokenAuthenticator())
    downloader.download(url, path=d, overwrite=True)
    assert_equal(request_get_callback.req.headers['Authorization'], "Token testtoken")


class FakeLorisCredential(Token):
    """Credential to test scenarios."""
    _fixed_credentials = {'token' : 'testtoken' }
    def is_known(self):
        return False
@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db
def test_HTTPLorisTokenAuthenticator(d=None):
    fpath = opj(d, 'crap.txt')

    def request_get_callback(request, uri, headers):
        # We can't assert inside the callback, or running the
        # test give "Connection aborted" errors instead of telling
        # us that the assertion failed. So instead, we make
        # the request object available outside of the callback
        # and do the assertions in the main test, not the callback
        request_get_callback.req = request
        return (200, headers, "correct body")

    httpretty.register_uri(httpretty.GET, url,
                           body=request_get_callback)



    credential = FakeCredential3(name='test', url=None)
    authenticator = HTTPBearerTokenAuthenticator()
    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    downloader.download(url, path=d)

    # Perform assertions. See note above.
    r = request_get_callback.req
    assert_equal(r.body, b'')
    assert_in('Authorization', r.headers)
    assert_equal(r.headers['Authorization'], "Bearer testtoken")

    content = read_file(fpath)
    assert_equal(content, "correct body")


@skip_if(not httpretty, "no httpretty")
@without_http_proxy
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db
@with_memory_keyring
@with_testsui(responses=['yes', 'user'])
def test_lorisadapter(d=None, keyring=None):
    fpath = opj(d, 'crap.txt')
    loginurl = "http://www.example.com/api/v0.0.2/login"

    def request_get_callback(request, uri, headers):
        # We can't assert inside the callback, or running the
        # test give "Connection aborted" errors instead of telling
        # us that the assertion failed. So instead, we make
        # the request object available outside of the callback
        # and do the assertions in the main test, not the callback
        request_get_callback.req = request
        return (200, headers, "correct body")
    def request_post_callback(request, uri, headers):
        return (200, headers, '{ "token": "testtoken33" }')

    httpretty.register_uri(httpretty.GET, url,
                           body=request_get_callback)
    httpretty.register_uri(httpretty.POST, loginurl,
                           body=request_post_callback)



    credential = LORIS_Token(name='test', url=loginurl, keyring=None)
    authenticator = HTTPBearerTokenAuthenticator()
    downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
    downloader.download(url, path=d)

    r = request_get_callback.req
    assert_equal(r.body, b'')
    assert_in('Authorization', r.headers)
    assert_equal(r.headers['Authorization'], "Bearer testtoken33")
    # Verify credentials correctly set to test user:pass

    content = read_file(fpath)
    assert_equal(content, "correct body")


@with_tree(tree=[('file.dat', 'abc')])
@serve_path_via_http
def test_download_url(toppath=None, topurl=None):
    furl = "%sfile.dat" % topurl
    # fails if URL is dysfunctional
    assert_raises(DownloadError, download_url, furl + 'magic', toppath)

    # working download
    tfpath = opj(toppath, "file-downloaded.dat")
    download_url(furl, tfpath)
    ok_file_has_content(tfpath, 'abc')

    # fails if destfile exists
    assert_raises(DownloadError, download_url, furl, tfpath)
    # works when forced
    download_url(furl, tfpath, overwrite=True)
