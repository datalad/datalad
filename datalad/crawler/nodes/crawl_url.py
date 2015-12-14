# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Basic crawler for the web
"""

from ...support.network import fetch_page
from ...utils import updated
from ...downloaders.providers import Providers

from logging import getLogger
lgr = getLogger('datalad.crawl.crawl_url')

class crawl_url(object):
    """Given a source url, perform the initial crawling of the page, i.e. simply
    bloody fetch it and pass along

    """
    def __init__(self,
                 url=None, matchers=None,
                 input='url',
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
        self._providers = Providers.from_config_files()

    def reset(self):
        """Reset cache of seen urls"""
        self._seen = set()

    def _visit_url(self, url, data):
        if url in self._seen:
            return
        self._seen.add(url)
        # this is just a cruel first attempt
        lgr.debug("Visiting %s" % url)
        page = self._providers.fetch(url)
        data_ = updated(data, zip(self._output, (page, url)))
        yield data_
        # now recurse if matchers were provided
        matchers = self._matchers
        if matchers:
            lgr.debug("Looking for more URLs at %s using %s", url, matchers)
            for matcher in (matchers if isinstance(matchers, (list, tuple)) else [matchers]):
                for data_matched in matcher(data_):
                    if 'url' not in data_matched:
                        lgr.warning("Got data without a url from %s" % matcher)
                        continue
                    # proxy findings
                    for data_matched_ in self._visit_url(data_matched['url'], data_matched):
                        yield data_matched_


    def __call__(self, data={}):
        #assert(data == {}) # atm assume we are the first of mogican
        url = data[self._input] if not self._url else self._url
        return self._visit_url(url, data)

    def recurse(self, data):
        """Recurse into the page - self._url gets ignored"""
        return self._visit_url(data[self._input], data)


"""
    for extractors, actions in conditionals:
        extractors = _assure_listuple(extractors)
        actions = _assure_listuple(actions)
        seen_urls = set()
        for extractor in extractors:
            for url, meta_ in extractor(parent_url, meta=meta):
                if url in seen_urls:
                    continue
                file = None
                # progress through actions while possibly augmenting the url, file, and/or meta_
                for action in actions:
                    # TODO: may be we should return a dict with whatever that action
                    # found necessary to change, update local state and pass into
                    url, file, meta_ = \
                        action(parent_url=parent_url, url=url, file=file, meta=meta_)
                seen_urls.add(url)
"""

