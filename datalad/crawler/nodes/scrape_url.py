# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Basic web crawler/scraper using scrapy
"""

from ...utils import updated

import multiprocessing
import getpass
from logging import getLogger
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import CrawlSpider
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings

lgr = getLogger('datalad.crawl.scrape_url')



class crawl_url(object):
    """Given a source url, perform crawling of the page.
    NOTE: this implementation depends on scrapy, which
    has not yet been fully ported to python3.
    """

    def __init__(self, url=None, matchers=None, input='url',
                 output=('response', 'url'), login_info=None):
        """If url is None, would try to pick it up from data[input]

        Parameters
        ----------

        matchers: list of matchers
          Expect page content in and should produce url field

        login_info: dict of username and password (if required by the site) 
        """
        self._url = url
        self._matchers = matchers
        self._input = input
        self._output = output
        self._seen = set()
        self._login_info = login_info


    def reset(self):
        """Reset cache of seen urls"""
        self._seen = set()


    # def _visit_url(self, url, data, queue):
    def _visit_url(self, url, data, child_connection):

        def get_user_credentials():
            ''' returns dict of {'username': username, 'password': password}
            '''
            username = raw_input("Username: ")
            password = getpass.getpass()
            user_and_password = {'username': username, 'password': password}  
            # FIXME need to try out these values to see if it actually logs the user in or not; like give
            # three chances to login before bailing or something like that.
            #assert len([v for v in user_and_password.values() if v]) == 2, "ERROR: need to enter correct value for both 'username' and 'password'"
            return user_and_password


        class ScrapySpider(CrawlSpider):
            name = "scrapyspider"     # NOTE this must be uncommented for the spider to work
            # allowed_domains = ["abstractsonline.com"]

            start_urls = [url]

            # settings = get_project_settings()
            # settings.setdict({'LOG_ENABLED': False})


            def parse(self_, response):

                if response.xpath('//form'):
                    if self._login_info:
                        user_and_password_dict = self._login_info
                    else:
                        print("NEED TO LOG IN to\n" + response.url)
                        user_and_password_dict = get_user_credentials() #FIXME don't think this will work from in seperate proc like this
                        # user_and_password_dict = child_connection.send(get_user_credentials()) #TODO might need something like this
                    form_request = scrapy.FormRequest.from_response(response,
                                            formdata=user_and_password_dict)#, callback=self.parse)
                    yield form_request

                else:
                    if not response.url in self._seen:
                        self._seen.add(response.url)

                        data_ = updated(data, zip(self._output, (response.body, response.url)))
                        # queue.put(data_)
                        child_connection.send(data_)

                        matchers = self._matchers
                        if matchers:
                            lgr.debug("Looking for more URLs at %s using %s", response.url, [m._query for m in matchers])
                            for matcher in (matchers if isinstance(matchers, (list, tuple)) else [matchers]):
                                for data_matched in matcher(data_):
                                    if 'url' not in data_matched:
                                        lgr.warning("Got data without a url from %s" % matcher)
                                        continue

                                    yield scrapy.Request(data_matched['url'])#, callback=self.parse) 


        settings = Settings()
        # settings.setdict({'LOG_ENABLED': False})
        settings.setdict({'LOG_LEVEL': 'CRITICAL'})   # http://doc.scrapy.org/en/latest/topics/settings.html#log-level
        process = CrawlerProcess(settings)
        # process = CrawlerProcess()    # for settings set inside the crawler just do this
        process.crawl(ScrapySpider())
        process.start()
        child_connection.send('STOP')


    def __call__(self, data={}):
        url = data[self._input] if not self._url else self._url

        # queue = multiprocessing.Queue()
        # multi_proc = multiprocessing.Process(target=self._visit_url, args=(url, data, queue))
        # multi_proc.start()

        # while multi_proc.is_alive():
            # try:
                # data_ = queue.get(timeout=.1)
                # yield data_
            # except multiprocessing.queues.Empty:
                # pass

        # queue_output = None
        # while queue_output != 'STOP':
            # try:
                # queue_output = queue.get(timeout=.1)
                # if queue_output != 'STOP':
                    # data_ = queue_output
                    # yield data_
            # # from Queue import Empty
            # # except Empty:
            # except multiprocessing.queues.Empty:
                # pass
        # using a PIPE
        parent_connection, child_connection = multiprocessing.Pipe()
        multi_proc = multiprocessing.Process(target=self._visit_url, args=(url, data, child_connection))
        multi_proc.start()
        child_output = None
        while child_output != 'STOP':
            child_output = parent_connection.recv()
            if child_output != 'STOP':
                data_ = child_output
                yield data_


    def recurse(self, data):
        """Recurse into the page - self._url gets ignored"""
        # return self._visit_url(data[self._input], data)
        raise NotImplementedError
