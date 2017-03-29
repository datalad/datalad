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
import types

from six import PY3

from ...utils import updated
from ...support.network import dlurljoin
from ...utils import auto_repr

from logging import getLogger
lgr = getLogger('datalad.crawler')

try:
    from scrapy.http import Response
    from scrapy.selector import Selector
except ImportError:  # pragma: no cover
    lgr.debug("Failed to import Selector from scrapy, so matches would not be functional")
    class Selector(object):
        xpath = css = None
    Response = None


# for now heavily based on scrapy but we might make the backend
# replaceable
@auto_repr
class ExtractorMatch(object):
    """Generic matching extractor
    """

    def __init__(self, query, input='response', output='match', pop_input=False,
                 allow_multiple=False, xpaths=None, csss=None, min_count=None,
                 max_count=None):
        """"""
        # TODO: define arguments
        self.query = query
        # allow_multiple concerns only extraction of additional xpaths and csss
        self._allow_multiple = allow_multiple
        self._xpaths = xpaths
        self._csss = csss
        self._input = input
        self._output = output
        self._pop_input = False
        self._min_count = min_count
        self._max_count = max_count

    def _select_and_extract(self, selector, query, data):  # pragma: no cover
        raise NotImplementedError

    def __call__(self, data):
        input = data.pop(self._input) if self._pop_input else data[self._input]

        if isinstance(input, Response):
            selector = Selector(response=input)
            if hasattr(input, 'url') and input.url and ('url' not in data):
                # take the URL of the response object
                data = updated(data, {'url': input.url})
        else:
            selector = Selector(text=input)

        count = 0
        for entry, data_ in self._select_and_extract(selector, self.query, data):
            data_ = updated(data_, {self._output: entry.extract()})
            # now get associated xpaths, css, etc
            for selectors_dict, entry_method in ((self._xpaths, entry.xpath),
                                                 (self._csss, entry.css)):
                if not selectors_dict:
                    continue
                for key in selectors_dict:
                    selector_ = selectors_dict[key]
                    key_extracted = entry_method(selector_).extract()
                    if not len(key_extracted):
                        # TODO: warning, make mandatory to have a hit if expected?
                        continue
                    if len(key_extracted) > 1:
                        if self._allow_multiple:
                            data_[key] = key_extracted
                            # raise NotImplementedError("Don't know what to do yet with this one")
                        else:
                            lgr.warn(
                                "Got multiple selections for xpath query %s. "
                                "Keeping only the first one: %s" % (repr(selector_), key_extracted[0]))
                            data_[key] = key_extracted[0]
                    else:
                        data_[key] = key_extracted[0]
            count += 1
            yield data_

        if self._min_count and count < self._min_count:
            raise ValueError("Did not match required %d matches (got %d) using %s"
                             % (self._min_count, count, self))

        if self._max_count and count > self._max_count:
            raise ValueError("Matched more than %d matches (got %d) using %s"
                             % (self._max_count, count, self))


class ScrapyExtractorMatch(ExtractorMatch):

    EXTRACTOR = None  # defined in subclasses

    def _select_and_extract(self, selector, query, data):
        # there must be some magic happening since originally
        # (when just parsing the code) those are unbound (func)
        # and then somehow become bound
        if PY3 and isinstance(self.EXTRACTOR, types.MethodType):
            self.EXTRACTOR = self.EXTRACTOR.__func__
        for extracted in self.EXTRACTOR(selector, query):
            yield extracted, data


class xpath_match(ScrapyExtractorMatch):
    EXTRACTOR = Selector.xpath


class css_match(ScrapyExtractorMatch):
    EXTRACTOR = Selector.css


class AExtractorMatch(ExtractorMatch):
    """Helper to simplify matching of URLs based on their HREF or text
    """

    # abstract -- must be defined in subclass
    #_TARGET = None

    def _select_and_extract(self, selector, query, data):
        prev_url = data.get('url', None)
        url_query = re.compile(query)
        for url_e in selector.xpath('//a'):
            url = url_href = url_e.xpath('@href').extract_first()
            if not url:
                # it was an <a> without href
                continue

            # make it a full URL, if there was an original URL
            if prev_url:
                url = dlurljoin(prev_url, url_href)

            if self._TARGET == 'href':
                regex_target = url
            elif self._TARGET == 'text':
                regex_target = url_e.xpath('text()').extract_first()
            else:
                raise ValueError("Unknown _TARGET=%r" % (self._TARGET,))

            regex = url_query.match(regex_target)
            if not regex:
                continue

            # enrich data with extracted keywords
            data_ = data.copy()
            for k, v in regex.groupdict().items():
                data_[k] = v

            # TODO: such actions we might want to perform also in other cases,
            # e.g. operating on some extracted with XPATH content
            data_['url'] = url
            data_['url_href'] = url_href
            data_['url_text'] = url_e.xpath('text()').extract_first()
            lgr.log(5, "Matched %(url)s" % data_)

            yield url_e, data_


class a_href_match(AExtractorMatch):
    """Helper to simplify matching based on URL while also extracting various tags from URL while at it

    Given a URL regular expression pattern, perform matching among available URLs
    and yield those of interest, while also yielding additional groups which matched.
    It will return keys 'url', 'url_href', 'url_text' and the original '.extracted()'
    entry for the url extractor in the field specified by the output argument
    """
    _TARGET = 'href'


class a_text_match(AExtractorMatch):
    """Helper to simplify matching based on a target's text while also extracting various tags from it while at it

    """
    _TARGET = 'text'
