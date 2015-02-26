# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from .utils import eq_, ok_

from ..support.network import same_website, dgurljoin


def test_same_website():
    ok_(same_website("http://a.b", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("https://a.b/page/2/", "http://a.b/2014/01/xxx/"))
    ok_(same_website("http://a.b/page/2/", "https://a.b/2014/01/xxx/"))

def test_dgurljoin():
    eq_(dgurljoin('http://a.b/', 'f'), 'http://a.b/f')
    eq_(dgurljoin('http://a.b/page', 'f'), 'http://a.b/f')
    eq_(dgurljoin('http://a.b/dir/', 'f'), 'http://a.b/dir/f')
    eq_(dgurljoin('http://a.b/dir/', 'http://url'), 'http://url')
