# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Basic crawler for the web using scrapy
"""

from ...utils import updated

from logging import getLogger
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings

lgr = getLogger('datalad.crawl.scrape_url')




class crawl_url(object):
    """Given a source url, perform the initial crawling of the page, i.e. simply
    bloody fetch it and pass along
    """

    def __init__(self, url=None, matchers=None, input='url',
                 output=('response', 'url')):
        """If url is None, would try to pick it up from data[input]

        Parameters
        ----------

        matchers: list of matchers
          Expect page content in and should produce url field
        """
        self._url = url
        self._matchers = matchers
        self._input = input
        self._output = output
        self._seen = set()


    def reset(self):
        """Reset cache of seen urls"""
        self._seen = set()


    def _visit_url(self, url, data):

        visited_pages = []

        class ScrapySpider(CrawlSpider):
            name = "scrapyspider"     # NOTE this must be uncommented for the spider to work
            # allowed_domains = ["abstractsonline.com"]

            start_urls = [url]

            # settings = get_project_settings()
            # settings.setdict({'LOG_ENABLED': False})


            def parse(self_, response):

                # print '------------------'
                # print response.url
                # # print self._seen
                # print [page_url for page_html, page_url in visited_pages] 
                # print '------------------'

                if not response.url in self._seen:
                    self._seen.add(response.url)

                    visited_pages.append((response.body, response.url))

                    data_ = updated(data, zip(self._output, visited_pages[-1]))
                    matchers = self._matchers
                    # import pudb; pu.db
                    if matchers:
                        lgr.debug("Looking for more URLs at %s using %s", response.url, [m._query for m in matchers])
                        for matcher in (matchers if isinstance(matchers, (list, tuple)) else [matchers]):
                            print '=========================='
                            print matcher._query
                            print '=========================='
                            for data_matched in matcher(data_):
                                if 'url' not in data_matched:
                                    lgr.warning("Got data without a url from %s" % matcher)
                                    continue

                                # print 'url', data_matched['url']
                                yield scrapy.Request(data_matched['url']#, callback=self.parse, 
                                                    )


        settings = Settings()
        # settings.setdict({'LOG_ENABLED': False})
        # settings.setdict({'LOG_LEVEL': 'CRITICAL'})   # http://doc.scrapy.org/en/latest/topics/settings.html#log-level
        process = CrawlerProcess(settings)
        # process = CrawlerProcess()    # for settings set inside the crawler just do this
        process.crawl(ScrapySpider())
        process.start()

        for page, url in visited_pages:
            data_ = updated(data, zip(self._output, (page, url)))
            yield data_


    def __call__(self, data={}):
        #assert(data == {}) # atm assume we are the first of mogican
        url = data[self._input] if not self._url else self._url
        return self._visit_url(url, data)


    def recurse(self, data):
        """Recurse into the page - self._url gets ignored"""
        raise NotImplementedError
        # return self._visit_url(data[self._input], data)

