# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# now with some recursive structure of directories

from glob import glob
from os.path import exists, join as opj
from datalad.tests.utils import eq_, ok_
from datalad.tests.utils import serve_path_via_http, with_tree

from datalad.tests.utils import skip_if_scrapy_without_selector
skip_if_scrapy_without_selector()

from ..crawl_url import crawl_url
from ..crawl_url import parse_checksums
from ..matches import a_href_match
from ...pipeline import run_pipeline
from ....tests.utils import assert_equal
from ....tests.utils import assert_false
from ....tests.utils import SkipTest
from ....utils import updated

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

@with_tree(**pages_loop)
@serve_path_via_http()
def test_recurse_loop_http(path, url):
    def visit(url, matchers):
        return sorted((d['url'].replace(url, '')
                       for d in crawl_url(url, matchers=matchers)()))

    target_pages = ['', 'page2.html', 'page3.html', 'page4.html', 'page5.html']
    eq_(visit(url, [a_href_match('.*')]), target_pages)

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


def test_parse_checksums():
    response = """\
abc  f1.txt
bcd  d1/f1.txt
"""
    out = list(parse_checksums(digest='md5')(
            {'response': response,
            'url': 'http://example.com/subdir/checksums.md5'}))
    assert_equal(len(out), 2)
    assert_equal(out[0]['path'], '')
    assert_equal(out[0]['filename'], 'f1.txt')
    assert_equal(out[0]['url'], 'http://example.com/subdir/f1.txt')

    assert_equal(out[1]['path'], 'd1')
    assert_equal(out[1]['filename'], 'f1.txt')
    assert_equal(out[1]['url'], 'http://example.com/subdir/d1/f1.txt')
