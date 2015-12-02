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