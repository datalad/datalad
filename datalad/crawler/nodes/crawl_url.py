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

class crawl_url(object):
    """Given a source url, perform the initial crawling of the page, i.e. simply
    bloody fetch it and pass along

    """
    def __init__(self, url=None,
                 input='url',
                 output=('response', 'url')):
        """If url is None, would try to pick it up from data[input]"""
        self._url = url
        self._input = input
        self._output = output

    def __call__(self, **data):
        #assert(data == {}) # atm assume we are the first of mogican
        url = data[self._input] if self._url is None else self._url

        # this is just a cruel first attempt
        yield updated(data, zip(self._output, (fetch_page(url), url)))

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

