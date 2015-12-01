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
from ..providers import Providers  # to test against crcns

# BTW -- mock_open is not in mock on wheezy (Debian 7.x)
from mock import patch
from ...tests.utils import assert_in
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


# @use_cassette('fixtures/vcr_cassettes/crcns-alm-1-auth.yaml')
@with_tempfile(mkdir=True)
def test_authenticate_crcns(d):
    providers = Providers.from_config_files()
    url = 'https://portal.nersc.gov/project/crcns/download/alm-1/checksums.md5'
    fpath = opj(d, 'checksums.md5')
    crcns = providers.get_provider(url)
    if not crcns.credential.is_known:
        raise SkipTest("This test requires known credentials for CRCNS")
    downloader = crcns.get_downloader(url)
    downloader.download(url, path=d)
    with open(fpath) as f:
        content = f.read()
        assert_false("<form action=" in content)
        assert_in("datafiles/meta_data_files.tar.gz", content)
test_authenticate_crcns.tags = ['external-portal']

# TODO: test that download fails (even if authentication credentials are right) if form_url
# is wrong!




import httpretty, requests, sure

# TODO
# def test_HTMLFormAuthenticator_constructor():
    # pass

url = 'https://portal.nersc.gov/project/crcns/download/pvc-1'
html = '''<html><body>
  <form action="/project/crcns/download/index.php" method="post">
   <input type="hidden" name="fn" value="pvc-1" />
   <table>
   <tr><td>username:</td><td><input type="text" name="username" /></td></tr>
   <tr><td>password:</td><td><input type="password" name="password" /></td></tr>
   </table>
   <input type="submit" name="submit" value="Login" /></form>
</body></html>''',
header_vals = dict(username='myusername', password='mypassword', submit='Login')

@httpretty.activate
def test_HTMLFormAuthenticator_authenticate_crcns(url=url, fields=header_vals):

    httpretty.register_uri(httpretty.POST, url,
                           body=html,
                           status=200)

    response = requests.post(url, data=header_vals)
    sure.expect(response.status_code).to.equal(200)


def test_HTMLFormAuthenticator_authenticate_crcns2(url=url, fields=header_vals):

    httpretty.register_uri(httpretty.POST, url,
                           body=html,
                           status=200)
    # TODO fill out this stuff where the datalad commands would go (like the stuff in test_authenticate_crcns above)
