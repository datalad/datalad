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
#-----------------\____________________________________/------------------

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

import calendar
import email.utils
import gzip
import os
import re
import shutil
import time
import urllib2

from BeautifulSoup import BeautifulSoup
from StringIO import StringIO
from urlparse import urljoin, urlsplit

import logging
lgr = logging.getLogger('page2annex.network')

from joblib import Memory
memory = Memory(cachedir="/tmp/datagit", verbose=1)

def get_response_filename(url, response_info):
    if 'Content-Disposition' in response_info:
        # If the response has Content-Disposition, try to get filename from it
        cd = dict(map(
            lambda x: x.strip().split('=') if '=' in x else (x.strip(),''),
            response_info['Content-Disposition'].split(';')))
        if 'filename' in cd:
            filename = cd['filename'].strip("\"'")
            return filename
    return None


def get_response_stamp(url, response_info):
    size, mtime = None, None
    if 'Content-length' in response_info:
        size = int(response_info['Content-length'])
    if 'Last-modified' in response_info:
        mtime = calendar.timegm(email.utils.parsedate(
            response_info['Last-modified']))
    return dict(size=size, mtime=mtime, url=url)

def __download(url, filename=None, filename_only=False):
    # http://stackoverflow.com/questions/862173/how-to-download-a-file-using-python-in-a-smarter-way
    request = urllib2.Request(url)
    request.add_header('Accept-encoding', 'gzip,deflate')
    r = urllib2.urlopen(request)
    try:
        filename = filename or getFileName(url, r)
        if not filename_only:
            with open(filename, 'wb') as f:
                if r.info().get('Content-Encoding') == 'gzip':
                    buf = StringIO( r.read())
                    src = gzip.GzipFile(fileobj=buf)
                else:
                    src = r
                shutil.copyfileobj(src, f)
    finally:
        r.close()
    return filename

@memory.cache
def fetch_page(url, retries=3):
    lgr.debug("Fetching %s" % url)
    for t in xrange(retries):
        try:
            page = urllib2.urlopen(url).read()
            break
        except urllib2.URLError, e:
            lgr.warn("Received exception while reading %s: %s" % (url, e))
            if t == retries - 1:
                # if we have reached allowed number of retries -- reraise
                raise
    lgr.info("Fetched %d bytes page from %s" % (len(page), url))
    return page


# takes long -- so let's cache it
@memory.cache
def parse_urls(page):
    lgr.debug("Parsing out urls")
    soup = BeautifulSoup(page)
    return [(link.get('href'), link.text)
            for link in soup.findAll('a')]


def filter_urls(urls,
                include_href=None,
                exclude_href=None,
                include_href_a=None,
                exclude_href_a=None):

    if (not include_href) and not (include_href_a):
        include_href = '.*'               # include all

    # First do all includes explicitly and then excludes
    return [(url, a)
             for url, a in urls
                if url
                   and
                   ((include_href and re.search(include_href, url))
                     or (include_href_a and re.search(include_href_a, a))) \
                   and not
                   ((exclude_href and re.search(exclude_href, url))
                     or (exclude_href_a and re.search(exclude_href_a, a)))]


def download_url(url, incoming, subdir='', db_incoming=None, dry_run=False,
                 fast_mode=False):
    # TODO: relaxed mode? so no size/mtime stamps are collected, mere
    # presence is enough... uff -- too much of annex duplication? ;)
    # yeah -- but this is just a degenerate example
    updated = False
    # so we could check and remove it to keep it clean
    temp_full_filename = None

    if db_incoming is None:
        db_incoming = {}

    url_filename = os.path.basename(urlsplit(url).path)

    class ReturnSooner(Exception):
        pass

    try: # might RF -- this is just to not repeat the same return
        if dry_run:
            # we can only try to deduce from the url...
            filename = url_filename
            repo_filename = os.path.join(subdir, filename)
            full_filename = os.path.join(incoming, repo_filename)
            # and not really do much
            lgr.debug("Nothing else could be done for download in dry mode")
            raise ReturnSooner

        # TODO: add mode alike to 'relaxed' where we would not
        # care about content-deposition filename
        # http://stackoverflow.com/questions/862173/how-to-download-a-file-using-python-in-a-smarter-way
        request = urllib2.Request(url)

        # No traffic compression since we do not know how to identify
        # exactly either it has to be decompressed
        # request.add_header('Accept-encoding', 'gzip,deflate')
        #
        # TODO: think about stamping etc -- we seems to be redoing
        # what git-annex does for us already
        r = urllib2.urlopen(request)
        try:
            r_info = r.info()

            r_stamp = get_response_stamp(url, r_info)
            filename = get_response_filename(url, r_info) or url_filename
            repo_filename = os.path.join(subdir, filename)
            full_filename = os.path.join(incoming, repo_filename)

            if r_stamp['size']:
                lgr.debug("File %s is of size %d" % (repo_filename, r_stamp['size']))

            if url_filename != filename:
                lgr.debug("Filename in url %s differs from the load %s" % (url_filename, filename))

            # So we have filename -- time to figure out either we need to re-download it

            # db_incoming might maintain information even if file is not present, e.g.
            # if originally we haven't kept originals
            download = False

            def _compare_stamps(ofs, nfs, msg):
                """ofs -- old stamps, nfs -- new ones
                """
                download = False
                for k in ofs.keys():
                    n, o = nfs[k], ofs[k]
                    if n:
                        if o != n:
                            lgr.debug("Response %s %s differs from %s %s -- download"
                                      % (k, n, msg, o))
                            download = True
                return download

            if repo_filename in db_incoming:
                # if it is listed and has no stamps?
                # no -- it should have stamps -- we will place them there if none
                # was provided in HTML response. and we will redownload only
                # if any of those returned in HTTP header non-None and differ.
                # Otherwise we would assume that we have it
                # TODO: think if it is not too fragile
                download |= _compare_stamps(db_incoming.get(repo_filename),
                                            r_stamp, "previous")
            elif os.path.exists(full_filename):
                lgr.debug("File %s already exists under %s but no known stamps for it"
                          % (repo_filename, full_filename))

                # Verify time stamps etc
                # TODO: IF IT IS UNDER git-annex -- we can't do this
                file_stat = os.stat(full_filename)
                ex_stamp = dict(size=file_stat.st_size,
                                mtime=file_stat.st_mtime)

                download |= _compare_stamps(ex_stamp, r_stamp, "file stats")

            if not (repo_filename in db_incoming) and not os.path.exists(full_filename):
                lgr.debug("File %s is not known and doesn't exist" % repo_filename)
                download = True

            mtime = r_stamp['mtime']
            size = r_stamp['size']
            db_incoming[repo_filename] = dict(mtime=mtime, size=size, url=url)

            if fast_mode:
                lgr.debug("Not downloading -- fast mode")
                raise ReturnSooner

            if not download:
                lgr.debug("Not downloading for the reasons above stated")
                raise ReturnSooner

            lgr.info("Need to download file %s under %s" % (repo_filename, incoming))

            if os.path.exists(full_filename):
                lgr.debug("Removing previously existing file")
                # TODO

            # actual download -- quite plain -- may be worth to offload to
            # wget or curl for now?
            temp_full_filename = full_filename + '.download'

            if os.path.exists(temp_full_filename):
                raise RuntimeError("File %s should not be there yet" % temp_full_filename)

            try:
                # we might need the directory
                full_filename_dir = os.path.dirname(temp_full_filename)
                if not os.path.exists(full_filename_dir):
                    os.makedirs(full_filename_dir)

                with open(temp_full_filename, 'wb') as f:
                    # No magical decompression for now
                    if False: #r.info().get('Content-Encoding') == 'gzip':
                        buf = StringIO( r.read())
                        src = gzip.GzipFile(fileobj=buf)
                    else:
                        src = r
                    shutil.copyfileobj(src, f)
            except Exception, e:
                lgr.error("Failed to download: %s" % e)
                if os.path.exists(temp_full_filename):
                    lgr.info("Removing %s" % temp_full_filename)
                    os.unlink(temp_full_filename)
                raise

            if mtime:
                lgr.debug("Setting downloaded file's mtime to %s obtained from HTTP header"
                          % r_stamp['mtime'])
                os.utime(temp_full_filename, (time.time(), mtime))

            # Get stats and check on success
            # TODO: may be some would have MD5SUMS associated?
            updated = True

            # get mtime so we could update entry for our file
            file_stat = os.stat(temp_full_filename)
            new_mtime = file_stat.st_mtime
            new_size = file_stat.st_size

            if mtime and (new_mtime != mtime):
                lgr.debug("Set mtime differs for some reason.  Got %s (%s) while it should have been %s (%s)"
                          % (new_mtime, time.gmtime(new_mtime),
                             mtime, time.gmtime(mtime)))
                updated = False

            if size and (new_size != size):
                lgr.debug("Downloaded file differs in size.  Got %d while it should have been %d"
                          % (new_size, size))
                updated = False

            if updated:
                # TODO: we might like to git annex drop previously existed file etc
                os.rename(temp_full_filename, full_filename)

            else:
                pass
        finally:
            r.close()
            if temp_full_filename and os.path.exists(temp_full_filename):
                lgr.debug("Removing left-over %s of size %d"
                          % (temp_full_filename, os.stat(temp_full_filename).st_size))
                os.unlink(temp_full_filename)

    except ReturnSooner:
        # We have handled things already, just need to return
        pass

    return repo_filename, updated

