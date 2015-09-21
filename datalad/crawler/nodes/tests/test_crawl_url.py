# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# now with some recursive structure of directories

from datalad.tests.utils import eq_, ok_
from datalad.tests.utils import serve_path_via_http, with_tree
from ..crawl_url import crawl_url
from ..matches import a_href_match

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

    eq_(visit(url, [a_href_match('.*')]), ['', 'page2.html', 'page3.html', 'page4.html', 'page5.html'])