# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Pipeline to scrape abstracts information from online resource (e.g. for SfN 2015)"""

from ..nodes.crawl_url import crawl_url
from ..nodes.matches import a_href_match, xpath_match
from ..nodes.misc import Sink

# TODO: migrate to stock nodes package/module. make an io module probably
class dump_csv(object):
    """IO node to dump collected data as a csv"""
    def __init__(self, keys, filename=None, delimiter='\t'):
        self.keys = keys
        self.filename = filename
        self.delimiter = delimiter

    def __call__(self, data):
        # should be taken from data
        filename = data['filename'] if not self.filename else self.filename
        # TODO do actual dumping of keys of data as csv file
        yield data


def parse_abstract(data):
    data = data.copy()
    # TODO do parsing here and assign all interesting fields to data[] fields
    yield data


def pipeline(mkey=None, outputfile=None):
      crawler = crawl_url('http://www.abstractsonline.com/plan/start.aspx?mkey={%s}' % mkey)
      sink_abstracts = Sink(output='abstracts')
      # fields_sink = sink_dict(key='field', values='raw_value',
      #                         output='abstract_fields',
      #                         exclude_keys=('', 'Disclosures:')),
      return [
        [   # {'return_last': True, },
            crawler,
            a_href_match('.*/Browse.aspx'),
            crawler.recurse,
            a_href_match('.*/BrowseResults.aspx?date=(?P<date>[/0-9]*)'),
            crawler.recurse,
            a_href_match('.*/ViewSession.aspx?.*'),
            crawler.recurse,
            a_href_match('.*/ViewAbstract.aspx?mID=.*'),
            #[
              crawler.recurse,
              #fields_sink.reset,
              #xpath_match('//td[@class="ViewAbstractDataLabel"]',
              #   xpaths={'field': 'normalize-space(text())',
              #           'raw_value': 'following-sibling::td'}),
              xpath_match('//table[@cellpadding=3]'),
              # TODO:  do not match one by one, just get entire DIV and parse itout
              # into interesting fields
              parse_abstract,
              sink_abstracts,
              #return_from_pipeline(['abstract_fields'])
            #],
            # process_fields(key='abstract_fields',
            #                funcs={'Program#/Poster#:': extract_td_text,
            #                       'Authors:': fancy_authors_extractor,
            #                       {'Presentation time:', 'Presenter at Poster:'}: extract_date,
            #                       ...},
            #                default_func=extract_td_text),
            # dump_dict(keys=('...'), filename='output.csv')
        ],
        dump_csv(keys=('title', 'authors', '...'), filename=outputfile)
      ]