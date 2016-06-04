# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .utils import eq_, neq_, ok_, assert_raises

from ..support.network import same_website, dlurljoin
from ..support.network import get_tld
from ..support.network import get_url_straight_filename
from ..support.network import get_response_disposition_filename
from ..support.network import parse_url_opts
from ..support.network import URL
from ..support.network import _split_colon


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

from ..support.network import rfc2822_to_epoch
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
    neq_(URL(), URL(hostname='x'))


def _check_url(url, **fields):
    """just a helper to carry out few checks on urls"""
    url_ = URL(**fields)
    eq_(URL(url), url_)
    eq_(url, url_)  # just in case ;)  above should fail first if smth is wrong
    eq_(url, str(url_))  # that we can reconstruct it


def test_url():
    assert_raises(ValueError, URL, "http://example.com", hostname="example.com")
    eq_(repr(URL("http://example.com")), "URL(hostname='example.com', scheme='http')")
    _check_url("http://example.com", scheme='http', hostname="example.com")
    eq_(URL("http://example.com"), "http://example.com")  # automagic coercion in __eq__
    neq_(URL(), URL(hostname='x'))
    # "complete" one for classical http
    _check_url("http://user:pw@example.com/p/sp?p1=v1&p2=v2#frag",
        scheme='http', hostname="example.com", username='user', password='pw', path='/p/sp', query='p1=v1&p2=v2', fragment='frag')

    # sample one for ssh with specifying the scheme
    # XXX? might be useful?  https://github.com/FriendCode/giturlparse.py
    _check_url("ssh://host/path/sp1", scheme='ssh', hostname='host', path='/path/sp1')
    _check_url("user@host:path/sp1",
               scheme='ssh:implicit', hostname='host', path='path/sp1', username='user')
    _check_url("host:path/sp1", scheme='ssh:implicit', hostname='host', path='path/sp1')
    _check_url("host:path", scheme='ssh:implicit', hostname='host', path='path')
    _check_url("host:/path", scheme='ssh:implicit', hostname='host', path='/path')
    # TODO!!!  should this be a legit URL like this?
    # _check_url("host", scheme='ssh:implicit', hostname='host'))
    eq_(repr(URL("host:path")), "URL(hostname='host', path='path', scheme='ssh:implicit')")

    # And now perspective 'datalad:implicit' urls pointing to the canonical center location
    _check_url("///", scheme='datalad:implicit', path='/')
    _check_url("///p/s1", scheme='datalad:implicit', path='/p/s1')
    # could be considered by someone as "URI reference" relative to scheme
    _check_url("//a/", scheme='datalad:implicit', path='/', hostname='a')
    _check_url("//a/data", scheme='datalad:implicit', path='/data', hostname='a')

    # here we will do custom magic allowing only schemes with + in them, such as dl+archive
    # or not so custom as
    _check_url("hg+https://host/user/proj",
        scheme="hg+https", hostname='host', path='/user/proj')
    # "old" style
    _check_url("dl+archive:KEY/path/sp1#size=123",
        scheme='dl+archive', path='KEY/path/sp1', fragment='size=123')
    # "new" style
    _check_url("dl+archive:KEY#path=path/sp1&size=123",
        scheme='dl+archive', path='KEY', fragment='path=path/sp1&size=123')

    #https://en.wikipedia.org/wiki/File_URI_scheme
    _check_url("file://host", scheme='file', hostname='host')
    _check_url("file://host/path/sp1", scheme='file', hostname='host', path='/path/sp1')
    _check_url("file:///path/sp1", scheme='file', path='/path/sp1')
    _check_url("file:///~/path/sp1", scheme='file', path='/~/path/sp1')
    # not sure but let's check
    _check_url("file:///c:/path/sp1", scheme='file', path='/c:/path/sp1')

    # and now implicit paths or actually they are also "URI references"
    _check_url("f", scheme='file:implicit', path='f')
    _check_url("f/s1", scheme='file:implicit', path='f/s1')
    _check_url("/f", scheme='file:implicit', path='/f')
    _check_url("/f/s1", scheme='file:implicit', path='/f/s1')

    # some github ones, just to make sure
    _check_url("git://host/user/proj", scheme="git", hostname="host", path="/user/proj")
    _check_url("git@host:user/proj",
               scheme="ssh:implicit", hostname="host", path="user/proj", username='git')