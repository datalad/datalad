# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import calendar
import email.utils
import gzip
import os
import re
import shutil
import time

from six import string_types
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, urlunparse
from six.moves.urllib.error import URLError

# TODO not sure what needs to use `six` here yet
import requests

import logging
lgr = logging.getLogger('datalad.network')


def get_response_disposition_filename(s):
    """Given a string s as from HTTP Content-Disposition field in the response
    return possibly present filename if any
    """
    if not s:
        return None
    # If the response has Content-Disposition, try to get filename from it
    cd = dict(map(
        lambda x: x.strip().split('=') if '=' in x else (x.strip(),''),
        s.split(';')))
    if 'filename' in cd:
        filename = cd['filename'].strip("\"'")
        return filename
    return None


def get_url_disposition_filename(url, headers=None):
    """Get filename as possibly provided by the server in Content-Disposition
    """
    if headers is None:
        request = Request(url)
        r = retry_urlopen(request)
        # things are different in requests
        if 'requests.' in str(r.__class__):
            headers = r.headers
        else:
            headers = r.info()
    else:
        r = None
    try:
        return get_response_disposition_filename(headers.get('Content-Disposition', ''))
    finally:
        if r:
            r.close()


def get_url_straight_filename(url, strip=[], allowdir=False):
    """Get file/dir name of the last path component of the URL

    Parameters
    ----------
    strip: list, optional
      If provided, listed names will not be considered and their
      parent directory will be selected
    allowdir: bool, optional
      If url points to a "directory" (ends with /), empty string
      would be returned unless allowdir is True, in which case the
      name of the directory would be returned
    """
    path = urlunquote(urlsplit(url).path)
    path_parts = path.split('/')

    if allowdir:
        # strip empty ones
        while len(path_parts) > 1 and not path_parts[-1]:
            path_parts = path_parts[:-1]

    if strip:
        while path_parts and path_parts[-1] in strip:
            path_parts = path_parts[:-1]

    if path_parts:
        return path_parts[-1]
    else:
        return None

def get_url_filename(url, headers=None, strip=[]):
    """Get filename from the url, first consulting server about Content-Disposition
    """
    filename = get_url_disposition_filename(url, headers)
    if filename:
        return filename
    return get_url_straight_filename(url, strip=[])

def get_url_response_stamp(url, response_info):
    size, mtime = None, None
    if 'Content-length' in response_info:
        size = int(response_info['Content-length'])
    if 'Last-modified' in response_info:
        mtime = calendar.timegm(email.utils.parsedate(
            response_info['Last-modified']))
    return dict(size=size, mtime=mtime, url=url)


def get_tld(url):
    """Return top level domain from a url

    Parameters
    ----------
    url : str
    """
    # maybe use this instead to be safe:  https://pypi.python.org/pypi/tld
    if not url.strip():
        raise ValueError("Empty URL has no TLD")
    rec = urlsplit(url)
    if not rec.netloc:
        if not rec.scheme:
            # There were no scheme provided thus netloc was empty -- must have been a simple 'path like'
            return url.split('/', 1)[0]
        else:
            raise ValueError("It seems that only the scheme was provided without the net location/TLD")
    return rec.netloc

from email.utils import parsedate_tz, mktime_tz
def rfc2822_to_epoch(datestr):
    """Given rfc2822 date/time format, return seconds since epoch"""
    return mktime_tz(parsedate_tz(datestr))

import calendar
from datetime import datetime
def iso8601_to_epoch(datestr):
    return calendar.timegm(datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%S.%fZ").timetuple())

def __urlopen_requests(url, header_vals=None):
    # XXX Workaround for now for ... broken code
    if isinstance(url, Request):
        url = url.get_full_url()
    return requests.Session().get(url)



def retry_urlopen(url, retries=3):
    for t in range(retries):
        try:
            return __urlopen_requests(url)
        except URLError as e:
            lgr.warn("Received exception while reading %s: %s" % (url, e))
            if t == retries - 1:
                # if we have reached allowed number of retries -- reraise
                raise


def is_url_quoted(url):
    """Return either URL looks being already quoted
    """
    try:
        url_ = urlunquote(url)
        return url != url_
    except:  # problem with unquoting -- then it must be wasn't quoted (correctly)
        return False


def same_website(url_rec, u_rec):
    """Decide either a link leads to external site

    Parameters
    ----------
    url_rec: ParseResult
      record for original url
    u_rec: ParseResult
      record for new url
    """
    if isinstance(url_rec, string_types):
        url_rec = urlparse(url_rec)
    if isinstance(u_rec, string_types):
        u_rec = urlparse(u_rec)
    return (url_rec.netloc == u_rec.netloc)
    # todo: collect more of sample cases.
    # disabled below check while working on ratholeradio, since links
    # could go to the parent and that is ok.  Figure out when it was
    # desired not to go to the parent -- we might need explicit option
    # and u_rec.path.startswith(url_rec.path)):


def dlurljoin(u_path, url):
    url_rec = urlparse(url)  # probably duplicating parsing :-/ TODO
    if url_rec.scheme:
        # independent full url, so just return it
        return url
    if u_path.endswith('/'):  # should here be also a scheme use?
        if url.startswith('/'): # jump to the root
            u_path_rec = urlparse(u_path)
            return urljoin(urlunparse((u_path_rec.scheme, u_path_rec.netloc, '','','','')), url)
        else:
            return os.path.join(u_path, url)
    # TODO: recall where all this dirname came from and bring into the test
    return urljoin(os.path.dirname(u_path) + '/', url)


# TODO should it be a node maybe?
class SimpleURLStamper(object):
    """Gets a simple stamp about the URL: {url, time, size} of whatever was provided in the header
    """
    def __init__(self, mode='full'):
        self.mode = mode

    def __call__(self, url):
        # Extracted from above madness
        # TODO: add mode alike to 'relaxed' where we would not
        # care about content-disposition filename
        # http://stackoverflow.com/questions/862173/how-to-download-a-file-using-python-in-a-smarter-way
        request = Request(url)

        # No traffic compression since we do not know how to identify
        # exactly either it has to be decompressed
        # request.add_header('Accept-encoding', 'gzip,deflate')
        #
        # TODO: think about stamping etc -- we seems to be redoing
        # what git-annex does for us already... not really
        r = retry_urlopen(request)
        try:
            r_info = r.info()
            r_stamp = get_url_response_stamp(url, r_info)

            return dict(mtime=r_stamp['mtime'], size=r_stamp['size'], url=url)
        finally:
            r.close()
