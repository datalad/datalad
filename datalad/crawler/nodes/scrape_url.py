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

import multiprocessing
from logging import getLogger
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import CrawlSpider
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


    def _visit_url(self, url, data, queue):

        class ScrapySpider(CrawlSpider):
            name = "scrapyspider"     # NOTE this must be uncommented for the spider to work
            # allowed_domains = ["abstractsonline.com"]

            start_urls = [url]

            # settings = get_project_settings()
            # settings.setdict({'LOG_ENABLED': False})


            def parse(self_, response):

                if not response.url in self._seen:
                    self._seen.add(response.url)

                    data_ = updated(data, zip(self._output, (response.body, response.url)))
                    queue.put(data_)

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


    def __call__(self, data={}):
        url = data[self._input] if not self._url else self._url
        queue = multiprocessing.Queue()
        multi_proc = multiprocessing.Process(target=self._visit_url, args=(url, data, queue))
        multi_proc.start()
        while multi_proc.is_alive():
            try:
                data_ = queue.get(timeout=.1)
                yield data_
            except multiprocessing.queues.Empty:
                pass


    def recurse(self, data):
        """Recurse into the page - self._url gets ignored"""
        # return self._visit_url(data[self._input], data)
        raise NotImplementedError

