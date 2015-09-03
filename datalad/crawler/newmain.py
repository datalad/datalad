# In new design there is no public/incoming -- but there will be multiple branches
# No actions performed in "incoming" branches

from os.path import exists

from ..support.annexrepo import AnnexRepo
from logging import getLogger
lgr = getLogger('datalad.crawler')

def crawl_url(url, conditionals, annexificator):
    """Given a source url, perform crawling of the page

       with subsequent set of actions associated with each "conditional"

    """

    return TODO


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


class Annexificator(object):
    """A helper which would enapsulate operation of adding new content to git/annex repo

    """
    def __init__(self, path, options=None):
        self.repo = AnnexRepo(path, create=False)
        self.options = options or []

    def add(self, filenames):
        raise NotImplementedError()

    def addurl(self, url, filename=None):
        raise NotImplementedError()
        # TODO: register url within "The DB" after it was added
        self.register_url_in_db(url, filename)

    def register_url_in_db(self, url, filename):
        # might need to go outside -- since has nothing to do with self


def crawl_openfmri():
    # TODO: get to 'incoming branch'
    crawl_url("https://openfmri.org/datasets",
                 [# for crawling for datasets
                  (a_href_match("(?P<url>.*/dataset/(?P<dataset>ds[0-9]*))$")),
                   initiate_handle(directory="openfmri/%{dataset}s",
                                   uri="%{url}s",
                                   flavor="openfmri"))])


def crawl_openfmri_dataset(directory):
    annexificator = Annexificator(options=["-c", "annex.largefiles='exclude=*.txt'"])
    # TODO: url = get_crawl_config(directory)
    # TODO: cd directory
    # TODO: get to 'incoming branch'
    crawl_url(
        url,
        # mixing hits by url's and then xpath -- might be real tricky
        [ (a_href_match(".*release_history.txt"), AnnexContent(filename="changelog.txt")),
          # (a_href_match(...) && not a_href_match(...)
          (a_href_match("ds.*_raw.tgz"), AnnexContent(content_filename_request=False)),
          (a_href_match(".*dataset/ds[0-9]*$",
                        # extracted xpaths relevant to the url should be passed into the action
                        xpaths="TODO"), ExtractOpenfMRIDatasetMeta("README.txt")),
          (xpath_match("TODO"), AnnexContent(filename="license.txt")),
          # ad-hoc way to state some action to be performed for anything which matched any of prev rules
          (any_matched(), DontHaveAGoodExampleYet())
          # How to implement above without causing duplication... probably need to memo/cache all prev
          # hits
          ],
         # A simple beast which would add files to annex/git and commit the change(s)
         # at the end or along the way
        annexificator
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
                annexificator
                )])
    # in principle could may be implemented in the same fashion as crawl_url where for each
    # file it would spit out


# TODO: figshare
# TODO: pure S3
# TODO: ratholeradio
class GenerateRatholeRadioCue(object):
    def __init__(self, filename):
        self.filename = filename
    def __call__(self, el, tags):

def crawl_ratholeradio():
    annexificator = Annexificator(options=["-c", "annex.largefiles='exclude=*.cue and exclude=*.txt'"],
                                  mode='relaxed')
    # TODO: url = get_crawl_config(directory)
    # TODO: cd directory
    crawl_url('http://ratholeradio.org',
              [
                  (a_href_match('http://ratholeradio\.org/.*/ep(?P<episode>[0-9]*)/'),
                   recurse_crawl(url="%{url}s")),
                  (page_match('http://ratholeradio\.org/(?P<year>[0-9]*)/(?P<month>[0-9]*)/ep(?P<episode>[0-9]*)/')
                   && a_href_match('', xpaths='TODO'),
                   [AnnexContent(filename="%{episode}003d-TODO.ogg"),
                    GenerateRatholeRadioCue(filename="%{episode}003d-TODO.cue"),
                    # Ha -- here to assign the tags we need to bother above files!
                    # and we seems to not allow that easily
                    AssignAnnexTags(files="%{episode}003d-TODO.*",
                                    year="%(year)s",
                                    month="%(month)s")])
              ])