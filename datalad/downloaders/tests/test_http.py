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

from ..base import DownloadError
from ..http import HTTPDownloader
from ..http import HTMLFormAuthenticator
from ..providers import Providers, Credential  # to test against crcns

from ...support.network import get_url_straight_filename

# BTW -- mock_open is not in mock on wheezy (Debian 7.x)
import httpretty
from mock import patch
from ...tests.utils import assert_in
from ...tests.utils import assert_equal
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

@with_tempfile(mkdir=True)
def check_download_external_url(url, failed_str, success_str, d):
    global _test_providers
    fpath = opj(d, get_url_straight_filename(url))
    if not _test_providers:
        _test_providers = Providers.from_config_files()
    provider = _test_providers.get_provider(url)
    if not provider.credential.is_known:
        raise SkipTest("This test requires known credentials for %s" % provider.credential.name)
    downloader = provider.get_downloader(url)
    with swallow_outputs() as cmo:
        downloaded_path = downloader.download(url, path=d)
    assert_equal(fpath, downloaded_path)
    with open(fpath) as f:
        content = f.read()
        if success_str is not None:
            assert_in(success_str, content)
        if failed_str is not None:
            assert_false(failed_str in content)


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

@skip_httpretty_on_problematic_pythons
@httpretty.activate
@with_tempfile(mkdir=True)
def test_HTMLFormAuthenticator_httpretty(d):
    url = "http://example.com/crap.txt"
    fpath = opj(d, 'crap.txt')

    # SCENARIO 1
    # TODO: callaback which would verify that correct credentials provided
    # and return the cookie, which will be tested again while 'GET'ing
    httpretty.register_uri(httpretty.POST, url,
                           body="whatever",  # TODO: return some cookie for the session
                           status=200)
    # in GET verify that correct cookie was provided, and verify that no
    # credentials sneaked in
    httpretty.register_uri(httpretty.GET, url,
                           body="correct body",
                           status=200)

    # SCENARIO 2
    # outdated cookie provided to GET -- you must return 403 (access denied)
    # then our code should POST credentials again and get a new cookies
    # which is then provided to GET

    # SCENARIO 3
    # outdated cookie
    # outdated credentials
    # it should ask for new credentials (FakeCredential1 already mocks for that)
    # and then SCENARIO1 must work again

    # SCENARIO 4
    # cookie and credentials expired, user provided new bad credential

    # TODO: somehow mock or whatever access to cookies, because we don't want to modify
    # user's cookies during the test.
    # Also we want to test how would it work if cookie is available (may be)
    # TODO: check with correct and incorrect credential
    credential = FakeCredential1(name='test', type='user_password', url=None)
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
    # Provided URL is at the end 404s, or another failure (e.g. interrupted download)

def test_HTTPAuthAuthenticator_httpretty():
    raise SkipTest("Not implemented. TODO")
    # TODO: Single scenario -- test that correct credentials were provided to the HTTPPretty