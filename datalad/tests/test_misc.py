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

from os.path import join

from .utils import *

from ..api import *
from ..support.network import filter_urls, get_url_response_stamp, download_url, is_url_quoted

def test_is_url_quoted():
    ok_(is_url_quoted('%22%27%3ba&b&cd|'))
    ok_(not is_url_quoted('a b'))

def test_filter_urls():
    urls = [('/x.nii.gz', 'bogus', None),
            ('x.tar.gz', None, None),
            ('y', None, None)]
    eq_(filter_urls(urls, "^x\..*"), [urls[1]])
    eq_(filter_urls(urls, "^[xy]"), urls[1:])
    eq_(filter_urls(urls, "\.gz", "\.nii"),
           [urls[1]])
    eq_(filter_urls(urls, exclude_href="x"),
           [urls[2]])
    eq_(filter_urls(urls, "^[xy]"), urls[1:])

def test_get_response_stamp():
    r = get_url_response_stamp("http://www.example.com/1.dat",
                           {'Content-length': '101',
                            'Last-modified': 'Wed, 01 May 2013 03:02:00 GMT'})
    eq_(r['size'], 101)
    eq_(r['mtime'], 1367377320)
    eq_(r['url'], "http://www.example.com/1.dat")


def test_download_url():
    # let's simulate the whole scenario
    fd, fname = tempfile.mkstemp()
    dout = fname + '-d'
    # TODO move tempfile/tempdir setup/cleanup into fixture(s)
    os.mkdir(dout)
    os.write(fd, "How do I know what to say?\n")
    os.close(fd)

    # Let's assume absent subdirectory
    #repo_filename, downloaded, updated, downloaded_size
    repo_filename, downloaded, updated, size \
        = download_url("file://%s" % fname, dout)
    ok_(updated)
    ok_(downloaded)
    # check if stats are the same
    s, s_ = os.stat(fname), os.stat(join(dout, repo_filename))
    eq_(s.st_size, s_.st_size)
    # at least to a second
    eq_(int(s.st_mtime), int(s_.st_mtime))

    # and if again -- should not be updated
    repo_filename, downloaded, updated, size = \
        download_url("file://%s" % fname, dout)
    ok_(not updated)
    ok_(not downloaded)

    # but it should if we remove it
    os.unlink(join(dout, repo_filename))
    repo_filename, downloaded, updated, size = \
        download_url("file://%s" % fname, dout)
    full_filename = join(dout, repo_filename)
    ok_(updated)
    ok_(downloaded)
    # check if stats are the same
    s_ = os.stat(full_filename)
    eq_(s.st_size, s_.st_size)
    eq_(int(s.st_mtime), int(s_.st_mtime))
    eq_(s.st_size, size)

    # and what if we maintain db_incoming
    db_incoming = {}
    os.unlink(full_filename)
    repo_filename, downloaded, updated, size = \
        download_url("file://%s" % fname, dout, db_incoming=db_incoming)
    full_filename = join(dout, repo_filename)
    ok_(updated)
    ok_(downloaded)
    ok_(repo_filename in db_incoming,
        "db_incoming should have the %s. Got %s" % (repo_filename, str(db_incoming)))
    s_ = os.stat(full_filename)
    eq_(int(s.st_mtime), int(s_.st_mtime))
    eq_(int(s.st_mtime), db_incoming[repo_filename]['mtime'])

    # and if we remove it but maintain information that we think it
    # exists -- we should skip it ATM
    os.unlink(full_filename)
    repo_filename, downloaded, updated, size = \
        download_url("file://%s" % fname, dout, db_incoming=db_incoming)
    full_filename = join(dout, repo_filename)
    ok_(not updated)
    ok_(not downloaded)
    ok_(repo_filename in db_incoming)
    assert_raises(OSError, os.stat, full_filename)

    os.unlink(fname)
    rmtree(dout, True)
