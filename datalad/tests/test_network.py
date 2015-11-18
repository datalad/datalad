# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .utils import eq_, ok_

from ..support.network import same_website, dlurljoin
from ..support.network import get_url_straight_filename


def test_same_website():
    ok_(same_website("http://a.b", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("https://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "https://a.b/2014/01/xxx/"))

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
