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

from ..http import HTTPDownloader
from ..http import DownloadError
from ..providers import Providers  # to test against crcns

from mock import patch, mock_open
from ...tests.utils import assert_in
from ...tests.utils import assert_false
from ...tests.utils import assert_raises
from ...tests.utils import ok_file_has_content
from ...tests.utils import serve_path_via_http, with_tree
from ...tests.utils import swallow_logs
from ...tests.utils import with_tempfile
from ...tests.utils import use_cassette

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
    download(furl, tfpath, overwrite=True)
    ok_file_has_content(tfpath, 'abc')

    # Some errors handling
    # XXX obscure mocking since impossible to mock write alone
    # and it still results in some warning being spit out
    with swallow_logs(), \
         patch('__builtin__.open', fake_open(write_=_raise_IOError)):
        assert_raises(DownloadError, download, furl, tfpath, overwrite=True)

    # TODO: access denied scenario
    # TODO: access denied detection


@use_cassette('fixtures/vcr_cassettes/crcns-alm-1-auth.yaml')
@with_tempfile(mkdir=True)
def test_authenticate_crcns(d):
    providers = Providers.from_config_files()
    url = 'https://portal.nersc.gov/project/crcns/download/alm-1/checksums.md5'
    fpath = opj(d, 'checksums.md5')
    crcns = providers.get_provider(url)
    downloader = crcns.get_downloader(url)
    downloader.download(url, path=d)
    with open(fpath) as f:
        content = f.read()
        assert_false("<form action=" in content)
        assert_in("datafiles/meta_data_files.tar.gz", content)
test_authenticate_crcns.tags = ['external-portal']

# TODO: test that download fails (even if authentication credentials are right) if form_url
# is wrong!