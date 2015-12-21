# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for http downloader"""

import os
from os.path import join as opj
import time
from calendar import timegm
import six.moves.builtins as __builtin__
from six import PY3

from ..base import DownloadError
from ..http import HTTPDownloader
from ..http import HTMLFormAuthenticator
from ..providers import Providers, Credential  # to test against crcns
from ...support.cookies import CookiesDB

from ...support.network import get_url_straight_filename
from ...tests.utils import with_fake_cookies_db

# BTW -- mock_open is not in mock on wheezy (Debian 7.x)
if PY3:
    class NoHTTPPretty(object):
       __bool__ = __nonzero__ = lambda s: False
       activate = lambda s, t: t
    httpretty = NoHTTPPretty()
else:
    import httpretty

from mock import patch
from ...tests.utils import assert_in
from ...tests.utils import assert_not_in
from ...tests.utils import assert_equal
from ...tests.utils import assert_greater
from ...tests.utils import assert_false
from ...tests.utils import assert_raises
from ...tests.utils import ok_file_has_content
from ...tests.utils import serve_path_via_http, with_tree
from ...tests.utils import swallow_logs
from ...tests.utils import swallow_outputs
from ...tests.utils import with_tempfile
from ...tests.utils import use_cassette
from ...tests.utils import SkipTest
from ...tests.utils import skip_httpretty_on_problematic_pythons
from ...tests.utils import skip_if

def test_docstring():
    doc = HTTPDownloader.__init__.__doc__
    assert_in("\ncredential: Credential", doc)

# XXX doesn't quite work as it should since doesn't provide context handling
# I guess... but at least causes the DownloadError ;)
def fake_open(write_=None):
    class myfile(object):
        """file which does nothing"""
        if write_:
            def write(self, *args, **kwargs):
                write_(*args, **kwargs)
        def close(self):
            pass

    def myopen(*args, **kwargs):
        return myfile
    return myopen

def _raise_IOError(*args, **kwargs):
    raise IOError("Testing here")

@with_tree(tree=[('file.dat', 'abc')])
@serve_path_via_http
def test_HTTPDownloader_basic(toppath, topurl):
    furl = "%sfile.dat" % topurl
    tfpath = opj(toppath, "file-downloaded.dat")
    downloader = HTTPDownloader()  # no auth/credentials needed
    download = downloader.download
    download(furl, tfpath)
    ok_file_has_content(tfpath, 'abc')

    # see if fetch works correctly
    assert_equal(downloader.fetch(furl), 'abc')

    # By default should not overwrite the file
    assert_raises(DownloadError, download, furl, tfpath)
    # but be able to redownload whenever overwrite==True
    downloaded_path = download(furl, tfpath, overwrite=True)
    assert_equal(downloaded_path, tfpath)
    ok_file_has_content(tfpath, 'abc')

    # Some errors handling
    # XXX obscure mocking since impossible to mock write alone
    # and it still results in some warning being spit out
    with swallow_logs(), \
         patch.object(__builtin__, 'open', fake_open(write_=_raise_IOError)):
        assert_raises(DownloadError, download, furl, tfpath, overwrite=True)

    # TODO: access denied scenario
    # TODO: access denied detection


_test_providers = None

def _get_test_providers():
    """Return reusable instance of our global providers"""
    global _test_providers
    if not _test_providers:
        _test_providers = Providers.from_config_files()
    return _test_providers

@with_tempfile(mkdir=True)
def check_download_external_url(url, failed_str, success_str, d):
    fpath = opj(d, get_url_straight_filename(url))
    _test_providers = _get_test_providers()
    provider = _test_providers.get_provider(url)
    if not provider.credential.is_known:
        raise SkipTest("This test requires known credentials for %s" % provider.credential.name)
    downloader = provider.get_downloader(url)

    # Download way
    with swallow_outputs() as cmo:
        downloaded_path = downloader.download(url, path=d)
    assert_equal(fpath, downloaded_path)
    with open(fpath) as f:
        content = f.read()
        if success_str is not None:
            assert_in(success_str, content)
        if failed_str is not None:
            assert_false(failed_str in content)

    # And if we specify size
    for s in [1, 2]:
        #with swallow_outputs() as cmo:
        downloaded_path_ = downloader.download(url, path=d, size=s, overwrite=True)
        # should not be affected
        assert_equal(downloaded_path, downloaded_path_)
        with open(fpath) as f:
            content_ = f.read()
        assert_equal(len(content_), s)
        assert_equal(content_, content[:s])

    # Fetch way
    content = downloader.fetch(url)
    if success_str is not None:
        assert_in(success_str, content)
    if failed_str is not None:
        assert_false(failed_str in content)

    # And if we specify size
    for s in [1, 2]:
        with swallow_outputs() as cmo:
            content_ = downloader.fetch(url, size=s)
        assert_equal(len(content_), s)
        assert_equal(content_, content[:s])

    # Verify status
    status = downloader.get_status(url)
    assert_in('Last-Modified', status)
    assert_in('Content-Length', status)
    # TODO -- more and more specific


@use_cassette('fixtures/vcr_cassettes/test_authenticate_external_portals.yaml', record_mode='once')
def test_authenticate_external_portals():
    yield check_download_external_url, \
          "https://portal.nersc.gov/project/crcns/download/alm-1/checksums.md5", \
          "<form action=", \
          "datafiles/meta_data_files.tar.gz"
    yield check_download_external_url, \
          'https://db.humanconnectome.org/data/archive/projects/HCP_500/subjects/100307/experiments/100307_CREST/resources/100307_CREST/files/unprocessed/3T/Diffusion/100307_3T_DWI_dir97_LR.bval', \
          "failed", \
          "2000 1005 2000 3000"
test_authenticate_external_portals.tags = ['external-portal', 'network']

# TODO: redo smart way with mocking, to avoid unnecessary CPU waste
@with_tree(tree={'file.dat': '1'})
@serve_path_via_http
@with_tempfile
def test_mtime(path, url, tempfile):
    # let's set custom mtime
    file_to_download = opj(path, 'file.dat')
    os.utime(file_to_download, (time.time(), 1000))
    assert_equal(os.stat(file_to_download).st_mtime, 1000)

    file_url = "%s/%s" % (url, 'file.dat')
    with swallow_outputs():
        _get_test_providers().download(file_url, path=tempfile)
    assert_equal(os.stat(tempfile).st_mtime, 1000)

def test_get_status_from_headers():
    # function doesn't do any value transformation ATM
    headers = {
        'Content-Length': '123',
        # some other file record - we don't test content here yet
        'Content-Disposition': "bogus.txt",
        'Last-Modified': 'Sat, 07 Nov 2015 05:23:36 GMT'
    }
    headers['bogus1'] = '123'
    assert_equal(
            HTTPDownloader.get_status_from_headers(headers),
            {'Content-Length': 123, 'Content-Disposition': "bogus.txt", 'Last-Modified': 1446873816})
    assert_equal(HTTPDownloader.get_status_from_headers({'content-lengtH': '123'}), {'Content-Length': 123})

# TODO: test that download fails (even if authentication credentials are right) if form_url
# is wrong!


class FakeCredential1(Credential):
    """Credential to test scenarios."""
    _fixed_credentials = [
        {'user': 'testlogin', 'password': 'testpassword'},
        {'user': 'testlogin2', 'password': 'testpassword2'},
        {'user': 'testlogin2', 'password': 'testpassword3'}]
    def is_known(self):
        return True
    def __call__(self):
        return self._fixed_credentials[0]
    def enter_new(self):
        # pop last used credential, so we would use "new" ones
        del self._fixed_credentials[0]


url = "http://example.com/crap.txt"
test_cookie = 'somewebsite=testcookie'

#@skip_httpretty_on_problematic_pythons
@skip_if(not httpretty, "no httpretty")
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db
def test_HTMLFormAuthenticator_httpretty(d):
    fpath = opj(d, 'crap.txt')

    credential = FakeCredential1(name='test', type='user_password', url=None)
    credentials = credential()

    def request_post_callback(request, uri, headers):
        post_params = request.parsed_body
        assert_equal(credentials['password'], post_params['password'][0])
        assert_equal(credentials['user'], post_params['username'][0])
        assert_not_in('Cookie', request.headers)
        return (200, headers, "Got {} response from {}".format(request.method, uri))

    def request_get_callback(request, uri, headers):
        assert_equal(request.body, '')
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

    with open(fpath) as f:
        content = f.read()
        assert_equal(content, "correct body")

    # Unsuccesfull scenarios to test:
    # the provided URL at the end 404s, or another failure (e.g. interrupted download)



class FakeCredential2(Credential):
    """Credential to test scenarios."""
    _fixed_credentials = {'user': 'testlogin', 'password': 'testpassword'}
    def is_known(self):
        return True
    def __call__(self):
        return self._fixed_credentials
    def enter_new(self):
        return self._fixed_credentials


@skip_if(not httpretty, "no httpretty")
@httpretty.activate
@with_tempfile(mkdir=True)
@with_fake_cookies_db(cookies={'example.com': dict(some_site_id='idsomething', expires='Tue, 15 Jan 2013 21:47:38 GMT')})
def test_HTMLFormAuthenticator_httpretty_2(d):
    fpath = opj(d, 'crap.txt')

    credential = FakeCredential2(name='test', type='user_password', url=None)
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
        assert_equal(request.body, '')
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

    with open(fpath) as f:
        content = f.read()
        assert_equal(content, "correct body")


