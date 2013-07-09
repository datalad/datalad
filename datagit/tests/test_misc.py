#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
#------------------------- =+- Python script -+= -------------------------
"""

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

from .utils import *

from ..api import *
from ..cmd import getstatusoutput
from ..network import filter_urls, get_response_stamp, download_url, \
     fetch_page, parse_urls
from ..config import get_default_config
from ..main import rock_and_roll

def test_filter_urls():
    urls = [('/x.nii.gz', 'bogus'),
            ('x.tar.gz', None),
            ('y', None)]
    eq_(filter_urls(urls, "^x\..*"), [urls[1]])
    eq_(filter_urls(urls, "^[xy]"), urls[1:])
    eq_(filter_urls(urls, "\.gz", "\.nii"),
           [urls[1]])
    eq_(filter_urls(urls, exclude_href="x"),
           [urls[2]])
    eq_(filter_urls(urls, "^[xy]"), urls[1:])

def test_get_response_stamp():
    r = get_response_stamp({'Content-length': '101',
                            'Last-modified': 'Wed, 01 May 2013 03:02:00 GMT'})
    eq_(r['size'], 101)
    eq_(r['mtime'], 1367377320)


def test_download_url():
    # let's simulate the whole scenario
    fd, fname = tempfile.mkstemp()
    dout = fname + '-d'
    # TODO move tempfile/tempdir setup/cleanup into fixture(s)
    os.mkdir(dout)
    os.write(fd, "How do I know what to say?\n")
    os.close(fd)

    filename, full_filename, updated = download_url("file://%s" % fname, dout)
    ok_(updated)
    # check if stats are the same
    s, s_ = os.stat(fname), os.stat(full_filename)
    eq_(s.st_size, s_.st_size)
    # at least to a second
    eq_(int(s.st_mtime), int(s_.st_mtime))

    # and if again -- should not be updated
    filename, full_filename, updated = download_url("file://%s" % fname, dout)
    ok_(not updated)

    # but it should if we remove it
    os.unlink(full_filename)
    filename, full_filename, updated = download_url("file://%s" % fname, dout)
    ok_(updated)
    # check if stats are the same
    s_ = os.stat(full_filename)
    eq_(s.st_size, s_.st_size)
    eq_(int(s.st_mtime), int(s_.st_mtime))

    # and what if we maintain url_stamps
    url_stamps = {}
    os.unlink(full_filename)
    filename, full_filename, updated = download_url("file://%s" % fname, dout, url_stamps)
    ok_(updated)
    ok_(full_filename in url_stamps)
    s_ = os.stat(full_filename)
    eq_(int(s.st_mtime), int(s_.st_mtime))
    eq_(int(s.st_mtime), url_stamps[full_filename]['mtime'])
    print filename, full_filename, url_stamps,

    # and if we remove it but maintain information that we think it
    # exists -- we should skip it ATM
    os.unlink(full_filename)
    filename, full_filename, updated = download_url("file://%s" % fname, dout, url_stamps)
    ok_(not updated)
    ok_(full_filename in url_stamps)
    assert_raises(OSError, os.stat, full_filename)

    os.unlink(fname)
    rmtree(dout, True)


@with_tree((('test.txt', 'abracadabra'),
            ('1.tar.gz', (
               ('1f.txt', '1f load'),
               ('d', (('1d', ''),
                      )),
               ))),
           dir=os.curdir,
           prefix='.tmp-page2annex-')
@serve_path_via_http()
def test_parse_urls_recurse(url):
    dout = tempfile.mkdtemp()
    page = fetch_page(url)
    urls = parse_urls(page)

    cfg = get_default_config(dict(
        DEFAULT=dict(
            incoming=dout,
            public=dout,
            description="test",
            ),
        files=dict(
            directory='files', # TODO: recall what was wrong with __name__ substitution, look into fail2ban/client/configparserinc.py
            url=url)))

    stats1 = rock_and_roll(cfg, dry_run=False)
    assert_greater(stats1['annex_updates'], 0)   # TODO: more specific
    eq_(stats1['downloads'], 2)

    # Let's repeat -- there should be no downloads/updates
    stats2 = rock_and_roll(cfg, dry_run=False)
    eq_(stats2['annex_updates'], 0)
    eq_(stats2['downloads'], 0)

    # TODO: verify that the structure as it should be

    #print dout, "URLS: ", urls
    rmtree(dout, True)
    #print dout


