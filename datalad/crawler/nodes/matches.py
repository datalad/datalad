# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers to match and generate urls and extracted content"""

__docformat__ = 'restructuredtext'

import re

from scrapy.selector import Selector
from scrapy.http import Response

from ...utils import updated
from ...support.network import dlurljoin

from logging import getLogger
lgr = getLogger('datalad.crawler')

# for now heavily based on scrapy but we might make the backend
# replaceable
class ExtractorMatch(object):
    """Generic matching extractor
    """

    def __init__(self, query, input='response', output='match', pop_input=False,
                 allow_multiple=False, xpaths=None, csss=None):
        self._query = query
        # allow_multiple concerns only extraction of additional xpaths and csss
        self._allow_multiple = allow_multiple
        self._xpaths = xpaths
        self._csss = csss
        self._input = input
        self._output = output
        self._pop_input = False

    def _select_and_extract(self, selector, query, data):
        raise NotImplementedError

    def __call__(self, **data):
        input = data.pop(self._input) if self._pop_input else data[self._input]

        if isinstance(input, Response):
            selector = Selector(response=input)
            if hasattr(input, 'url') and input.url and (not 'url' in data):
                # take the url of the response object
                data = updated(data, {'url': input.url})
        else:
            selector = Selector(text=input)

        for entry, data_ in self._select_and_extract(selector, self._query, data):
            data_ = updated(data_, {self._output: entry.extract()})
            # now get associated xpaths, csss etc
            for selectors_dict, entry_method in ((self._xpaths, entry.xpath),
                                                 (self._csss, entry.css)):
                if not selectors_dict:
                    continue
                for key in selectors_dict:
                    key_extracted = entry_method(selectors_dict[key]).extract()
                    if not len(key_extracted):
                        # TODO: warning, make mandatory to have a hit if expected?
                        continue
                    if len(key_extracted) > 1:
                        if self._allow_multiple:
                            raise NotImplementedError("Don't know what to do yet with this one")
                        else:
                            lgr.warn(
                                "Got multiple selections for xpath query %s. "
                                "Keeping only the first one: %s" % (repr(query), key_extracted[0]))
                    data_[key] = key_extracted[0]
            yield data_


class ScrapyExtractorMatch(ExtractorMatch):

    EXTRACTOR = None  # Defined in subclasses

    def _select_and_extract(self, selector, query, data):
        for extracted in self.EXTRACTOR(selector, query):
            yield extracted, data


class xpath_match(ScrapyExtractorMatch):
    EXTRACTOR = Selector.xpath


class css_match(ScrapyExtractorMatch):
    EXTRACTOR = Selector.css


class a_href_match(ExtractorMatch):
    """Helper to simplify matching based on URL while also extracting various tags from URL while at it

    Given a url regular expression pattern, perform matching among available URLs
    and yield those of interest, while also yielding additional groups which matched.
    It will return keys 'url', 'url_href', 'url_text' and the original .extracted()
    entry for the url extractor in the field specified by output argument
    """

    def _select_and_extract(self, selector, query, data):
        prev_url = data.get('url', None)
        url_query = re.compile(query)
        for url_e in selector.xpath('//a'):
            url = url_href = url_e.xpath('@href').extract_first()
            if not url:
                # it was an <a> without href
                continue

            # make it a full url, if there was an original url
            if prev_url:
                url = dlurljoin(prev_url, url_href)

            url_regex = url_query.match(url)
            if not url_regex:
                continue

            # enrich data with extracted keywords
            data_ = data.copy()
            for k, v in url_regex.groupdict().items():
                data_[k] = v

            # TODO: such actions we might want to perform also in other cases,
            # e.g. operating on some extracted with XPATH content
            data_['url'] = url
            data_['url_href'] = url_href
            data_['url_text'] = url_e.xpath('text()').extract_first()
            yield url_e, data_

