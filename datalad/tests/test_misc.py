# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join

from .utils import *

from ..support.network import get_url_response_stamp, is_url_quoted

def test_is_url_quoted():
    ok_(is_url_quoted('%22%27%3ba&b&cd|'))
    ok_(not is_url_quoted('a b'))


def test_get_response_stamp():
    r = get_url_response_stamp("http://www.example.com/1.dat",
                           {'Content-length': '101',
                            'Last-modified': 'Wed, 01 May 2013 03:02:00 GMT'})
    eq_(r['size'], 101)
    eq_(r['mtime'], 1367377320)
    eq_(r['url'], "http://www.example.com/1.dat")
