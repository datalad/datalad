# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
lgr = logging.getLogger('datalad.network')

lgr.log(5, "Importing support.network")
import calendar
import email.utils
import os
import pickle
import re
import time
import iso8601

from hashlib import md5
from collections import OrderedDict
from os.path import abspath, isabs
from os.path import join as opj
from os.path import dirname
from ntpath import splitdrive as win_splitdrive

from six import string_types
from six import iteritems
from six.moves.urllib.parse import urlsplit
from six.moves.urllib.request import Request
from six.moves.urllib.parse import quote as urlquote, unquote as urlunquote
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunparse, ParseResult
from six.moves.urllib.parse import parse_qsl
from six.moves.urllib.parse import urlencode
from six.moves.urllib.error import URLError

from datalad.dochelpers import exc_str
from datalad.utils import on_windows
from datalad.utils import assure_dir
from datalad.consts import DATASETS_TOPURL
from datalad import cfg

# TODO not sure what needs to use `six` here yet
# !!! Lazily import requests where needed -- needs 30ms or so
# import requests


def get_response_disposition_filename(s):
    """Given a string s as from HTTP Content-Disposition field in the response
    return possibly present filename if any
    """
    if not s:
        return None
    # If the response has Content-Disposition, try to get filename from it
    cd = map(
        lambda x: x.strip().split('=', 1) if '=' in x else [x.strip(), ''],
        s.split(';')
    )
    # unify the key to be lower case and make it into a dict
    cd = dict([[x[0].lower()] + x[1:] for x in cd])
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


def get_url_straight_filename(url, strip=None, allowdir=False):
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


def get_url_filename(url, headers=None, strip=None):
    """Get filename from the url, first consulting server about Content-Disposition
    """
    filename = get_url_disposition_filename(url, headers)
    if filename:
        return filename
    return get_url_straight_filename(url, strip=strip)


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


def iso8601_to_epoch(datestr):
    """Given ISO 8601 date/time format, return in seconds since epoch

    iso8601 is used to parse properly the time zone information, which
    can't be parsed with standard datetime strptime
    """
    return calendar.timegm(iso8601.parse_date(datestr).timetuple())


def __urlopen_requests(url):
    # XXX Workaround for now for ... broken code
    if isinstance(url, Request):
        url = url.get_full_url()
    from requests import Session
    return Session().get(url)


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
        # MIH: ValueError?
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
        if url.startswith('/'):  # jump to the root
            u_path_rec = urlparse(u_path)
            return urljoin(urlunparse(
                (u_path_rec.scheme, u_path_rec.netloc, '', '', '', '')), url)
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

def _guess_ri_cls(ri):
    """Factory function which would determine which type of a ri a provided string is"""
    TYPES = {
        'url': URL,
        'ssh':  SSHRI,
        'file': PathRI,
        'datalad': DataLadRI
    }
    # go in exotic mode if this is an absolute windows path
    win_split = win_splitdrive(ri)
    # we need a drive and a path, otherwise this could be a false positive
    if win_split[0] and win_split[1]:
        # OMG we got something from windows
        lgr.log(5, "Detected file ri")
        return TYPES['file']

    # We assume that it is a URL and parse it. Depending on the result
    # we might decide that it was something else ;)
    fields = URL._pr_to_fields(urlparse(ri))
    lgr.log(5, "Parsed ri %s into fields %s" % (ri, fields))
    type_ = 'url'
    # Special treatments
    # file:///path should stay file:
    if fields['scheme'] and fields['scheme'] not in {'file'} \
            and not fields['hostname']:
        # dl+archive:... or just for ssh   hostname:path/p1
        if '+' not in fields['scheme']:
            type_ = 'ssh'
            lgr.log(5, "Assuming ssh style ri, adjusted: %s" % (fields,))

    if not fields['scheme'] and not fields['hostname']:
        parts = _split_colon(ri)
        if fields['path'] and '@' in fields['path'] or len(parts) > 1:
            # user@host:path/sp1
            # or host_name: (hence parts check)
            # TODO: we need a regex to catch those really, parts check is not suff
            type_ = 'ssh'
        elif ri.startswith('//'):
            # e.g. // or ///path
            type_ = 'datalad'
        else:
            type_ = 'file'

    if not fields['scheme'] and fields['hostname']:
        # e.g. //a/path
        type_ = 'datalad'

    cls = TYPES[type_]
    # just parse the ri according to regex matchint ssh "ri" specs
    lgr.log(5, "Detected %s ri" % type_)
    return cls


class RI(object):
    """Resource Identifier - base class and a factory for URL, SSHRI, etc

    Intended to be a R/O object (i.e. no fields should be changed in-place).
    Subclasses define specific collections of fields they care about in _FIELDS
    class variable.
    The idea is that this class should help to break apart a URL, while being
    able to rebuild itself into a string representation for reuse

    `RI` could be used as factory, whenever type of the resource is unknown and
    must be guessed from the string representation.  One of the subclasses will be
    provided as output, e.g.

    >>> RI('http://example.com')
    URL(hostname='example.com', scheme='http')
    >>> RI('example.com:path')
    SSHRI(hostname='example.com', path='path')
    """

    # All of the subclasses will provide path
    _FIELDS = (
        'path',
    )

    __slots__ = _FIELDS + ('_fields', '_str')

    def __new__(cls, ri=None, **kwargs):
        """Used as a possible factory for known RI types

        Returns
        -------
        RI
           uninitialized RI object of appropriate class with _str
           set to string representation if was provided

        """
        if cls is RI and ri is not None:
            # RI class was used as a factory
            cls = _guess_ri_cls(ri)

        if cls is RI:
            # should we fail or just pretend we are nothing??? ;-) XXX
            raise ValueError("Could not deduce RI type for %r" % (ri,))

        ri_obj = super(RI, cls).__new__(cls)
        # Store internally original str
        ri_obj._str = ri
        return ri_obj

    def __init__(self, ri=None, **fields):
        """
        Parameters
        ----------
        ri: str, optional
          String version of a resource specific for this class.  If you would like
          a type of the resource be deduced, use RI(ri)
        **fields: dict, optional
          The values for the fields defined in _FIELDS class variable.
        """
        if ri and (bool(ri) == bool(fields)):
            raise ValueError(
                "Specify either ri or breakdown from the fields, not both. "
                "Got ri=%r, fields=%r" % (ri, fields))

        self._fields = self._get_blank_fields()
        if ri is not None:
            fields = self._str_to_fields(ri)
        self._set_from_fields(**fields)

        # If was initialized from a string representation
        if self._str is not None:
            # well -- some ris might not unparse identically back
            # strictly speaking, but let's assume they do
            ri_ = self.as_str()
            if ri != ri_:
                lgr.debug("Parsed version of %s %r differs from original %r",
                          self.__class__.__name__, ri_, ri)

    @classmethod
    def _get_blank_fields(cls, **fields):
        return OrderedDict(((f, fields.get(f, '')) for f in cls._FIELDS))

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

    # Lazily evaluated if _str was not set
    def __str__(self):
        if self._str is None:
            self._str = self.as_str()
        return self._str

    @classmethod
    def from_str(cls, ri_str):
        obj = cls(**cls._str_to_fields(ri_str))
        obj._str = ri_str
        return obj

    @property
    def localpath(self):
        # by default RIs point to remote locations
        raise ValueError("%s points to remote location" % self)

    # Apparently doesn't quite play nicely with multiple inheritence for MixIn'
    # of regexp based URLs
    #@abstractmethod
    #@classmethod
    #def _str_to_fields(cls, ri_str):
    #    raise NotImplementedError

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
            raise ValueError("Do not know about %s. Known fields for %s are: %s"
                             % (unknown_fields, self.__class__, self._FIELDS))

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
                    # awkward %2F to startswith
                    ev = ev.replace('%2F', '/')
                fields[f] = ev

        self._fields.update(fields)

    #
    # Quick comparators
    #

    def __eq__(self, other):
        if not isinstance(other, RI):
            other = RI(other)
        return isinstance(other, self.__class__) and dict(other._fields) == dict(self._fields)

    def __ne__(self, other):
        return not (self == other)

    def __getattribute__(self, item):
        if item.startswith('_') or item not in self._FIELDS:
            return super(RI, self).__getattribute__(item)
        else:
            return self._fields[item]

    def __setattr__(self, item, value):
        if item.startswith('_') or item not in self._FIELDS:
            super(RI, self).__setattr__(item, value)
        else:
            self._fields[item] = value
            self._str = None


class URL(RI):
    """Universal resource locator

    Although largely decorating urlparse.ParseResult, it
    - doesn't mandate providing all parts of the URL
    - doesn't require netloc but rather asks for separate username, password, and hostname
    """

    _FIELDS = RI._FIELDS + (
        'scheme',
        'username',
        'password',
        'hostname', 'port',
        'query',
        'fragment',
    )

    def as_str(self):
        """Render URL as a string"""
        return urlunparse(self.to_pr())

    @classmethod
    def _str_to_fields(cls, url_str):
        fields = URL._pr_to_fields(urlparse(url_str))
        fields['path'] = urlunquote(fields['path'])
        return fields

    def to_pr(self):
        """Convert URL to urlparse.ParseResults namedtuple"""
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
            if fields['hostname'].count(':') >= 2:
                # ipv6 -- need to enclose in []
                netloc = '[%s]:%s' % (netloc, fields['port'])
            else:
                netloc += ':%s' % fields['port']

        pr_fields = {
            f: fields[f]
            for f in cls._FIELDS
            if f not in ('hostname', 'password', 'username', 'port')
        }
        pr_fields['netloc'] = netloc
        pr_fields['params'] = ''
        # We need to quote the path
        pr_fields['path'] = urlquote(pr_fields['path'])
        # TODO: figure out what to do with query/fragment... one step at a time
        return ParseResult(**pr_fields)

    @classmethod
    def _pr_to_fields(cls, pr):
        """ParseResult is a tuple so immutable, which complicates adjusting it

        This function converts ParseResult into dict"""

        if pr.params:
            lgr.warning("ParseResults contains params %r, which will be ignored"
                        % (pr.params,))

        hostname_port = pr.netloc.split('@')[-1]
        is_ipv6 = hostname_port.count(':') >= 2
        # can't use just pr._asdict since we care to ask those properties
        # such as .port , .hostname etc
        # Forcing '' instead of None since those properties (.hostname), .password,
        # .username return None if not available and we decided to uniformize
        if is_ipv6:
            rem = re.match('\[(?P<hostname>.*)\]:(?P<port>\d+)', hostname_port)
            if rem:
                hostname, port = rem.groups()
                port = int(port)
            else:
                hostname, port = hostname_port, ''

            def _getattr(pr, f):
                """Helper for custom handling in case of ipv6 addresses which blows
                stock ParseResults logic"""
                if f == 'port':
                    # for now not supported at all, so
                    return port
                elif f == 'hostname':
                    return hostname
                else:
                    return getattr(pr, f)
        else:
            _getattr = getattr

        return {f: (_getattr(pr, f) or '') for f in cls._FIELDS}

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

    @property
    def localpath(self):
        if self.scheme != 'file':
            raise ValueError(
                "Non 'file://' URL cannot be resolved to a local path")
        hostname = self.hostname
        if not (hostname in (None, '', 'localhost', '::1')
                or hostname.startswith('127.')):
            raise ValueError("file:// URL does not point to 'localhost'")
        return self.path


class PathRI(RI):
    """RI pointing to a (local) file/directory"""
    def as_str(self):
        return self.path

    @classmethod
    def _str_to_fields(cls, url_str):
        return dict(path=url_str)

    @property
    def localpath(self):
        return self.path


class RegexBasedURLMixin(object):
    """Base class for URLs which we could simple parse using regular expressions"""

    _REGEX = None

    # not used ATM but possible ;)
    # @classmethod
    # def is_str_matches(cls, url_str):
    #     return bool(cls._REGEX.match(url_str))

    @classmethod
    def _str_to_fields(cls, url_str):
        re_match = cls._REGEX.match(url_str)
        if not re_match:
            # TODO: custom error?
            raise ValueError(
                "Possibly incorrectly determined string %r correspond to %s address"
                " -- it failed matching regex. Dunno how to handle. Contact developers"
                % (cls, url_str,)
            )
        fields = cls._get_blank_fields()
        fields.update({k: v for k, v in iteritems(re_match.groupdict()) if v})
        cls._normalize_fields(fields)
        return fields

    @classmethod
    def _normalize_fields(self, fields):
        """Helper to be ran if any of the fields need to be normalized after parsing"""
        pass


class SSHRI(RI, RegexBasedURLMixin):
    """RI pointing to a remote location reachable via SSH"""

    _FIELDS = RI._FIELDS + (
        'username',
        'hostname',
        'port',
    )

    _REGEX = re.compile(r'((?P<username>\S*)@)?(?P<hostname>[^:]+)(\:(?P<path>.*))?$')

    @classmethod
    def _normalize_fields(cls, fields):
        if fields['path'] and fields['path'].startswith('//'):
            # Let's normalize for now to avoid multiple leading slashes
            fields['path'] = '/' + fields['path'].lstrip('/')
        # escape path so we have direct representation of the path to work with
        fields['path'] = unescape_ssh_path(fields['path'])

    def as_str(self, escape=False):
        fields = self.fields  # copy so we could escape symbols
        url_fmt = '{hostname}'
        if fields['username']:
            url_fmt = "{username}@" + url_fmt
        if fields['path']:
            url_fmt += ':{path}'
        if escape:
            fields['path'] = escape_ssh_path(fields['path'])
        return url_fmt.format(**fields)

    # TODO:
    # we can "support" localhost:path as localpaths


class DataLadRI(RI, RegexBasedURLMixin):
    """RI pointing to datasets within central DataLad super-dataset"""

    _FIELDS = RI._FIELDS + (
        'remote',
    )

    # For now or forever we don't deal with any fragments or other special stuff
    _REGEX = re.compile(r'//(?P<remote>[^\s/]*)/(?P<path>.*)$')

    # do they need to be normalized??? loosing track ...

    def as_str(self):
        return "//{remote}/{path}".format(**self._fields)

    def as_git_url(self):
        """Dereference /// into original URLs which could be used by git for cloning

        Returns
        -------
        str
          URL string to reference the DataLadRI from its /// form
        """
        if self.remote:
            raise NotImplementedError("not supported ATM to reference additional remotes")
        return "{}{}".format(DATASETS_TOPURL, urlquote(self.path))


def _split_colon(s, maxsplit=1):
    """Split on unescaped colon"""
    return re.compile(r'(?<!\\):').split(s, maxsplit=maxsplit)

# \ should be first to deal with
_SSH_ESCAPED_CHARACTERS = '\\#&;`|*?~<>^()[]{}$\'" '


# TODO: RF using re.sub
def escape_ssh_path(path):
    """Escape all special characters present in the path"""
    for c in _SSH_ESCAPED_CHARACTERS:
        if c in path:
            path = path.replace(c, '\\' + c)
    return path


def unescape_ssh_path(path):
    """Un-escape all special characters present in the path"""
    for c in _SSH_ESCAPED_CHARACTERS[::-1]:
        if c in path:
            path = path.replace('\\' + c, c)
    return path


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
def is_url(ri):
    """Returns whether argument is a resource identifier what datalad should treat as a URL

    This includes ssh "urls" which git understands.

    Parameters
    ----------
    ri : str or RI
      The resource identifier (as a string or RI) to "analyze"
    """
    if not isinstance(ri, RI):
        try:
            ri = RI(ri)
        except:  # MIH: MemoryError?
            return False
    return isinstance(ri, (URL, SSHRI))


# TODO: RF to remove duplication
def is_datalad_compat_ri(ri):
    """Returns whether argument is a resource identifier what datalad should treat as a URL

    including its own DataLadRI
    """
    if not isinstance(ri, RI):
        try:
            ri = RI(ri)
        except:  # MIH: MemoryError?
            return False
    return isinstance(ri, (URL, SSHRI, DataLadRI))


# TODO: better name? additionally may be move to SSHRI.is_valid() or sth.
def is_ssh(ri):
    """helper to determine, whether `ri` requires an SSH connection

    Parameters
    ----------
    ri: str or RI

    Returns
    -------
    bool
    """

    # not exactly fitting the doc, but we actually can deal not necessarily with
    # string or RI only, but with everything RI itself can deal with:
    _ri = RI(ri) if not isinstance(ri, RI) else ri

    return isinstance(_ri, SSHRI) \
        or (isinstance(_ri, URL) and _ri.scheme == 'ssh')


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
        furl = str(URL(scheme='file', path=fname))
    return furl


def get_url_cache_filename(url, name=None):
    """Return a filename where to cache online doc from a url"""
    if not name:
        name = "misc"
    cache_dir = opj(cfg.obtain('datalad.locations.cache'), name)
    doc_fname = opj(
        cache_dir,
        '{}-{}.p{}'.format(
            urlsplit(url).netloc,
            md5(url.encode('utf-8')).hexdigest(),
            pickle.HIGHEST_PROTOCOL)
    )
    return doc_fname


def get_cached_url_content(url, name=None, fetcher=None, maxage=None):
    """Loader of a document from a url, which caches loaded instance on disk

    Doesn't do anything smart about http headers etc which could provide
    information for cache/proxy servers for how long to retain etc

    TODO: theoretically it is not network specific at all -- and just a memoize
    pattern, but may be some time we would make it treat headers etc correctly.
    And ATM would support any URL we support via providers/downloaders

    Parameters
    ----------
    fetcher: callable, optional
       Function to call with url if needed to be refetched
    maxage: float, optional
       Age in days to retain valid for.  <0 - would retain forever.  If None -
       would consult the config, 0 - would force to reload
    """
    doc_fname = get_url_cache_filename(url, name)
    if maxage is None:
        maxage = float(cfg.get('datalad.locations.cache-maxage'))

    doc = None
    if os.path.exists(doc_fname) and maxage != 0:

        fage = (time.time() - os.stat(doc_fname).st_mtime)/(24. * 3600)
        if maxage < 0 or fage < maxage:
            try:
                lgr.debug("use cached request result to '%s' from %s", url, doc_fname)
                doc = pickle.load(open(doc_fname, 'rb'))
            except Exception as e:  # it is OK to ignore any error and fall back on the true source
                lgr.warning(
                    "cannot load cache from '%s', fall back to download: %s",
                    doc_fname, exc_str(e))

    if doc is None:
        if fetcher is None:
            from datalad.downloaders.providers import Providers
            providers = Providers.from_config_files()
            fetcher = providers.fetch

        doc = fetcher(url)
        assure_dir(dirname(doc_fname))
        # use pickle to store the entire request result dict
        pickle.dump(doc, open(doc_fname, 'wb'))
        lgr.debug("stored result of request to '{}' in {}".format(url, doc_fname))
    return doc

lgr.log(5, "Done importing support.network")
