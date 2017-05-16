# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging

from os.path import join as opj
from collections import OrderedDict

from datalad.tests.utils import eq_, neq_, ok_, nok_, assert_raises
from datalad.tests.utils import skip_if_on_windows
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import assert_re_in
from datalad.tests.utils import assert_in
from datalad.tests.utils import get_most_obscure_supported_name
from datalad.tests.utils import SkipTest

from ..network import same_website, dlurljoin
from ..network import get_tld
from ..network import get_url_straight_filename
from ..network import get_response_disposition_filename
from ..network import parse_url_opts
from ..network import RI
from ..network import SSHRI
from ..network import PathRI
from ..network import DataLadRI
from ..network import URL
from ..network import _split_colon
from ..network import is_url
from ..network import is_datalad_compat_ri
from ..network import get_local_file_url
from ..network import is_ssh
from ..network import iso8601_to_epoch


def test_same_website():
    ok_(same_website("http://a.b", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("https://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "https://a.b/2014/01/xxx/"))


def test_get_tld():
    eq_(get_tld('http://example.com'), 'example.com')
    eq_(get_tld('http://example.com/1'), 'example.com')
    eq_(get_tld('http://example.com/1/2'), 'example.com')
    eq_(get_tld('example.com/1/2'), 'example.com')
    eq_(get_tld('s3://example.com/1/2'), 'example.com')
    assert_raises(ValueError, get_tld, "")
    assert_raises(ValueError, get_tld, "s3://")
    assert_raises(ValueError, get_tld, "http://")

def test_dlurljoin():
    eq_(dlurljoin('http://a.b/', 'f'), 'http://a.b/f')
    eq_(dlurljoin('http://a.b/page', 'f'), 'http://a.b/f')
    eq_(dlurljoin('http://a.b/dir/', 'f'), 'http://a.b/dir/f')
    eq_(dlurljoin('http://a.b/dir/', 'http://url'), 'http://url')
    eq_(dlurljoin('http://a.b/dir/', '/'), 'http://a.b/')
    eq_(dlurljoin('http://a.b/dir/', '/x/y'), 'http://a.b/x/y')

def _test_get_url_straight_filename(suf):
    eq_(get_url_straight_filename('http://a.b/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1' + suf), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1/' + suf, allowdir=True), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/p2' + suf), 'p2')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, allowdir=True), 'p2')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, allowdir=True, strip=('p2', 'xxx')), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, strip=('p2', 'xxx')), '')

def test_get_url_straight_filename():
    yield _test_get_url_straight_filename, ''
    yield _test_get_url_straight_filename, '#'
    yield _test_get_url_straight_filename, '#tag'
    yield _test_get_url_straight_filename, '#tag/obscure'
    yield _test_get_url_straight_filename, '?param=1'
    yield _test_get_url_straight_filename, '?param=1&another=/'

from ..network import rfc2822_to_epoch
def test_rfc2822_to_epoch():
    eq_(rfc2822_to_epoch("Thu, 16 Oct 2014 01:16:17 EDT"), 1413436577)


def test_get_response_disposition_filename():
    eq_(get_response_disposition_filename('attachment;filename="Part1-Subjects1-99.tar"'), "Part1-Subjects1-99.tar")
    eq_(get_response_disposition_filename('attachment'), None)


def test_parse_url_opts():
    url = 'http://map.org/api/download/?id=157'
    output = parse_url_opts(url)
    eq_(output, ('http://map.org/api/download/', {'id': '157'}))

    url = 's3://bucket/save/?key=891'
    output = parse_url_opts(url)
    eq_(output, ('s3://bucket/save/', {'key': '891'}))

    url = 'http://map.org/api/download/?id=98&code=13'
    output = parse_url_opts(url)
    eq_(output, ('http://map.org/api/download/', {'id': '98', 'code': '13'}))


def test_split_colon():
    eq_(_split_colon('a:b'), ['a', 'b'])
    eq_(_split_colon('a:b:c'), ['a', 'b:c'])
    eq_(_split_colon('a:b:c', 2), ['a', 'b', 'c'])
    eq_(_split_colon('ab'), ['ab'])
    eq_(_split_colon(r'a\:b'), [r'a\:b'])


def test_url_eq():
    eq_(URL(), URL())
    # doesn't make sense to ask what kind of a url it is an empty URL
    #eq_(RI(), RI())
    neq_(URL(), URL(hostname='x'))
    # Different types aren't equal even if have the same fields values
    neq_(URL(path='x'), PathRI(path='x'))
    neq_(URL(hostname='x'), SSHRI(hostname='x'))
    neq_(str(URL(hostname='x')), str(SSHRI(hostname='x')))


def _check_ri(ri, cls, exact_str=True, localpath=None, **fields):
    """just a helper to carry out few checks on urls"""
    with swallow_logs(new_level=logging.DEBUG) as cml:
        ri_ = cls(**fields)
        murl = RI(ri)
        eq_(murl.__class__, cls)  # not just a subclass
        eq_(murl, ri_)
        eq_(str(RI(ri)), ri)
        eq_(eval(repr(ri_)), ri)  # repr leads back to identical ri_
        eq_(ri, ri_)  # just in case ;)  above should fail first if smth is wrong
        if not exact_str:
            assert_in('Parsed version of', cml.out)
    (eq_ if exact_str else neq_)(ri, str(ri_))  # that we can reconstruct it EXACTLY on our examples
    # and that we have access to all those fields
    nok_(set(fields).difference(set(cls._FIELDS)))
    for f, v in fields.items():
        eq_(getattr(ri_, f), v)

    if localpath:
        eq_(ri_.localpath, localpath)
        old_localpath = ri_.localpath  # for a test below
    else:
        # if not given -- must be a remote url, should raise exception
        with assert_raises(ValueError):
            ri_.localpath

    # do changes in the path persist?
    old_str = str(ri_)
    ri_.path = newpath = opj(ri_.path, 'sub')
    eq_(ri_.path, newpath)
    neq_(str(ri_), old_str)
    if localpath:
        eq_(ri_.localpath, opj(old_localpath, 'sub'))



def test_url_base():
    # Basic checks
    assert_raises(ValueError, URL, "http://example.com", hostname='example.com')
    url = URL("http://example.com")
    eq_(url.hostname, 'example.com')
    eq_(url.scheme, 'http')
    eq_(url.port, '')  # not specified -- empty strings
    eq_(url.username, '')  # not specified -- empty strings
    eq_(repr(url), "URL(hostname='example.com', scheme='http')")
    eq_(url, "http://example.com")  # automagic coercion in __eq__

    neq_(URL(), URL(hostname='x'))

    smth = URL('smth')
    eq_(smth.hostname, '')
    ok_(bool(smth))
    nok_(bool(URL()))

    assert_raises(ValueError, url._set_from_fields, unknown='1')

    with swallow_logs(new_level=logging.WARNING) as cml:
        # we don't "care" about params ATM so there is a warning if there are any
        purl = URL("http://example.com/;param")
        eq_(str(purl), 'http://example.com/;param')  # but we do maintain original string
        assert_in('ParseResults contains params', cml.out)
        eq_(purl.as_str(), 'http://example.com/')


def test_url_samples():
    _check_ri("http://example.com", URL, scheme='http', hostname="example.com")
    # "complete" one for classical http
    _check_ri("http://user:pw@example.com:8080/p/sp?p1=v1&p2=v2#frag", URL,
              scheme='http', hostname="example.com", port=8080,
              username='user', password='pw', path='/p/sp',
              query='p1=v1&p2=v2', fragment='frag')

    # sample one for ssh with specifying the scheme
    # XXX? might be useful?  https://github.com/FriendCode/giturlparse.py
    _check_ri("ssh://host/path/sp1", URL, scheme='ssh', hostname='host', path='/path/sp1')
    _check_ri("user@host:path/sp1", SSHRI,
              hostname='host', path='path/sp1', username='user')
    _check_ri("host:path/sp1", SSHRI, hostname='host', path='path/sp1')
    _check_ri("host:path", SSHRI, hostname='host', path='path')
    _check_ri("host:/path", SSHRI, hostname='host', path='/path')
    _check_ri("user@host", SSHRI, hostname='host', username='user')
    # TODO!!!  should this be a legit URL like this?
    # _check_ri("host", SSHRI, hostname='host'))
    eq_(repr(RI("host:path")), "SSHRI(hostname='host', path='path')")

    # And now perspective 'datalad', implicit=True urls pointing to the canonical center location
    _check_ri("///", DataLadRI)
    _check_ri("///p/s1", DataLadRI, path='p/s1')
    # could be considered by someone as "URI reference" relative to scheme
    _check_ri("//a/", DataLadRI, remote='a')
    _check_ri("//a/data", DataLadRI, path='data', remote='a')

    # here we will do custom magic allowing only schemes with + in them, such as dl+archive
    # or not so custom as
    _check_ri("hg+https://host/user/proj", URL,
              scheme="hg+https", hostname='host', path='/user/proj')
    # "old" style
    _check_ri("dl+archive:KEY/path/sp1#size=123", URL,
              scheme='dl+archive', path='KEY/path/sp1', fragment='size=123')
    # "new" style
    _check_ri("dl+archive:KEY#path=path/sp1&size=123", URL,
              scheme='dl+archive', path='KEY', fragment='path=path/sp1&size=123')
    # actually above one is probably wrong since we need to encode the path
    _check_ri("dl+archive:KEY#path=path%2Fbsp1&size=123", URL,
              scheme='dl+archive', path='KEY', fragment='path=path%2Fbsp1&size=123')

    #https://en.wikipedia.org/wiki/File_URI_scheme
    _check_ri("file://host", URL, scheme='file', hostname='host')
    _check_ri("file://host/path/sp1", URL, scheme='file', hostname='host', path='/path/sp1')
    # stock libraries of Python aren't quite ready for ipv6
    ipv6address = '2001:db8:85a3::8a2e:370:7334'
    _check_ri("file://%s/path/sp1" % ipv6address, URL,
              scheme='file', hostname=ipv6address, path='/path/sp1')
    for lh in ('localhost', '::1', '', '127.3.4.155'):
        _check_ri("file://%s/path/sp1" % lh, URL, localpath='/path/sp1',
                  scheme='file', hostname=lh, path='/path/sp1')
    _check_ri('http://[1fff:0:a88:85a3::ac1f]:8001/index.html', URL,
              scheme='http', hostname='1fff:0:a88:85a3::ac1f', port=8001, path='/index.html')
    _check_ri("file:///path/sp1", URL, localpath='/path/sp1', scheme='file', path='/path/sp1')
    # we don't do any magical comprehension for home paths/drives for windows
    # of file:// urls, thus leaving /~ and /c: for now:
    _check_ri("file:///~/path/sp1", URL, localpath='/~/path/sp1', scheme='file', path='/~/path/sp1', exact_str=False)
    _check_ri("file:///%7E/path/sp1", URL, localpath='/~/path/sp1', scheme='file', path='/~/path/sp1')
    # not sure but let's check
    _check_ri("file:///c:/path/sp1", URL, localpath='/c:/path/sp1', scheme='file', path='/c:/path/sp1', exact_str=False)

    # and now implicit paths or actually they are also "URI references"
    _check_ri("f", PathRI, localpath='f', path='f')
    _check_ri("f/s1", PathRI, localpath='f/s1', path='f/s1')
    _check_ri("/f", PathRI, localpath='/f', path='/f')
    _check_ri("/f/s1", PathRI, localpath='/f/s1', path='/f/s1')

    # some github ones, just to make sure
    _check_ri("git://host/user/proj", URL, scheme="git", hostname="host", path="/user/proj")
    _check_ri("git@host:user/proj", SSHRI, hostname="host", path="user/proj", username='git')

    _check_ri('weired:/', SSHRI, hostname='weired', path='/')
    # since schema is not allowing some symbols so we need to add additional check
    _check_ri('weired_url:/', SSHRI, hostname='weired_url', path='/')
    _check_ri('example.com:/', SSHRI, hostname='example.com', path='/')
    _check_ri('example.com:path/sp1', SSHRI, hostname='example.com', path='path/sp1')
    _check_ri('example.com/path/sp1\:fname', PathRI, localpath='example.com/path/sp1\:fname',
              path='example.com/path/sp1\:fname')
    # ssh is as stupid as us, so we will stay "Consistently" dumb
    """
    $> ssh example.com/path/sp1:fname
    ssh: Could not resolve hostname example.com/path/sp1:fname: Name or service not known
    """
    _check_ri('example.com/path/sp1:fname', SSHRI, hostname='example.com/path/sp1', path='fname')

    # SSHRIs have .port, but it is empty
    eq_(SSHRI(hostname='example.com').port, '')

    # check that we are getting a warning logged when url can't be reconstructed
    # precisely
    # actually failed to come up with one -- becomes late here
    #_check_ri("http://host///..//p", scheme='http', path='/..//p')

    # actually this one is good enough to trigger a warning and I still don't know
    # what it should exactly be!?
    with swallow_logs(new_level=logging.DEBUG) as cml:
        weired_str = 'weired://'
        weired_url = RI(weired_str)
        repr(weired_url)
        cml.assert_logged(
            'Parsed version of SSHRI .weired:/. '
            'differs from original .weired://.'
        )
        # but we store original str
        eq_(str(weired_url), weired_str)
        neq_(weired_url.as_str(), weired_str)


    raise SkipTest("TODO: file://::1/some does complain about parsed version dropping ::1")


def _test_url_quote_path(cls, clskwargs, target_url):
    path = '/ "\';a&b&cd `| '
    if not (cls is PathRI):
        clskwargs['hostname'] = hostname = 'example.com'
    url = cls(path=path, **clskwargs)
    eq_(url.path, path)
    if 'hostname' in clskwargs:
        eq_(url.hostname, hostname)
    # all nasty symbols should be quoted
    url_str = str(url)
    eq_(url_str, target_url)
    # no side-effects:
    eq_(url.path, path)
    if 'hostname' in clskwargs:
        eq_(url.hostname, hostname)

    # and figured out and unquoted
    url_ = RI(url_str)
    ok_(isinstance(url_, cls))
    eq_(url_.path, path)
    if 'hostname' in clskwargs:
        eq_(url.hostname, hostname)


def test_url_quote_path():
    yield _test_url_quote_path, SSHRI, {}, r'example.com:/ "' + r"';a&b&cd `| "
    yield _test_url_quote_path, URL, {'scheme': "http"}, 'http://example.com/%20%22%27%3Ba%26b%26cd%20%60%7C%20'
    yield _test_url_quote_path, PathRI, {}, r'/ "' + r"';a&b&cd `| "  # nothing is done to file:implicit


def test_url_compose_archive_one():
    url = URL(scheme='dl+archive', path='KEY',
              fragment=OrderedDict((('path', 'f/p/ s+'), ('size', 30))))
    # funny - space is encoded as + but + is %2B
    eq_(str(url), 'dl+archive:KEY#path=f/p/+s%2B&size=30')
    eq_(url.fragment_dict, {'path': 'f/p/ s+', 'size': '30'})


def test_url_fragments_and_query():
    url = URL(hostname="host", query=OrderedDict((('a', 'x/b'), ('b', 'y'))))
    eq_(str(url), '//host?a=x%2Fb&b=y')
    eq_(url.query, 'a=x%2Fb&b=y')
    eq_(url.query_dict, {'a': 'x/b', 'b': 'y'})

    url = URL(hostname="host", fragment=OrderedDict((('b', 'x/b'), ('a', 'y'))))
    eq_(str(url), '//host#b=x/b&a=y')
    eq_(url.fragment, 'b=x/b&a=y')
    eq_(url.fragment_dict, {'a': 'y', 'b': 'x/b'})

    fname = get_most_obscure_supported_name()
    url = URL(hostname="host", fragment={'a': fname})
    eq_(url.fragment_dict, {'a': fname})


def test_url_dicts():
    eq_(URL("http://host").query_dict, {})


@skip_if_on_windows
def test_get_url_path_on_fileurls():
    eq_(URL('file:///a').path, '/a')
    eq_(URL('file:///a/b').path, '/a/b')
    eq_(URL('file:///a/b').localpath, '/a/b')
    eq_(URL('file:///a/b#id').path, '/a/b')
    eq_(URL('file:///a/b?whatever').path, '/a/b')


def test_is_url():
    ok_(is_url('file://localhost/some'))
    ok_(is_url('http://localhost'))
    ok_(is_url('ssh://me@localhost'))
    # in current understanding it is indeed a url but an 'ssh', implicit=True, not just
    # a useless scheme=weired with a hope to point to a netloc
    with swallow_logs():
        ok_(is_url('weired://'))
    nok_(is_url('relative'))
    nok_(is_url('/absolute'))
    ok_(is_url('like@sshlogin'))  # actually we do allow ssh:implicit urls ATM
    nok_(is_url(''))
    nok_(is_url(' '))
    nok_(is_url(123))  # stuff of other types wouldn't be considered a URL

    # we can pass RI instance directly
    ok_(is_url(RI('file://localhost/some')))
    nok_(is_url(RI('relative')))


# TODO: RF with test_is_url to avoid duplication
def test_is_datalad_compat_ri():
    ok_(is_datalad_compat_ri('file://localhost/some'))
    ok_(is_datalad_compat_ri('///localhost/some'))
    nok_(is_datalad_compat_ri('relative'))
    nok_(is_datalad_compat_ri('.///localhost/some'))
    nok_(is_datalad_compat_ri(123))


def test_get_local_file_url_linux():
    eq_(get_local_file_url('/a'), 'file:///a')
    eq_(get_local_file_url('/a/b/c'), 'file:///a/b/c')
    eq_(get_local_file_url('/a~'), 'file:///a%7E')
    eq_(get_local_file_url('/a b/'), 'file:///a%20b/')


def test_is_ssh():

    ssh_locators = ["ssh://host",
                    "ssh://host/some/where",
                    "user@host:path/sp1",
                    "user@host:/absolute/path/sp1",
                    "host:path/sp1",
                    "host:/absolute/path/sp1",
                    "user@host"]
    for ri in ssh_locators:
        ok_(is_ssh(ri), "not considered ssh (string): %s" % ri)
        ok_(is_ssh(RI(ri)), "not considered ssh (RI): %s" % ri)

    non_ssh_locators = ["file://path/to",
                        "/abs/path",
                        "../rel/path",
                        "http://example.com",
                        "git://host/user/proj",
                        "s3://bucket/save/?key=891"]
    for ri in non_ssh_locators:
        ok_(not is_ssh(ri), "considered ssh (string): %s" % ri)
        ok_(not is_ssh(RI(ri)), "considered ssh (RI): %s" % ri)


def test_iso8601_to_epoch():
    epoch = 1467901515
    eq_(iso8601_to_epoch('2016-07-07T14:25:15+00:00'), epoch)
    # zone information is actually not used
    eq_(iso8601_to_epoch('2016-07-07T14:25:15+11:00'), epoch)
    eq_(iso8601_to_epoch('2016-07-07T14:25:15Z'), epoch)
    eq_(iso8601_to_epoch('2016-07-07T14:25:15'), epoch)

    eq_(iso8601_to_epoch('2016-07-07T14:25:14'), epoch-1)
