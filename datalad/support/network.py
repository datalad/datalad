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
from six import iteritems
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, urlunparse, ParseResult
from six.moves.urllib.parse import parse_qs
from six.moves.urllib.parse import urlencode
from six.moves.urllib.error import URLError

from datalad.utils import auto_repr
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

#@auto_repr
# TODO: Well -- it is more of a URI than URL I guess
class URL(object):
    """A helper class to deal with URLs with some "magical" treats to facilitate use of "ssh" urls

    Although largely decorating urlparse.ParseResult, it
    - doesn't mandate providing all parts of the URL
    - doesn't require netloc but rather asks for separate username, password, and hostname
    - TODO fragment and query are stored as (ordered) dictionaries of single entry elements
      (or otherwise encoded), with empty value being equivalent with no value.  If conversion
      to value=pair fails, string would be stored (so it it was indeed a url pointing to an id
      within a page)

    The idea is that this class should help to break apart a URL, while being
    able to rebuild itself into a string representation for reuse

    If scheme was implicit (e.g. "host:path" for ssh, or later may be "host::path" for
    rsync) ":implicit" suffix added to the scheme (so it is included in the repr of the
    instance "for free")

    Additional semantics we might want to somehow understand/map???
    - strings starting with // (no scheme) assumed to map to local central DataLad dataset,
      with `location` (if not empty) identifying the remote (super)dataset

    Implementation:
    - currently might be overengineered and could be simplified.  Internally keeps
      all values as attributes, but for manipulation in dict (called fields) and converts
      back and forth to ParseResults
    So after we agree on viability of the approach  and collect enough tests we can simplify
    """

    # fields with their defaults
    _FIELDS = (
        'scheme',
        'username',
        'password',
        'hostname', 'port',
        'path', # 'params',
        'query',
        'fragment',
    )

    __slots__ = _FIELDS

    def __init__(self, url=None, **kwargs):
        if url and (bool(url) == bool(kwargs)):
            raise ValueError(
                "Specify either url or breakdown from the fields, not both. "
                "Got url=%r, fields=%r" % (url, kwargs))

        if url:
            self._set_from_str(url)
        else:
            self._set_from_fields(**kwargs)

    @property
    def is_implicit(self):
        return self.scheme and self.scheme.endswith(':implicit')

    def __repr__(self):
        # since auto_repr doesn't support "non-0" values atm
        fields = self.to_fields()
        return "%s(%s)" % (
            self.__class__.__name__,
            ", ".join(["%s=%r" % (k, v) for k, v in sorted(fields.items()) if v]))

    # Some custom __str__s for :implicit URLs
    def __str_ssh__(self):
        """Custom str for ssh:implicit"""
        url = urlunparse(self.to_pr())
        pref = 'ssh:implicit://'
        assert(url.startswith(pref))
        url = url[len(pref):]
        # and we should replace leading /
        url = url.replace('/',
                          ':/' if self.path and self.path.startswith('/') else ':',
                          1)
        return url

    def __str_datalad__(self):
        """Custom str for datalad:implicit"""
        fields = self.to_fields()
        fields['scheme'] = None
        url = urlunparse(self._fields_to_pr(fields))
        if not self.hostname:
            # was of /// type
            url = '//' + url
        return url

    def __str_file__(self):
        """Custom str for datalad:implicit"""
        fields = self.to_fields()
        fields['scheme'] = None
        url = urlunparse(self._fields_to_pr(fields))
        return url

    def __str__(self):
        if not self.is_implicit:
            return urlunparse(self.to_pr())
        else:
            base_scheme = self.scheme.split(':', 1)[0]
            try:
                __str__ = getattr(self, '__str_%s__' % base_scheme)
            except AttributeError:
                raise ValueError("Don't know how to convert %s:implicit into str"
                                 % base_scheme)
            return __str__()

    #
    # If any field is specified, URL is not considered 'False', i.e.
    # non-existing, although may be we could/shout omit having only
    # scheme or port specified since it doesn't point to any useful
    # location
    #

    def __nonzero__(self):
        return any(getattr(self, f) for f in self._FIELDS)

    #
    # Helpers to deal with internal structures and conversions
    #

    def _set_from_fields(self, **kwargs):
        unknown_fields = set(kwargs).difference(self._FIELDS)
        if unknown_fields:
            raise ValueError("Do not know about %s. Known fields are: %s"
                             % (unknown_fields, self._FIELDS))

        # encode dicts for query or fragment into
        for f in {'query', 'fragment'}:
            v = kwargs.get(f)
            if isinstance(v, dict):

                ev = urlencode(v)
                # / is reserved char within query
                if f == 'fragment' and '%2F' not in str(v):
                    # but seems to be ok'ish within the fragment which is
                    # the last element of URI and anyways used only by the
                    # client (i.e. by us here if used to compose the URL)
                    # so let's return / back for clarity if there were no
                    # awkward %2F to startwith
                    ev = ev.replace('%2F', '/')
                kwargs[f] = ev

        # set them to provided values
        for f in self._FIELDS:
            setattr(self, f, kwargs.get(f, None))

    def to_fields(self):
        return {f: getattr(self, f) for f in self._FIELDS}

    def to_pr(self):
        return self._fields_to_pr(self.to_fields())

    @classmethod
    def _fields_to_pr(cls, fields):
        """Recompose back fields dict to ParseResult"""
        netloc = fields['username'] or ''
        if fields['password']:
            netloc += ':' + fields['password']
        if netloc:
            netloc += '@'
        netloc += fields['hostname'] if fields['hostname'] else ''
        if fields['port']:
            netloc += ':%s' % fields['port']

        pr_fields = {
            f: (fields[f] if fields[f] is not None else '')
            for f in cls._FIELDS
            if f not in ('hostname', 'password', 'username', 'port')
        }
        pr_fields['netloc'] = netloc
        pr_fields['params'] = ''

        return ParseResult(**pr_fields)

    def _pr_to_fields(self, pr):
        """ParseResult is a tuple so immutable, which complicates adjusting it

        This function converts ParseResult into dict"""

        if pr.params:
            lgr.warning("ParseResults contains params %r, which will be ignored"
                        % (pr.params,))

        def getattrnone(f):
            """Just a little helper so we could just map and get None if empty"""
            v = getattr(pr, f)
            return v if v else None

        return {f: getattrnone(f) for f in self._FIELDS}

    def _set_from_str(self, url):
        fields = self._pr_to_fields(urlparse(url))
        lgr.log(5, "Parsed url %s into fields %s" % (url, fields))

        # Special treatments
        # file:///path should stay file:
        if fields['scheme'] and fields['scheme'] not in {'file'} \
                and not fields['hostname']:
            # dl+archive:... or just for ssh   hostname:path/p1
            if '+' not in fields['scheme']:
                fields['hostname'] = fields['scheme']
                fields['scheme'] = 'ssh:implicit'
                lgr.log(5, "Assuming ssh style url, adjusted: %s" % (fields,))

        if not fields['scheme'] and not fields['hostname']:
            if fields['path'] and '@' in fields['path']:
                # user@host:path/sp1
                fields['scheme'] = 'ssh:implicit'
            elif url.startswith('//'):
                # e.g. // or ///path
                fields['scheme'] = 'datalad:implicit'
            else:
                fields['scheme'] = 'file:implicit'

        if not fields['scheme'] and fields['hostname']:
            # e.g. //a/path
            fields['scheme'] = 'datalad:implicit'

        if fields['scheme'] in ('ssh:implicit',) and not fields['hostname']:
            if fields['query'] or fields['fragment']:
                # actually might be legit with some obscure filenames,
                # so TODO for correct -- probably just re.match the entire url
                # into fields
                raise ValueError("Thought that this url would point to host:path but got query and fragments: %s"
                                 % str(fields))
            #  user@hostname[:path] --> ssh://user@hostname[/path]
            parts = _split_colon(url)
            fields['scheme'] = 'ssh:implicit'
            if len(parts) == 2:
                fields['hostname'] = parts[0]
                fields['path'] = parts[1]
            # hostname might still contain the password
            if fields['hostname'] and '@' in fields['hostname']:
                fields['username'], fields['hostname'] = fields['hostname'].split('@', 1)
            lgr.log(5, "Detected ssh style url, adjusted: %s" % (fields,))

        self._set_from_fields(**fields)

        # well -- some urls might not unparse identically back
        # strictly speaking, but let's assume they do
        url_rec = str(self)
        # print "REPR: ", repr(self)
        if url != url_rec:
            lgr.warning("Parsed version of url %r differs from original %r",
                        url_rec, url)

    #
    # Quick comparators
    #

    def __eq__(self, other):
        if not isinstance(other, URL):
            other = URL(other)
        return all(getattr(other, f) == getattr(self, f) for f in self._FIELDS)

    def __ne__(self, other):
        return not (self == other)

    #
    # Access helpers
    #

    def _parse_qs(self, s, auto_delist=True):
        """Helper around parse_qs to strip unneeded 'list'ing etc and return a dict of key=values"""
        if not s:
            return {}
        out = parse_qs(s, 1)
        if not auto_delist:
            return out
        for k in out:
            v = out[k]
            if isinstance(v, list) and len(v) == 1:
                v = v[0]
                out[k] = None if v == '' else v
        return out

    @property
    def query_dict(self):
        return self._parse_qs(self.query)

    @property
    def fragment_dict(self):
        return self._parse_qs(self.fragment)


def _split_colon(s, maxsplit=1):
    """Split on unescaped colon"""
    return re.compile(r'(?<!\\):').split(s, maxsplit=maxsplit)


def parse_url_opts(url):
    """Given a string with url-style query, split into content before # and options as dict"""
    url = URL(url)
    # we need to filter out query and fragment to get the base url
    fields = url.to_fields()
    fields.pop('query')
    fields.pop('fragment')
    opts = url.query_dict
    return str(URL(**fields)), opts


# TODO: should we just define URL.good_for_git or smth like that? ;)
# although git also understands regular paths
def is_url(s):
    """Returns whether a string looks like something what datalad should treat as a URL

    This includes ssh "urls" which git understands.
    """
    try:
        url = URL(s)
    except:
        return False
    implicit = url.is_implicit
    scheme = url.scheme
    return scheme in {'ssh:implicit'} or (not implicit and bool(url))


