# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# now with some recursive structure of directories

from six import PY2
from datalad.tests.utils import eq_
from datalad.tests.utils import serve_path_via_http, with_tree
from ..crawl_url import crawl_url
from ..scrape_url import crawl_url as scrapy_crawl_url
from ..matches import a_href_match
from ...pipeline import run_pipeline

pages_loop = dict(
    tree=(
        ('index.html', """<html><body>
                            <a href="page2.html">mypage2</a>
                            <a href="page4.html">mypage4</a>
                          </body></html>"""),
        ('page2.html', '<html><body><a href="page3.html">mypage3</a></body></html>'),
        ('page3.html', '<html><body><a href="/">root</a></body></html>'),
        ('page4.html', '<html><body><a href="page5.html">mypage5</a></body></html>'),
        ('page5.html', '<html><body><a href="page3.html">mypage3</a></body></html>'),
    )
)

target_pages = ['', 'page2.html', 'page3.html', 'page4.html', 'page5.html']


@with_tree(**pages_loop)
@serve_path_via_http()
def check_recurse_loop_http(crawl_url_, path, url):
    def visit(url, matchers):
        crawled_urls = sorted((d['url'].replace(url, '')
                                for d in crawl_url_(url, matchers=matchers)()))
        return crawled_urls

    eq_(visit(url, [a_href_match('.*')]), target_pages)


def test_recurse_loop_http():
    yield check_recurse_loop_http, crawl_url

    if PY2:
        # Skip testing of scrapy based crawler using py3 (not fully ported yet).
        yield check_recurse_loop_http, scrapy_crawl_url
        # run again to test that scrapy/twisted can be restarted from the same proc
        yield check_recurse_loop_http, scrapy_crawl_url


@with_tree(**pages_loop)
@serve_path_via_http()
def test_recurse_loop_http2(path, url):
    # test recursive loop as implemented by pipeline
    crawler = crawl_url(url)
    pipeline = [
        {'output': 'outputs'},  # just to simplify testing here
        crawler,
        [
            {'loop': True, 'output': 'input+outputs'},
            a_href_match('.*'),
            crawler.recurse
        ]
    ]
    pipeline_results = run_pipeline(pipeline)
    eq_(sorted([d['url'].replace(url, '') for d in pipeline_results]), target_pages)
