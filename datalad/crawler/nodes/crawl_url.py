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

from os.path import splitext, dirname, basename
from ...utils import updated
from ...dochelpers import exc_str
from ...downloaders.base import DownloadError
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
                 failed=None,
                 output=('response', 'url')):
        """If url is None, would try to pick it up from data[input]

        Parameters
        ----------

        matchers: list of matchers
          Expect page content in and should produce url field
        failed: {skip}, optional
          What to do about failing urls. If None -- would consult (eventually) the config
        """
        self._url = url
        self._matchers = matchers
        self._input = input
        self._output = output
        self._seen = set()
        self._providers = Providers.from_config_files()
        self.failed = failed

    def reset(self):
        """Reset cache of seen urls"""
        self._seen = set()

    def _visit_url(self, url, data):
        if url in self._seen:
            return
        self._seen.add(url)
        # this is just a cruel first attempt
        lgr.debug("Visiting %s" % url)
        try:
            page = self._providers.fetch(url)
        except DownloadError as exc:
            lgr.warning("URL %s failed to download: %s" % (url, exc_str(exc)))
            if self.failed in {None, 'skip'}:
                # TODO: config  -- failed='skip' should be a config option, for now always skipping
                return
            raise  # otherwise -- kaboom

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

# TODO: probably might sense to RF into just a generic TSV file parser
def parse_checksums(digest=None):
    """Generates a node capable of parsing checksums file and generating new URLs

    Base of the available in data url is used for new URLs
    """
    def _parse_checksums(data):
        url = data['url']
        urlsplit = url.split('/')
        topurl = '/'.join(urlsplit[:-1])
        if digest is None:
            # deduce from url's file extension
            filename = urlsplit[-1]
            base, ext = splitext(filename)
            digest_ = ext if ext else digest

        content = data['response']
        # split into separate lines, first entry is checksum, 2nd file path
        for line in content.split('\n'):
            if not line:  # empty line
                continue
            checksum, fpath = line.split(None, 1)
            yield updated(data, {'digest': digest or digest_,
                                 'checksum': checksum,
                                 'path': dirname(fpath),
                                 'filename': basename(fpath),
                                 'url': "%s/%s" % (topurl, fpath)
                                 })
    return _parse_checksums