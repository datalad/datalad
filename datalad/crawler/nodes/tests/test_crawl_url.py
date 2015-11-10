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
        # crawled_urls = sorted((d['url'].replace(url, '')
                                # for d in crawl_url_(url, matchers=matchers)()))
        crawled_urls = []
        for d in crawl_url_(url, matchers=matchers)():
            print '========================='
            print d
            print '=========================\n'
            crawled_urls.append(d['url'].replace(url, ''))

        return sorted(crawled_urls)

    eq_(visit(url, [a_href_match('.*')]), target_pages)


def test_recurse_loop_http():
    yield check_recurse_loop_http, crawl_url
    if PY2:
        # Skip testing of scrapy based crawler using py3 (not fully ported yet).
        yield check_recurse_loop_http, scrapy_crawl_url
        # run again to test that scrapy/twisted can be restarted from the same proc
        # yield check_recurse_loop_http, scrapy_crawl_url


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




# pages_loop = dict(
    # tree=(
        # ('index.html', """<html><body>
                            # <a href="page2.html">mypage2</a>
                            # <a href="page4.html">mypage4</a>
                          # </body></html>"""),
        # ('page2.html', 
                        # '''<html><body>
                                # <form action"page4.html" method="post">
                                # <input type="hidden" name="fn" value="pvc-1" />
                                # <table>
                                # <tr><td>username:</td><td><input type="text" name="username" /></td></tr>
                                # <tr><td>password:</td><td><input type="password" name="password" /></td></tr>
                                # </table>
                                # <input type="submit" name="submit" value="Login" />
                            # </body></html>'''

                        # # '''<html><body>
                            # # <script>
                            # # function checkIt()
                            # # {if(document.getElementById("username").value=="myusername" &&
                                # # document.getElementById("password").value=="mypassword")
                                # # location.href="page5.html";
                            # # else
                                # # location.href="/";
                            # # }
                            # # </script>

                            # # <form action"" method="post">
                            # # <input type="hidden" name="form_testing" value="for_log_in_page" />
                            # # <table>
                                # # <tr><td>Username: <input id="username" type="text"/></td></tr>
                                # # <tr><td>Password: <input id="password" type="password"/></td></tr>
                            # # </table>
                            # # <input type="button" value="Submit" onclick="checkIt()"/>
                        # # </body></html>'''
        # ),
        # ('page3.html', '<html><body><a href="/">root</a></body></html>'),
        # ('page4.html', '<html><body><a href="page5.html">mypage5</a></body></html>'),
        # ('page5.html', '<html><body><a href="page3.html">mypage3</a></body></html>'),
    # )
# )

# @with_tree(**pages_loop)
# @serve_path_via_http()
# def test_recurse_loop_http_with_form(path, url):
    # def visit(url, matchers):
        # if PY2:
            # login_info = dict(username='myusername', password='mypassword')
            # # crawled_urls = (d['url'].replace(url, '')
                            # # for d in scrapy_crawl_url(url, matchers=matchers, login_info=login_info)())
            # crawled_urls = []
            # for d in scrapy_crawl_url(url, matchers=matchers, login_info=login_info)():
                # crawled_urls.append(d['url'].replace(url, ''))
            # return sorted(crawled_urls)

    # eq_(visit(url, [a_href_match('.*')]), target_pages)





import glob
import httpretty
import requests

target_pages_with_form = ['', 'login_page2.html', 'dataset_page3.html', 'page4.html', 'page5.html']

login_form_pg = '''<html><body>
                     <form action="dataset_page3.html" method="post">
                     <input type="hidden" value="some_dataset" />
                     <table>
                       <tr><td>username:</td><td><input type="text" name="username" /></td></tr>
                       <tr><td>password:</td><td><input type="password" name="password" /></td></tr>
                     </table>
                     <input type="submit" name="submit" value="Login" />
                   </body></html>'''

pages_loop_with_form = dict((
        ('index.html', """<html><body> <a href="login_page2.html">login_page2</a> </body></html>"""),
        ('login_page2.html', login_form_pg),
        ('dataset_page3.html', '<html><body> <a href="page4.html">mypage4</a> </body></html>'),
        ('page4.html', '<html><body> <a href="page5.html">mypage5</a> </body></html>'),
        ('page5.html', '<html><body> <a href="/">root</a> </body></html>'),
    ))


# @with_tree(**pages_loop_with_form)
# @serve_path_via_http()
@httpretty.activate
# def test_recurse_loop_http_with_form_login(*args):
def test_recurse_loop_http_with_form_login():#path, url):
    # print args
    # print glob.glob(args[0] + '/*')
    # print glob.glob(path + '/*')
    # print path, url

    # def visit(url, matchers):
        # login_info = dict(username='myusername', password='mypassword')

        # httpretty.register_uri(httpretty.GET, url)#, body=d['response'])
        # crawled_urls = []
        # for d in scrapy_crawl_url(url, matchers=matchers, login_info=login_info)():
            # print '********************** d:'
            # print d
            # httpretty.register_uri(httpretty.GET, d['url'], #body=d['response'],
                                   # responses=[d['response']]
                                  # )
            # response = requests.get(d['url'])
            # assert response.content == d['response']

            # # response = requests.post(d['url'])#, {"username":"myusername", "password":"mypassword"})
            # # import pudb; pu.db
            
            # crawled_urls.append(d['url'].replace(url, ''))

        # print crawled_urls
        # return sorted(crawled_urls)
    
    ### Try outside of function 
    import os
    url = 'http://some_great_website.com'
    # httpretty.enable()
    for pg, response_body in pages_loop_with_form.items():
        httpretty.register_uri(httpretty.GET, os.path.join(url, pg), body=response_body)

    login_info = dict(username='myusername', password='mypassword')

    crawled_urls = []
    for d in crawl_url(url+'/index.html', matchers=[a_href_match('.*')])():#, login_info=login_info)():
        print '--------------------------'
        print d

    # httpretty.disable()
    # httpretty.reset()


    # for page in target_pages_with_form:

    # httpretty.register_uri(httpretty.POST, url,
                           # body=login_form_pg)
    # response = requests.post(url, {'username':'myusername', 'password':'mypassword'},
                            # )

    # eq_(visit(url, [a_href_match('.*')]), target_pages_with_form)
    # visit(url, [a_href_match('.*')])
