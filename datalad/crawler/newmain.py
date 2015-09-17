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

lgr = getLogger('datalad.crawler')


def _assure_listuple(obj):
    """Given an object, wrap into a tuple if not list or tuple
    """
    if isinstance(obj, list) or isinstance(obj, tuple):
        return obj
    return (obj,)

def crawl_url(parent_url, conditionals, meta={}):
    """Given a source url, perform crawling of the page

       with subsequent set of actions associated with each "conditional"

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


def initiate_handle(directory, uri, flavor):
    if exists(directory):
        lgr.info("Skipping %s since already exists" % directory)
        return
        # TODO verify flavor etc
    # well -- we will have a registry, so no explicit if code will be here
    if flavor == 'openfmri':
        init = initiate_openfmri_handle
    else:
        raise ValueError("Unknown flavor 'openfmri'")
    lgr.info("Initializing handle from %{uri}s under %{directory}s of flavor %{flavor}s using %{init}s" % locals())
    init = (directory, uri)


def initiate_openfmri_handle(directory, uri):
    if exists(directory):
        lgr.info("Skipping %s since already exists" % directory)
    # TODO:

class URLDB(object):
    """Database collating urls for the content across all handles

    Schema: TODO, but needs for sure

    - URL (only "public" or internal as for content from archives, or that separate table?)
    - common checksums which we might use/rely upon (MD5, SHA1, SHA256, SHA512)
    - last_checked (if online)
    - last_verified (when verified to contain the content according to the checksums

    allow to query by any known checksum
    """
    pass


class Annexificator(object):
    """A helper which would encapsulate operation of adding new content to git/annex repo

    """
    def __init__(self, path, mode=None, options=None):
        self.repo = AnnexRepo(path, create=False)
        self.mode = mode
        self.options = options or []

    def add(self, filenames):
        raise NotImplementedError()

    def addurl(self, url, filename=None):
        raise NotImplementedError()
        # TODO: register url within "The DB" after it was added
        self.register_url_in_db(url, filename)

    def register_url_in_db(self, url, filename):
        # might need to go outside -- since has nothing to do with self

    def __call__(self, filename=None, content_filename_request=False):
        """Return the "Action" callable which would do all the annexification

        Parameters
        ----------
        filename : str or None, optional
          Filename to be used
        content_filename_request : bool, optional
          Either to request the filename from the website to serve as a value
          for the filename
        """


def crawl_openfmri():
    # TODO: get to 'incoming branch'
    crawl_url("https://openfmri.org/datasets",
                 [# for crawling for datasets
                  (a_href_match("(?P<url>.*/dataset/ds0*(?P<dataset>[1-9][0-9]*))$")),
                   initiate_handle(directory="openfmri/%{dataset}s",
                                   uri="%{url}s",
                                   flavor="openfmri"))])


from os.path import curdir
def crawl_openfmri_dataset(dataset, path=curdir):
    annexer = Annexificator(path,
                            options=["-c", "annex.largefiles='exclude=*.txt'"])
    # TODO: url = get_crawl_config(directory)
    # I think it will be the internal knowledge of the "template"
    url = urljoin("https://openfmri.org/dataset", "ds%06d" % int(dataset))
    # TODO: cd directory.
    # TODO: get to 'incoming branch'
    crawl_url(
        url,
        # mixing hits by url's and then xpath -- might be real tricky
        #Action() API should be
        # parent_url=None, url=None, file=None, meta={})
        [ (a_href_match(".*release_history.txt", limit=1), annexer(filename="changelog.txt")),
          # (a_href_match(...) && not a_href_match(...)
          (a_href_match("ds.*_raw.tgz"
                        # TODO: might think about providing some checks, e.g. that we MUST
                        # have at least 1 hit of those, or may be in combination with some other
                        ), annexer(content_filename_request=False)),
          (a_href_match(".*dataset/ds[0-9]*$",
                        # extracted xpaths relevant to the url should be passed into the action
                        xpaths={"url_text": 'text()',
                                "parent_div": '../..'}),
                        ExtractOpenfMRIDatasetMeta("README.txt")),
          (xpath_match("TODO"), annexer(filename="license.txt")),
          # ad-hoc way to state some action to be performed for anything which matched any of prev rules
          (any_matched(), DontHaveAGoodExampleYet())
          # How to implement above without causing duplication... probably need to memo/cache all prev
          # hits
          ]
    )
    # master branch should then be based on 'incoming' but with some actions performed
    # TODO: switch to 'master'
    perform_actions(
        source_branch="incoming",
        merge_strategy="replace", # so we will remove original content of the branch, overlay content from source_branch, perform actions
        actions=[
            # so will take each
            ExtractArchives(
                #source_branch="incoming",
                regex="\.(tgz|tar\..*)$",
                renames=[
                    ("^[^/]*/(.*)", "\1") # e.g. to strip leading dir, or could prepend etc
                ],
                exclude="license.*", # regexp
                annexer
                )])
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

def crawl_ratholeradio():
    annexer = Annexificator(options=["-c", "annex.largefiles='exclude=*.cue and exclude=*.txt'"],
                                  mode='relaxed')
    # TODO: url = get_crawl_config(directory)
    # TODO: cd directory
    crawl_url('http://ratholeradio.org',
              [
                  (a_href_match('http://ratholeradio\.org/.*/ep(?P<episode>[0-9]*)/'),
                   recurse_crawl(url="%{url}s")),
                  (page_match('http://ratholeradio\.org/(?P<year>[0-9]*)/(?P<month>[0-9]*)/ep(?P<episode>[0-9]*)/')
                   && a_href_match('', xpaths='TODO'),
                   [annexer(filename="%{episode}003d-TODO.ogg"),
                    GenerateRatholeRadioCue(filename="%{episode}003d-TODO.cue"),
                    # Ha -- here to assign the tags we need to bother above files not urls!
                    # and we seems to not allow that easily
                    AssignAnnexTags(files="%{episode}003d-TODO.*",
                                    year="%(year)s",
                                    month="%(month)s")])
              ])

"""
    nih videos

        http://videocast.nih.gov/summary.asp?Live=16840&bhcp=1
        xpath_match('//a[contains(@href, ".f4v")][last()]',
            {"title": '//div[@class="blox-title"]//h3/text()',
             "date_field": '//b[text()="Air date:"]/../..//td[2]/text()[1]' }
"""