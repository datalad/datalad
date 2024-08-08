# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import os
import tempfile
from os.path import isabs
from os.path import join as opj

import pytest

import datalad.support.network
from datalad.distribution.dataset import Dataset
from datalad.support.network import (
    RI,
    SSHRI,
    URL,
    DataLadRI,
    GitTransportRI,
    PathRI,
    _split_colon,
    dlurljoin,
    get_local_file_url,
    get_response_disposition_filename,
    get_tld,
    get_url_straight_filename,
    is_datalad_compat_ri,
    is_ssh,
    is_url,
    iso8601_to_epoch,
    local_path2url_path,
    local_path_representation,
    local_url_path_representation,
    parse_url_opts,
    quote_path,
    same_website,
    url_path2local_path,
    urlquote,
)
from datalad.tests.utils_pytest import (
    OBSCURE_FILENAME,
    SkipTest,
    assert_in,
    assert_raises,
    assert_status,
    eq_,
    get_most_obscure_supported_name,
    known_failure_githubci_win,
    neq_,
    nok_,
    ok_,
    skip_if,
    swallow_logs,
    with_tempfile,
)
from datalad.utils import (
    Path,
    PurePosixPath,
    on_windows,
)


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

@pytest.mark.parametrize("suf", [
    '',
    '#',
    '#tag',
    '#tag/obscure',
    '?param=1',
    '?param=1&another=/',
])
def test_get_url_straight_filename(suf):
    eq_(get_url_straight_filename('http://a.b/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1' + suf), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1/' + suf, allowdir=True), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/p2' + suf), 'p2')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf), '')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, allowdir=True), 'p2')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, allowdir=True, strip=('p2', 'xxx')), 'p1')
    eq_(get_url_straight_filename('http://a.b/p1/p2/' + suf, strip=('p2', 'xxx')), '')

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
    assert URL() == URL()
    # doesn't make sense to ask what kind of a url it is an empty URL
    assert URL() != URL(hostname='x')
    # Different types aren't equal even if have the same fields values
    assert URL(path='x') != PathRI(path='x')
    assert URL(hostname='x') != SSHRI(hostname='x')
    assert str(URL(hostname='x')) != str(SSHRI(hostname='x'))


def _check_ri(ri, cls, exact_str=True, localpath=None, **fields):
    """just a helper to carry out few checks on urls"""
    with swallow_logs(new_level=logging.DEBUG) as cml:
        ri_ = cls(**fields)
        murl = RI(ri)
        assert murl.__class__ == cls  # not just a subclass
        assert murl == ri_
        if isinstance(ri, str):
            assert str(RI(ri)) == ri
        assert eval(repr(ri_)) == ri  # repr leads back to identical ri_
        assert ri == ri_  # just in case ;)  above should fail first if smth is wrong
        if not exact_str:
            assert_in('Parsed version of', cml.out)
    if exact_str:
        assert str(ri) == str(ri_)
    else:
        assert str(ri) != str(ri_)

    # and that we have access to all those fields
    nok_(set(fields).difference(set(cls._FIELDS)))
    for f, v in fields.items():
        assert getattr(ri_, f) == v

    if localpath:
        if cls == URL:
            local_representation = local_url_path_representation(localpath)
        else:
            local_representation = local_path_representation(localpath)
        assert ri_.localpath == local_representation
        old_localpath = ri_.localpath  # for a test below
    else:
        # if not given -- must be a remote url, should raise exception on
        # non-Windows systems. But not on Windows systems because we allow UNCs
        # to be encoded in URLs
        if not on_windows:
            with assert_raises(ValueError):
                ri_.localpath

    # This one does not have a path. TODO: either proxy path from its .RI or adjust
    # hierarchy of classes to make it more explicit
    if cls == GitTransportRI:
        return
    # do changes in the path persist?
    old_str = str(ri_)
    ri_.path = newpath = opj(ri_.path, 'sub')
    assert ri_.path == newpath
    assert str(ri_) != old_str
    if localpath:
        assert ri_.localpath == local_path_representation(opj(old_localpath, 'sub'))


def test_url_base():
    # Basic checks
    assert_raises(ValueError, URL, "http://example.com", hostname='example.com')
    url = URL("http://example.com")
    eq_(url.hostname, 'example.com')
    eq_(url.scheme, 'http')
    eq_(url.port, '')  # not specified -- empty strings
    eq_(url.username, '')  # not specified -- empty strings
    eq_(repr(url), "URL(hostname='example.com', netloc='example.com', scheme='http')")
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


@with_tempfile
def test_pathri_guessing(filename=None):
    # Complaining about ;param only at DEBUG level
    # see https://github.com/datalad/datalad/issues/6872
    with swallow_logs(new_level=logging.DEBUG) as cml:
        # we don't "care" about params ATM so there is a warning if there are any
        ri = RI(f"{filename};param")
        assert isinstance(ri, PathRI)
        if not on_windows:
            # Does not happen on Windows since paths with \ instead of / do not
            # look like possible URLs
            assert_in('ParseResults contains params', cml.out)


@skip_if(not on_windows)
def test_pathri_windows_anchor():
    assert RI('file:///c:/Windows').localpath == 'C:\\Windows'


@known_failure_githubci_win
def test_url_samples():
    _check_ri("http://example.com", URL, scheme='http', hostname="example.com", netloc='example.com')
    # "complete" one for classical http
    _check_ri("http://user:pw@example.com:8080/p/sp?p1=v1&p2=v2#frag", URL,
              scheme='http', netloc='user:pw@example.com:8080',
              hostname="example.com", port=8080, username='user', password='pw',
              path='/p/sp', query='p1=v1&p2=v2', fragment='frag')

    # sample one for ssh with specifying the scheme
    # XXX? might be useful?  https://github.com/FriendCode/giturlparse.py
    _check_ri("ssh://host/path/sp1", URL, scheme='ssh', hostname='host',
              netloc='host', path='/path/sp1')
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
    _check_ri("hg+https://host/user/proj", URL, scheme="hg+https",
              netloc='host', hostname='host', path='/user/proj')
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
    _check_ri("file://host", URL, scheme='file', netloc='host', hostname='host')
    _check_ri("file://host/path/sp1", URL, scheme='file', netloc='host',
              hostname='host', path='/path/sp1')
    # stock libraries of Python aren't quite ready for ipv6
    ipv6address = '2001:db8:85a3::8a2e:370:7334'
    _check_ri("file://%s/path/sp1" % ipv6address, URL,
              scheme='file', netloc=ipv6address, hostname=ipv6address,
              path='/path/sp1')
    for lh in ('localhost', '::1', '', '127.3.4.155'):
        if on_windows:
            url = RI(f"file://{lh}/path/sp1")
            assert url.localpath == f'\\\\{lh}\\path\\sp1' if lh else '\\path\\sp1'
        else:
            _check_ri("file://%s/path/sp1" % lh, URL, localpath='/path/sp1',
                      scheme='file', netloc=lh, hostname=lh, path='/path/sp1')

    _check_ri('http://[1fff:0:a88:85a3::ac1f]:8001/index.html', URL,
              scheme='http', netloc='[1fff:0:a88:85a3::ac1f]:8001',
              hostname='1fff:0:a88:85a3::ac1f', port=8001, path='/index.html')
    _check_ri("file:///path/sp1", URL, localpath='/path/sp1', scheme='file', path='/path/sp1')
    # we don't do any magical comprehension for home paths/drives for windows
    # of file:// urls, thus leaving /~ and /c: for now:
    _check_ri("file:///~/path/sp1", URL, localpath='/~/path/sp1', scheme='file', path='/~/path/sp1')
    _check_ri("file:///%7E/path/sp1", URL, localpath='/~/path/sp1', scheme='file', path='/~/path/sp1', exact_str=False)
    # not sure but let's check
    if on_windows:
        _check_ri("file:///C:/path/sp1", URL, localpath='C:/path/sp1', scheme='file', path='/C:/path/sp1', exact_str=False)
        _check_ri("file:/C:/path/sp1", URL, localpath='C:/path/sp1', scheme='file', path='/C:/path/sp1', exact_str=False)
        # git-annex style drive-letter encoding
        _check_ri("file://C:/path/sp1", URL, netloc="C:", hostname="c", localpath='C:/path/sp1', scheme='file', path='/path/sp1', exact_str=False)
    else:
        _check_ri("file:///C:/path/sp1", URL, localpath='/C:/path/sp1', scheme='file', path='/C:/path/sp1', exact_str=False)
        _check_ri("file:/C:/path/sp1", URL, localpath='/C:/path/sp1', scheme='file', path='/C:/path/sp1', exact_str=False)

    # and now implicit paths or actually they are also "URI references"
    _check_ri("f", PathRI, localpath='f', path='f')
    _check_ri("f/s1", PathRI, localpath='f/s1', path='f/s1')
    _check_ri(PurePosixPath("f"), PathRI, localpath='f', path='f')
    _check_ri(PurePosixPath("f/s1"), PathRI, localpath='f/s1', path='f/s1')
    # colons are problematic and might cause confusion into SSHRI
    _check_ri("f/s:1", PathRI, localpath='f/s:1', path='f/s:1')
    _check_ri("f/s:", PathRI, localpath='f/s:', path='f/s:')
    _check_ri("/f", PathRI, localpath='/f', path='/f')
    _check_ri("/f/s1", PathRI, localpath='/f/s1', path='/f/s1')

    # some github ones, just to make sure
    _check_ri("git://host/user/proj", URL, scheme="git", netloc="host",
              hostname="host", path="/user/proj")
    _check_ri("git@host:user/proj", SSHRI, hostname="host", path="user/proj", username='git')

    _check_ri('weird:/', SSHRI, hostname='weird', path='/')
    # since schema is not allowing some symbols so we need to add additional check
    _check_ri('weird_url:/', SSHRI, hostname='weird_url', path='/')
    _check_ri('example.com:/', SSHRI, hostname='example.com', path='/')
    _check_ri('example.com:path/sp1', SSHRI, hostname='example.com', path='path/sp1')
    _check_ri('example.com/path/sp1\\:fname', PathRI, localpath='example.com/path/sp1\\:fname',
              path='example.com/path/sp1\\:fname')
    # ssh is as stupid as us, so we will stay "Consistently" dumb
    """
    $> ssh example.com/path/sp1:fname
    ssh: Could not resolve hostname example.com/path/sp1:fname: Name or service not known

    edit 20190516 yoh: but this looks like a perfectly valid path.
    SSH knows that it is not a path but its SSHRI so it can stay dumb.
    We are trying to be smart and choose between RIs (even when we know that
    it is e.g. a file).
    """
    _check_ri('e.com/p/sp:f', PathRI, localpath='e.com/p/sp:f', path='e.com/p/sp:f')
    _check_ri('user@someho.st/mydir', PathRI, localpath='user@someho.st/mydir', path='user@someho.st/mydir')

    # SSHRIs have .port, but it is empty
    eq_(SSHRI(hostname='example.com').port, '')

    # check that we are getting a warning logged when url can't be reconstructed
    # precisely
    # actually failed to come up with one -- becomes late here
    #_check_ri("http://host///..//p", scheme='http', path='/..//p')

    # actually this one is good enough to trigger a warning and I still don't know
    # what it should exactly be!?
    with swallow_logs(new_level=logging.DEBUG) as cml:
        weird_str = 'weird://'
        weird_url = RI(weird_str)
        repr(weird_url)
        cml.assert_logged(
            'Parsed version of SSHRI .weird:/. '
            'differs from original .weird://.'
        )
        # but we store original str
        eq_(str(weird_url), weird_str)
        neq_(weird_url.as_str(), weird_str)

    raise SkipTest("TODO: file://::1/some does complain about parsed version dropping ::1")


def test_git_transport_ri():
    _check_ri("gcrypt::http://somewhere", GitTransportRI, RI='http://somewhere', transport='gcrypt')
    # man git-push says
    #  <transport>::<address>
    #    where <address> may be a path, a server and path, or an arbitrary URL-like string...
    # so full path to my.com/... should be ok?
    _check_ri("http::/my.com/some/path", GitTransportRI, RI='/my.com/some/path', transport='http')
    # some ssh server.  And we allow for some additional chars in transport.
    # Git doesn't define since it does not care! we will then be flexible too
    _check_ri("trans-port::server:path", GitTransportRI, RI='server:path', transport='trans-port')


@pytest.mark.parametrize("cls,clskwargs,target_url", [
    (SSHRI, {}, r'example.com:/ "' + r"';a&b&cd `| "),
    (URL, {'scheme': "http"}, 'http://example.com/%20%22%27%3Ba%26b%26cd%20%60%7C%20'),
    (PathRI, {}, r'/ "' + r"';a&b&cd `| "),  # nothing is done to file:implicit
])
def test_url_quote_path(cls, clskwargs, target_url):
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


def test_url_compose_archive_one():
    url = URL(scheme='dl+archive', path='KEY',
              fragment=dict((('path', 'f/p/ s+'), ('size', 30))))
    # funny - space is encoded as + but + is %2B
    eq_(str(url), 'dl+archive:KEY#path=f/p/+s%2B&size=30')
    eq_(url.fragment_dict, {'path': 'f/p/ s+', 'size': '30'})


def test_url_fragments_and_query():
    url = URL(hostname="host", query=dict((('a', 'x/b'), ('b', 'y'))))
    eq_(str(url), '//host?a=x%2Fb&b=y')
    eq_(url.query, 'a=x%2Fb&b=y')
    eq_(url.query_dict, {'a': 'x/b', 'b': 'y'})

    url = URL(hostname="host", fragment=dict((('b', 'x/b'), ('a', 'y'))))
    eq_(str(url), '//host#b=x/b&a=y')
    eq_(url.fragment, 'b=x/b&a=y')
    eq_(url.fragment_dict, {'a': 'y', 'b': 'x/b'})

    fname = get_most_obscure_supported_name()
    url = URL(hostname="host", fragment={'a': fname})
    eq_(url.fragment_dict, {'a': fname})


def test_url_dicts():
    eq_(URL("http://host").query_dict, {})


def test_get_url_path_on_fileurls():
    assert URL('file:///a').path == '/a'
    assert URL('file:///a/b').path == '/a/b'
    assert URL('file:///a/b').localpath == local_path_representation('/a/b')
    assert URL('file:///a/b#id').path == '/a/b'
    assert URL('file:///a/b?whatever').path == '/a/b'


def test_is_url():
    ok_(is_url('file://localhost/some'))
    ok_(is_url('http://localhost'))
    ok_(is_url('ssh://me@localhost'))
    # in current understanding it is indeed a url but an 'ssh', implicit=True, not just
    # a useless scheme=weird with a hope to point to a netloc
    with swallow_logs():
        ok_(is_url('weird://'))
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
    ok_(is_datalad_compat_ri('ssh://user:passw@host/path'))
    ok_(is_datalad_compat_ri('http://example.com'))
    ok_(is_datalad_compat_ri('file://localhost/some'))
    ok_(is_datalad_compat_ri('///localhost/some'))
    nok_(is_datalad_compat_ri('relative'))
    nok_(is_datalad_compat_ri('.///localhost/some'))
    nok_(is_datalad_compat_ri(123))


def test_get_local_file_url():
    compat_annex = 'git-annex'
    compat_git = 'git'
    for path, url, compatibility in (
                # relpaths are special-cased below
                ('test.txt', 'test.txt', compat_annex),
                (OBSCURE_FILENAME, urlquote(OBSCURE_FILENAME), compat_annex),
            ) + ((
                ('C:\\Windows\\notepad.exe', 'file://C:/Windows/notepad.exe', compat_annex),
                ('C:\\Windows\\notepad.exe', 'file:///C:/Windows/notepad.exe', compat_git),
            ) if on_windows else (
                ('/a', 'file:///a', compat_annex),
                ('/a/b/c', 'file:///a/b/c', compat_annex),
                ('/a~', 'file:///a~', compat_annex),
                # there are no files with trailing slashes in the name
                #('/a b/', 'file:///a%20b/'),
                ('/a b/name', 'file:///a%20b/name', compat_annex),
            )):
        # Yarik found no better way to trigger.  .decode() isn't enough
        print("D: %s" % path)
        if isabs(path):
            assert get_local_file_url(path, compatibility=compatibility) == url
            abs_path = path
        else:
            assert get_local_file_url(path, allow_relative_path=True, compatibility=compatibility) \
                   == '/'.join((get_local_file_url(os.getcwd(), compatibility=compatibility), url))
            abs_path = opj(os.getcwd(), path)
        if compatibility == compat_git:
            assert get_local_file_url(abs_path, compatibility=compatibility) == Path(abs_path).as_uri()


@with_tempfile(mkdir=True)
def test_get_local_file_url_compatibility(path=None):
    # smoke test for file:// URL compatibility with other datalad/git/annex
    # pieces
    path = Path(path)
    ds1 = Dataset(path / 'ds1').create()
    ds2 = Dataset(path / 'ds2').create()
    testfile = path / 'testfile.txt'
    testfile.write_text('some')

    # compat with annex addurl
    ds1.repo.add_url_to_file(
        'test.txt',
        get_local_file_url(str(testfile), compatibility='git-annex'))

    # compat with git clone/submodule
    assert_status(
        'ok',
        ds1.clone(get_local_file_url(ds2.path, compatibility='git'),
                  result_xfm=None, return_type='generator'))


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
    eq_(iso8601_to_epoch('2016-07-07T14:25:15+11:00'),
        epoch - 11 * 60 * 60)
    eq_(iso8601_to_epoch('2016-07-07T14:25:15Z'), epoch)
    eq_(iso8601_to_epoch('2016-07-07T14:25:15'), epoch)

    eq_(iso8601_to_epoch('2016-07-07T14:25:14'), epoch-1)


def test_mapping_identity():
    from datalad.tests.utils_pytest import OBSCURE_FILENAME

    absolute_obscure_path = str(Path('/').absolute() / OBSCURE_FILENAME)
    temp_dir = tempfile.gettempdir()
    print(f"temp_dir: {temp_dir}")
    for name in (temp_dir, opj(temp_dir, "x.txt"), absolute_obscure_path):
        # On some platforms, e.g. MacOS, `temp_dir` might contain trailing
        # slashes. Since the conversion and its inverse normalize paths, we
        # compare the result to the normalized path
        normalized_name = str(Path(name))
        assert url_path2local_path(local_path2url_path(name)) == normalized_name

    prefix = "/C:" if on_windows else ""
    for name in map(quote_path, (prefix + "/window", prefix + "/d", prefix + "/" + OBSCURE_FILENAME)):
        assert local_path2url_path(url_path2local_path(name)) == name


def test_auto_resolve_path():
    relative_path = str(Path("a/b"))
    with pytest.raises(ValueError):
        local_path2url_path(relative_path)
    local_path2url_path("", allow_relative_path=True)


@skip_if(not on_windows)
def test_hostname_detection():
    with pytest.raises(ValueError):
        local_path2url_path("\\\\server\\share\\path")


def test_url_path2local_path_excceptions():
    with pytest.raises(ValueError):
        url_path2local_path('')
    with pytest.raises(ValueError):
        url_path2local_path(None)
    with pytest.raises(ValueError):
        url_path2local_path('a/b')
    with pytest.raises(ValueError):
        url_path2local_path(PurePosixPath('a/b'))
    with pytest.raises(ValueError):
        url_path2local_path(PurePosixPath('//a/b'))


def test_quote_path(monkeypatch):
    with monkeypatch.context() as ctx:
        ctx.setattr(datalad.support.network, 'on_windows', True)
        assert quote_path("/c:/win:xxx") == "/c:/win%3Axxx"
        assert quote_path("/C:/win:xxx") == "/C:/win%3Axxx"

        ctx.setattr(datalad.support.network, 'on_windows', False)
        assert quote_path("/c:/win:xxx") == "/c%3A/win%3Axxx"
        assert quote_path("/C:/win:xxx") == "/C%3A/win%3Axxx"
