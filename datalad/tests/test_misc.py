# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from distutils.version import LooseVersion

from .utils import *


import datalad
from datalad.support.network import get_url_response_stamp, is_url_quoted
from datalad.utils import swallow_outputs


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


def test_test():
    try:
        import numpy
        assert LooseVersion(numpy.__version__) >= '1.2'
    except:
        raise SkipTest("Need numpy 1.2")

    # we need to avoid running global teardown
    with patch.dict('os.environ', {'DATALAD_TESTS_NOTEARDOWN': '1'}):
        # we can't swallow outputs due to all the nosetests dances etc
        datalad.test('datalad.support.tests.test_status', verbose=0)