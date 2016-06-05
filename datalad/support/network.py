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

from collections import OrderedDict
from os.path import abspath, isabs

from six import string_types
from six import iteritems
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, urlunparse, ParseResult
from six.moves.urllib.parse import parse_qsl
from six.moves.urllib.parse import urlencode
from six.moves.urllib.error import URLError

from datalad.utils import on_windows

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


# TODO:  make it consistent/clear at what stage % encoding/decoding happens!
# now it is a mix!

#
# Useful functionality in requests.models
#  utils.requote_uri -- quote/unquote cycle to guarantee consistent appearance
#  RequestEncodingMixin._encode_params -- Will successfully encode parameters when passed as a dict or a list of ...
#  PreparedRequest().prepare_url(url, params) -- nicely cares about url encodings etc
#

#@auto_repr
# TODO: Well -- it is more of a URI than URL I guess
class URL(object):
    """A helper class to deal with URLs with some "magical" treats to facilitate use of "ssh" urls

    Intended to be a R/O object (i.e. no fields should be changed in-place)

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
        'path',  # 'params',
        'query',
        'fragment',
    )

    __slots__ = _FIELDS + ('_fields', '_str')

    def __init__(self, url=None, **kwargs):
        if url and (bool(url) == bool(kwargs)):
            raise ValueError(
                "Specify either url or breakdown from the fields, not both. "
                "Got url=%r, fields=%r" % (url, kwargs))

        # ok -- let's default to all of them being an empty string
        # Originally used None to signal no value but it complicated
        # operations since often needed first a check before e.g. doing
        # .startswith.  So more harmonic is just to store strings.
        # Not provided seems to be exactly as empty string, so Ok (stdlib
        # guys knew what they were doing ;)
        self._fields = {f: '' for f in self._FIELDS}
        if url:
            self._set_from_str(url)
        else:
            self._set_from_fields(**kwargs)

    @property
    def is_implicit(self):
        return self._fields['scheme'].endswith(':implicit')

    @property
    def fields(self):
        """Returns shallow copy of fields to ease manipulations"""
        return self._fields.copy()

    def __repr__(self):
        # since auto_repr doesn't support "non-0" values atm
        return "%s(%s)" % (
            self.__class__.__name__,
            ", ".join(["%s=%r" % (k, v)
                       for k, v in sorted(self._fields.items())
                       if v]))

    # Some custom __str__s for :implicit URLs
    def __str_ssh__(self):
        """Custom str for ssh:implicit"""
        url = urlunparse(self.to_pr())
        pref = 'ssh:implicit://'
        assert(url.startswith(pref))
        url = url[len(pref):]
        # and we should replace leading / after the hostname
        # Will preserve hostname as is, since we are trying to be as silly as ssh
        # where it tries to resolve hostnames with /
        lhostname = len(self.hostname)

        url = url[:lhostname] + \
              url[lhostname:].replace(
                  '/',
                  ':/' if self.path.startswith('/') else ':',
                  1)
        return url

    def __str_datalad__(self):
        """Custom str for datalad:implicit"""
        fields = self._fields.copy()
        fields['scheme'] = ''
        url = urlunparse(self._fields_to_pr(fields))
        if not fields['hostname']:
            # was of /// type
            url = '//' + url
        return url

    def __str_file__(self):
        """Custom str for datalad:implicit"""
        fields = self._fields.copy()
        fields['scheme'] = ''
        url = urlunparse(self._fields_to_pr(fields))
        return url

    # Lazily evaluated if _str was not set
    def __str__(self):
        if self._str is None:
            self._str = self._as_str()
        return self._str

    def _as_str(self):
        """Re-evaluate string repsentation"""

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
        fields = self._fields
        return any(fields.values())

    # for PY3
    __bool__ = __nonzero__

    #
    # Helpers to deal with internal structures and conversions
    #

    def _set_from_fields(self, **fields):
        unknown_fields = set(fields).difference(self._FIELDS)
        if unknown_fields:
            raise ValueError("Do not know about %s. Known fields are: %s"
                             % (unknown_fields, self._FIELDS))

        # encode dicts for query or fragment into
        for f in {'query', 'fragment'}:
            v = fields.get(f)
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
                fields[f] = ev

        self._fields.update(fields)
        self._str = None

    def to_pr(self):
        return self._fields_to_pr(self._fields)

    @classmethod
    def _fields_to_pr(cls, fields):
        """Recompose back fields dict to ParseResult"""
        netloc = fields['username'] or ''
        if fields['password']:
            netloc += ':' + fields['password']
        if netloc:
            netloc += '@'
        netloc += fields['hostname']
        if fields['port']:
            netloc += ':%s' % fields['port']

        pr_fields = {
            f: fields[f]
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

        # can't use just pr._asdict since we care to ask those properties
        # such as .port , .hostname etc
        # Forcing '' instead of None since those properties (.hostname), .password,
        # .username return None if not available and we decided to uniformize
        return {f: (getattr(pr, f) or '') for f in self._FIELDS}

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
            parts = _split_colon(url)
            if fields['path'] and '@' in fields['path'] or len(parts) > 1:
                # user@host:path/sp1
                # or host_name: (hence parts check)
                # TODO: we need a regex to catch those really, parts check is not suff
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
        self._str = url

        # well -- some urls might not unparse identically back
        # strictly speaking, but let's assume they do
        url_ = self._as_str()
        if url != url_:
            lgr.warning("Parsed version of url %r differs from original %r",
                        url_, url)

    #
    # Quick comparators
    #

    def __eq__(self, other):
        if not isinstance(other, URL):
            other = URL(other)
        return other._fields == self._fields

    def __ne__(self, other):
        return not (self == other)

    #
    # Access helpers
    #

    def _parse_qs(self, s, auto_delist=True):
        """Helper around parse_qs to strip unneeded 'list'ing etc and return a dict of key=values"""
        if not s:
            return {}
        out = OrderedDict(parse_qsl(s, 1))
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

    # def __getattribute__(self, item):
    #     if item.startswith('_') or item not in URL._FIELDS:
    #         return super(URL, self).__getattribute__(item)
    #     else:
    #         return self._fields[item]

# Bind properties to access fields (without overriding __getattr*)
# This one doesn't work -- I guess due to absent binding of f value
# to the context
#for f in URL._FIELDS:
#   setattr(URL, f, property(lambda self: self._fields[f]))
# These work but ugly duplication
# URL.hostname = property(lambda self: self._fields['hostname'])
# URL.path = property(lambda self: self._fields['path'])
# URL.query = property(lambda self: self._fields['query'])
# URL.scheme = property(lambda self: self._fields['scheme'])
# URL.fragment = property(lambda self: self._fields['fragment'])
# URL.username = property(lambda self: self._fields['username'])
# URL.password = property(lambda self: self._fields['password'])
# URL.port = property(lambda self: self._fields['port'])
for f in URL._FIELDS:
    exec("URL.%s = property(lambda self: self._fields['%s'])" % (f, f))


def _split_colon(s, maxsplit=1):
    """Split on unescaped colon"""
    return re.compile(r'(?<!\\):').split(s, maxsplit=maxsplit)


def parse_url_opts(url):
    """Given a string with url-style query, split into content before # and options as dict"""
    url = URL(url)
    # we need to filter out query and fragment to get the base url
    fields = url.fields
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


#### windows workaround ###
# TODO: There should be a better way
def get_local_file_url(fname):
    """Return OS specific URL pointing to a local file

    Parameters
    ----------
    fname : string
        Filename.  If not absolute, abspath is used
    """
    fname = fname if isabs(fname) else abspath(fname)
    if on_windows:
        fname_rep = fname.replace('\\', '/')
        furl = "file:///%s" % urlquote(fname_rep)
        lgr.debug("Replaced '\\' in file\'s url: %s" % furl)
    else:
        # TODO:  need to fix for all the encoding etc
        furl = str(URL(scheme='file', path=urlquote(fname)))
    return furl


def get_local_path_from_url(url):
    """If given a file:// URL, returns a local path, if possible.

    Raises `ValueError` if not possible, for example, if the URL
    scheme is different, or if the `host` isn't empty or 'localhost'

    The returned path is always absolute.
    """
    urlparts = urlsplit(url)
    if not urlparts.scheme == 'file':
        raise ValueError(
            "Non 'file://' URL cannot be resolved to a local path")
    if not (urlparts.netloc in ('', 'localhost', '::1') \
            or urlparts.netloc.startswith('127.')):
        raise ValueError("file:// URL does not point to 'localhost'")
    return urlunquote(urlparts.path)
