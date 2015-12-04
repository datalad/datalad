# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for http downloader"""

from os.path import join as opj
import six.moves.builtins as __builtin__

from ..http import HTTPDownloader
from ..http import DownloadError
from ..http import HTMLFormAuthenticator
from ..providers import Providers, Credential  # to test against crcns
from ...support.cookies import CookiesDB

# BTW -- mock_open is not in mock on wheezy (Debian 7.x)
import httpretty
from mock import patch
from ...tests.utils import assert_in
from ...tests.utils import assert_not_in
from ...tests.utils import assert_equal
from ...tests.utils import assert_false
from ...tests.utils import assert_raises
from ...tests.utils import ok_file_has_content
from ...tests.utils import serve_path_via_http, with_tree
from ...tests.utils import swallow_logs
from ...tests.utils import with_tempfile
from ...tests.utils import use_cassette
from ...tests.utils import SkipTest

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



@use_cassette('fixtures/vcr_cassettes/test_authenticate_external_portals.yaml', record_mode='once')
def test_authenticate_external_portals():

    providers = Providers.from_config_files()

    @with_tempfile(mkdir=True)
    def check_authenticate_external_portals(url, failed_str, success_str, d):
        fpath = opj(d, url.split('/')[-1])
        provider = providers.get_provider(url)
        if not provider.credential.is_known:
            raise SkipTest("This test requires known credentials for %s" % provider.credential.name)
        downloader = provider.get_downloader(url)
        downloader.download(url, path=d)
        with open(fpath) as f:
            content = f.read()
            assert_false(failed_str in content)
            assert_in(success_str, content)

    yield check_authenticate_external_portals, \
          "https://portal.nersc.gov/project/crcns/download/alm-1/checksums.md5", \
          "<form action=", \
          "datafiles/meta_data_files.tar.gz"
    yield check_authenticate_external_portals, \
          'https://db.humanconnectome.org/data/archive/projects/HCP_500/subjects/100307/experiments/100307_CREST/resources/100307_CREST/files/unprocessed/3T/Diffusion/100307_3T_DWI_dir97_LR.bval', \
          "failed", \
          "2000 1005 2000 3000"
test_authenticate_external_portals.tags = ['external-portal']


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


@httpretty.activate
@with_tempfile(mkdir=True)
def test_HTMLFormAuthenticator_httpretty(d):
    url = "http://example.com/crap.txt"
    test_cookie = 'somewebsite=testcookie'
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
                           set_cookie=test_cookie,
                          )
    # then in GET verify that correct cookie was provided and
    # that no credentials are there
    httpretty.register_uri(httpretty.GET, url,
                           body=request_get_callback
                          )

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
    def fake_load(self):
        self._cookies_db = {}

    with patch.object(CookiesDB, '_load', fake_load):
        downloader = HTTPDownloader(credential=credential, authenticator=authenticator)
        downloader.download(url, path=d)

    with open(fpath) as f:
        content = f.read()
        assert_equal(content, "correct body")

    # Unsuccesfull scenarios to test:
    # the provided URL at the end 404s, or another failure (e.g. interrupted download)


def test_HTTPAuthAuthenticator_httpretty():
    raise SkipTest("Not implemented. TODO")
    # TODO: Single scenario -- test that correct credentials were provided to the HTTPPretty
