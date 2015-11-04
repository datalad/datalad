# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

# In new design there is no public/incoming -- but there will be multiple branches
# No actions performed in "incoming" branches

__docformat__ = 'restructuredtext'

from os.path import exists

from logging import getLogger
from six.moves.urllib.parse import urljoin

from ..support.annexrepo import AnnexRepo
from .nodes.matches import *

lgr = getLogger('datalad.crawler')


def _assure_listuple(obj):
    """Given an object, wrap into a tuple if not list or tuple
    """
    if isinstance(obj, list) or isinstance(obj, tuple):
        return obj
    return (obj,)



def initiate_handle(directory, template, **params):
    if exists(directory):
        lgr.info("Skipping %s since already exists" % directory)
        return
        # TODO verify flavor etc
    # well -- we will have a registry, so no explicit if code will be here
    if template == 'openfmri':
        init = initiate_openfmri_handle
    else:
        raise ValueError("Unknown flavor 'openfmri'")
    lgr.info("Initializing handle from %{uri}s under %{directory}s of flavor %{flavor}s using %{init}s "
             "with params %{params}s" % locals())
    init(directory, uri, **params)




from os.path import curdir
def crawl_openfmri_dataset(dataset, path=curdir):
    annexer = Annexificator(path,
                            options=["-c", "annex.largefiles='exclude=*.txt'"])
    # TODO: url = get_crawl_config(directory)
    # I think it will be the internal knowledge of the "template"
    url = urljoin("https://openfmri.org/dataset", "ds%06d" % int(dataset))
    # TODO: cd directory.
    # TODO: get to 'incoming branch'
    return [
        annexer.switch_branch('incoming'),
        [
            crawl_url(url),
            # mixing hits by url's and then xpath -- might be real tricky
            #Action() API should be
            # parent_url=None, url=None, file=None, meta={})
            ( a_href_match(".*release_history.txt", limit=1),
              annexer(filename="changelog.txt")),
            # (a_href_match(...) && not a_href_match(...)
            ( a_href_match("ds.*_raw.tgz"
                           # TODO: might think about providing some checks, e.g. that we MUST
                           # have at least 1 hit of those, or may be in combination with some other
                          ),
              annexer(content_filename_request=False)),
            ( a_href_match(".*dataset/ds[0-9]*$",
                           # extracted xpaths relevant to the url should be passed into the action
                           xpaths={"url_text": 'text()',
                                   "parent_div": '../..'}),
              ExtractOpenfMRIDatasetMeta(opj(path, "README.txt")),
              annexer()),
            ( xpath_match("TODO"),
              annexer(filename="license.txt") ),
            # ad-hoc way to state some action to be performed for anything which matched any of prev rules
            # (any_matched(), DontHaveAGoodExampleYet())
            # How to implement above without causing duplication... probably need to memo/cache all prev
            # hits
        ],
        annexer.commit(),  # assure that we commit what we got so far. TODO: automagic by switch_branch?
        annexer.switch_branch('master'),
        ExtractArchives(
            # will do the merge of 'replace' strategy
            source_branch="incoming",
            regex="\.(tgz|tar\..*)$",
            renames=[
                ("^[^/]*/(.*)", "\1") # e.g. to strip leading dir, or could prepend etc
            ],
            exclude="license.*", # regexp
            ),
        annexer(),
        annexer.commit(),
    ]
    # master branch should then be based on 'incoming' but with some actions performed
    # TODO: switch to 'master'
    #perform_actions(
    #    merge_strategy="replace", # so we will remove original content of the branch, overlay content from source_branch, perform actions
    #    actions=[
    #        # so will take each
    # in principle could may be implemented in the same fashion as crawl_url where for each
    # file it would spit out

def crawl_openfmri_s3():
    # demo for versioned buckets
    # annexer should be the same pretty much
    annexer = Annexificator(options=["-c", "annex.largefiles='exclude=*.txt'"])
    # TODO: url = get_crawl_config(directory)
    # TODO: cd directory
    # TODO: get to 'incoming branch'
    crawl_s3_bucket(
        'openfmri',
        public=True, # means that we would rely/generate http urls, for private -- s3://
        # actually may be always s3:// so we could switch dynamically between regions???
        # prefix='',
        from_last_modified='XXX', # if known for this crawler. we need to store within handle
        # should crawl for 1 "revision" as figured out until a new update for something just fetched comes in
        actions=[
            # just everything should be annexed and registered in the DB
            (a_href_match(".*"), annexer())
        ]
        # but then how should crawl_ report that everything was fetched  etc
    )

# TODO: figshare
# TODO: ratholeradio
class GenerateRatholeRadioCue(object):
    def __init__(self, filename):
        self.filename = filename
    def __call__(self, el, tags):
        raise NotImplementedError()

def crawl_ratholeradio():
    annexer = Annexificator(options=["-c", "annex.largefiles='exclude=*.cue and exclude=*.txt'"],
                            mode='relaxed')
    # TODO: url = get_crawl_config(directory)
    # TODO: cd directory
    return [
        crawl_url('http://ratholeradio.org'),
        a_href_match('http://ratholeradio\.org/.*/ep(?P<episode>[0-9]*)/'),
        crawl_url.recurse(url="%{url}s"),
        # stop -- how to recurse entirely?...
        page_match('http://ratholeradio\.org/(?P<year>[0-9]*)/(?P<month>[0-9]*)/ep(?P<episode>[0-9]*)/'),
        a_href_match('.*\.ogg', xpaths='TODO'),
        annexer(filename="%{episode}003d-TODO.ogg"),
        GenerateRatholeRadioCue(filename="%{episode}003d-TODO.cue"),
        # Ha -- here to assign the tags we need to bother above files not urls!
        # and we seems to not allow that easily
        AssignAnnexTags(files="%{episode}003d-TODO.*",
                        year="%(year)s",
                        month="%(month)s")
    ]

"""
    nih videos

        http://videocast.nih.gov/summary.asp?Live=16840&bhcp=1
        xpath_match('//a[contains(@href, ".f4v")][last()]',
            {"title": '//div[@class="blox-title"]//h3/text()',
             "date_field": '//b[text()="Air date:"]/../..//td[2]/text()[1]' }
"""

"""
SfN program

interesting case it to allow to extract things from some structure and then group
them within a single data item e.g. dict

e.g.
http://www.abstractsonline.com/plan/ViewAbstract.aspx\?mID\=3744\&sKey\=64008424-c04d-40ad-9f9e-547223d7fab4\&cKey\=9ae8e7d9-7bf7-4013-a845-034079db07c3\&mKey\=d0ff4555-8574-4fbb-b9d4-04eec8ba0c84
[(h.xpath('text()').extract(), h.xpath('following-sibling::td').extract()) for h in response.xpath('//td[@class="ViewAbstractDataLabel"]')]

should look like a separate pipeline from which we would want to actually return some field

  crawler = crawl_url('http://www.abstractsonline.com/plan/Browse.aspx')

  fields_sink = sink_dict(key='field', values='raw_value',
                          output='abstract_fields',
                          exclude_keys=('', 'Disclosures:')),
  [
    crawler,
    a_href_match('.*/BrowseResults.aspx?date=(?P<date>[/0-9]*)'),
    crawler.recurse,
    a_href_match('.*/ViewSession.aspx?.*'),
    crawler.recurse,
    a_href_match('.*/ViewAbstract.aspx?mID=.*'),
    [
      crawler.recurse,
      fields_sink.reset,
      xpath_match('//td[@class="ViewAbstractDataLabel"]',
         xpaths={'field': 'normalize-space(text())',
                 'raw_value': 'following-sibling::td'}),
      fields_sink,
      return_from_pipeline(['abstract_fields'])
    ],
    process_fields(key='abstract_fields',
                   funcs={'Program#/Poster#:': extract_td_text,
                          'Authors:': fancy_authors_extractor,
                          {'Presentation time:', 'Presenter at Poster:'}: extract_date,
                          ...},
                   default_func=extract_td_text),


which then pipeline runner would comprehend to maintain and return (or yield??) the last value
although it starts to feel that may be regular scrapy/slybot could be more appropriate
since we do not even want much...  BUT on other hand we could even simply add

    dump_dict(keys=('...'), filename='output.csv')

]
and be done!
"""