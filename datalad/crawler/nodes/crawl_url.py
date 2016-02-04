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

import re
from distutils.version import LooseVersion

import os
from os import unlink
from os.path import splitext, dirname, basename, curdir
from os.path import lexists
from os.path import join as opj

from six import iteritems
from ...utils import updated
from ...utils import find_files
from ...dochelpers import exc_str
from ...support.versions import get_versions
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

"""
Versioned files examples

- version might be in the middle of the filename

README.txt                     ds030_R1.0.0_10631-10704.tgz@  ds030_R1.0.0_11104-11143.tgz@  ds030_R1.0.0_50067-60001.tgz@  ds030_R1.0.0_70001-70033.tgz@
ds030_R1.0.0_10150-10274.tgz@  ds030_R1.0.0_10707-10844.tgz@  ds030_R1.0.0_11149-50016.tgz@  ds030_R1.0.0_60005-60021.tgz@  ds030_R1.0.0_70034-70057.tgz@
ds030_R1.0.0_10280-10365.tgz@  ds030_R1.0.0_10855-10958.tgz@  ds030_R1.0.0_50020-50036.tgz@  ds030_R1.0.0_60022-60048.tgz@  ds030_R1.0.0_70058-70076.tgz@
ds030_R1.0.0_10370-10506.tgz@  ds030_R1.0.0_10963-11052.tgz@  ds030_R1.0.0_50038-50053.tgz@  ds030_R1.0.0_60049-60068.tgz@  ds030_R1.0.0_70077-70086.tgz@
ds030_R1.0.0_10517-10629.tgz@  ds030_R1.0.0_11059-11098.tgz@  ds030_R1.0.0_50054-50066.tgz@  ds030_R1.0.0_60070-60089.tgz@  ds030_R1.0.0_metadata_and_derivatives.tgz@

- version might be duplicated

http://ftp.ncbi.nlm.nih.gov/1000genomes/ftp/release/20110521/ALL.chr22.phase1_release_v3.20101123.snps_indels_svs.genotypes.vcf.gz
http://ftp.ncbi.nlm.nih.gov/1000genomes/ftp/release/20130502/ALL.chr22.phase3_shapeit2_mvncall_integrated_v5a.20130502.genotypes.vcf.gz

so there is a directory with that version and then version in the filename.  I guess we should operate in this case at the
level of directories and then with additional rename command strip suffix in the filename
"""

def __prune_to_the_next_version(
    # ATM wouldn't deal with multiple notations for versioning present in the same tree TODO?
    # ATM -- non deep -- just leading  TODO?
    regex,
    topdir=curdir,
    dirs=True,  # either match directory names
    name='version',      # optional,  to identify "versionier"
    # ha -- we could store status in prev commit msg may be? then no need for any additional files !
    store_version_info='commit',  # other methods -- some kind of db??
    unversioned='oldest',  # 'latest' - consider to be the latest one, 'oldest' the oldest, 'mtime' -judge by mtime, 'fail'
    mtimes='ignore',  # check -- fail if revisioning says otherwise, None/'ignore',
    rename=True,  # rename last version into the one without version suffix
    flag_to_redo='loop'  # "flag" to redo the loop if newer versions are yet to be processed
    ):
    """Handle versioned files in the current tree to process only "next" revision

    """

    def _prune_to_the_next_version(data):

        # TODO: RF this dark magic
        stats = data['datalad_stats']
        if not hasattr(stats, 'flags'):
            stats.flags = object()

        if mtimes != 'ignore':
            raise NotImplementedError(mtimes)

        versions = get_versions(
                find_files('.', dirs=dirs, topdir=topdir),
                regex=regex,
                unversioned=unversioned)

        # gave . regex now
        # # since we gave only regex matching ones to get_versions, there will be no None
        # # versioned
        # # check if for each one of them there is no unversioned one or handle it
        # for fpath in vfpaths:
        #     if lexists(fpath):
        #         if unversioned == 'fail':
        #             raise RuntimeError(
        #                 "There is an unversioned file %s whenever also following "
        #                 "versions were found: %s" % (fpath, vfpaths[fpath]))
        #         else:
        #             raise NotImplemented(unversioned)

        # For now simple implementation which assumes no per-file separate versioning,
        # necessity to overlay next versions on top of previous for other files, etc
        # TODO: handle more complex scenarios

        # theoretically shouldn't be necessary and code below should be general enough
        # to work in this case TODO: remove
        versions_keys = versions.keys()
        if len(versions) <= 1 or (len(versions) == 2 and versions_keys[0] == [None]):
            # no versioned files -- or just 1 version of top of None
            yield data
            return

        # # sort all the versions and prepend with 'None'
        # all_versions = [None] + map(str, sorted(map(LooseVersion, all_versions)))

        # get last processed version
        prev_version = None  # TODO

        # Get next version
        prev_version_index = versions_keys.index(prev_version)
        if prev_version_index < len(versions):
            current_version_index = prev_version_index + 1
        else:
            assert(prev_version is not None)  # since we quit early above, shouldn't happen
            lgr.debug("No new versions found from previous %s" % prev_version)
            # How do we exit all the pipelining!!!???
            #  If this was a 'refresh' run which didn't fetch anything new,
            #  and we did get here, we should re-process prev version but signal
            #  that no additional looping is needed
            current_version_index = prev_version_index

        # Set the flag so we loop or not -- depends if new versions available
        setattr(stats.flags, flag_to_redo, current_version_index + 1 < len(versions))
        current_version = versions_keys[current_version_index]

        # Go through all versioned files and remove all but current one
        # Since implementation is limited ATM, raise exception if there is no current
        # version for some file
        removed_other_versions = 0
        for version, fpaths in iteritems(versions):
            if version is None:
                # Nothing to be done AFAIK
                continue
            for fpath, vfpath in iteritems(fpaths):
                if version != current_version:
                    lgr.debug("Removing %s since not of current version %s" % (vfpath, current_version))
                    unlink(vfpath)
                    removed_other_versions += 1
                elif rename:
                    lgr.debug("Renaming %s into %s" % (vfpath, fpath))
                    os.rename(vfpath, fpath)

        # TODO: something about stats for e.g. removed_other_versions
        yield updated(data, {'version': current_version})

    return _prune_to_the_next_version
