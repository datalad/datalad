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
from ...tests.utils import ok_, eq_

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
    input = """
        <div id="#container">'
            %s%s%s
            <span>magic</span>
        </div>""" % a_htmls


def _test_match_basic(matcher, query):
    m = matcher(query,
                xpaths={'text': 'text()'},
                csss={'favorite': '.class1::text'})

    mg = m(input="<div></div>")
    ok_(inspect.isgenerator(mg))
    eq_(list(mg), [])  # there should be no hits

    mg = m(input=sample1.input)
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    for hit, a_html, a_text, class1_text in zip(
            hits, sample1.a_htmls, sample1.a_texts, sample1.class1_texts):
        ok_(hit['input'])
        eq_(hit['output'], a_html)
        eq_(hit['text'], a_text)
        eq_(hit.get('favorite', None), class1_text)

def test_match_basic():
    yield _test_match_basic, xpath_match, '//a'
    yield _test_match_basic, css_match, 'a'
    yield _test_match_basic, a_href_match, '.*'

def test_a_href_match_basic():
    m = a_href_match('.*')

    mg = m(input=sample1.input)
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    eq_([u['url_text'] for u in hits], sample1.a_texts)
    eq_([u['url_href'] for u in hits], sample1.a_url_hrefs)
    # nothing done to url
    eq_([u['url'] for u in hits], sample1.a_url_hrefs)

    # if we do provide original url where it comes from -- result urls should be full
    mg = m(input=sample1.input, url="http://example.com/d/")
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
    eq_([u['url_text'] for u in hits], sample1.a_texts)
    eq_([u['url_href'] for u in hits], sample1.a_url_hrefs)
    eq_([u['url'] for u in hits], sample1.a_url_hrefs)

def test_a_href_match_pattern():
    m = a_href_match('.*')

    mg = m(input=sample1.input)
    ok_(inspect.isgenerator(mg))
    hits = list(mg)
    eq_(len(hits), 3)
