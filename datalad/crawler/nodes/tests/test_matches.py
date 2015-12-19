# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import inspect
from nose import SkipTest
from ..matches import *
from datalad.tests.utils import ok_, eq_, assert_raises

try:
    import scrapy
except ImportError:
    raise SkipTest("Needs scrapy")

class sample1:
    # there could be some html normalization effects, so using " within for now
    a_htmls = (
               '<a id="#l1" href="/">/</a>',
               '<a id="#l2" href="buga/duga/du" class="class1">somewhere</a>',
               '<a href="http://example.com" class="class2">else</a>'
    )
    a_texts = ['/', 'somewhere', 'else']
    a_url_hrefs = ['/', 'buga/duga/du', 'http://example.com']
    class1_texts = [None, 'somewhere', None]
    response = """
        <div id="#container">'
            %s%s%s
            <span>magic</span>
        </div>""" % a_htmls


def _test_match_basic(matcher, query):
    extracts = dict(
        xpaths={'text': 'text()'},
        csss={'favorite': '.class1::text'}
    )
    m = matcher(query, **extracts)

    mg = m(dict(response="<div></div>"))
    ok_(inspect.isgenerator(mg))
    eq_(list(mg), [])  # there should be no hits

    mg = m(dict(response=sample1.response))
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    for hit, a_html, a_text, class1_text in zip(
            hits, sample1.a_htmls, sample1.a_texts, sample1.class1_texts):
        ok_(hit['response'])
        eq_(hit['match'], a_html)
        eq_(hit['text'], a_text)
        eq_(hit.get('favorite', None), class1_text)

    m = matcher(query, min_count=4, **extracts)
    mg = m(dict(response=sample1.response))
    ok_(inspect.isgenerator(mg))
    assert_raises(ValueError, list, mg)

    m = matcher(query, max_count=2, **extracts)
    mg = m(dict(response=sample1.response))
    ok_(inspect.isgenerator(mg))
    assert_raises(ValueError, list, mg)


def test_match_basic():
    yield _test_match_basic, xpath_match, '//a'
    yield _test_match_basic, css_match, 'a'
    yield _test_match_basic, a_href_match, '.*'

def test_a_href_match_basic():
    m = a_href_match('.*')

    mg = m(dict(response=sample1.response))
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    eq_([u['url_text'] for u in hits], sample1.a_texts)
    eq_([u['url_href'] for u in hits], sample1.a_url_hrefs)
    # nothing done to url
    eq_([u['url'] for u in hits], sample1.a_url_hrefs)

    # if we do provide original url where it comes from -- result urls should be full
    mg = m(dict(response=sample1.response, url="http://w.example.com:888/d/"))
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    eq_([u['url_text'] for u in hits], sample1.a_texts)
    eq_([u['url_href'] for u in hits], sample1.a_url_hrefs)
    eq_([u['url'] for u in hits],
        ['http://w.example.com:888/', 'http://w.example.com:888/d/buga/duga/du', 'http://example.com'])

def test_a_href_match_pattern1():
    m = a_href_match('.*buga/(?P<custom>.*)/.*')

    hits = list(m(dict(response=sample1.response)))
    eq_(len(hits), 1)
    hit = hits[0]
    eq_(hit['url'], 'buga/duga/du')
    eq_(hit['custom'], 'duga')

def test_a_href_match_pattern2():
    m = a_href_match('.*(?P<custom>.a).*')

    hits = list(m(dict(response=sample1.response)))
    eq_(len(hits), 2)
    eq_([u['url'] for u in hits], ['buga/duga/du', 'http://example.com'])
    eq_([u['custom'] for u in hits], ['ga', 'xa'])

def test_a_href_match_pattern3():
    # that we would match if top url was provided as well
    m = a_href_match('.*(?P<custom>bu..).*')

    hits = list(m(dict(response=sample1.response, url="http://w.buxxxx.com/")))
    eq_(len(hits), 2)
    eq_([u['url'] for u in hits], ['http://w.buxxxx.com/', 'http://w.buxxxx.com/buga/duga/du'])
    eq_([u['custom'] for u in hits], ['buxx', 'buga'])
