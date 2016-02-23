# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# now with some recursive structure of directories

from ..s3 import crawl_s3
from ..misc import switch
from ..annex import Annexificator
from ...pipeline import run_pipeline
from ....consts import DATALAD_SPECIAL_REMOTE
from ....downloaders.tests.utils import get_test_providers
from ....support.stats import ActivityStats
from ....utils import swallow_logs

from ....tests.utils import eq_
from ....tests.utils import assert_in, assert_not_in
from ....tests.utils import SkipTest
from ....tests.utils import use_cassette
from ....tests.utils import externals_use_cassette
from ....tests.utils import with_tempfile


def _annex(path):
    annex = Annexificator(path)
    # TODO:  we need helper functions for those two and RF all copies of such code
    annex.repo.annex_initremote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'autoenable=true'])

    url = 's3://datalad-test0-versioned'
    providers = get_test_providers(url)  # to skip if no credentials
    # start with a fresh bucket each time so we could reuse the same vcr tapes work
    providers.get_provider(url).get_downloader(url).reset()
    return annex

target_version = '0.0.20151107'

@use_cassette('test_crawl_s3')
@with_tempfile
def test_crawl_s3(path):
    annex = _annex(path)
    # For now a very simple one which doesn't give a damn about files being removed
    # so we just get the "most recent existed" view of all of them without having commits
    # for previous versions but  annex  processing them thus doing all house-keeping
    # necessary
    pipeline = [
        [
            crawl_s3('datalad-test0-versioned', strategy='naive', repo=annex.repo),
            annex
        ],
        annex.finalize()
    ]

    with externals_use_cassette('test_crawl_s3-pipeline1'):
        out = run_pipeline(pipeline)
    # things are committed and thus stats are empty
    eq_(out, [{'datalad_stats': ActivityStats()}])
    total_stats = out[0]['datalad_stats'].get_total()
    eq_(set(total_stats.versions), {target_version})  # we have a bunch of them since not uniq'ing them and they are all the same
    total_stats.versions = []
    eq_(total_stats, ActivityStats(files=14, overwritten=5, downloaded=14, urls=14, add_annex=14, downloaded_size=112))

    # if we rerun -- nothing new should have been done.  I.e. it is the
    # and ATM we can reuse the same cassette
    with externals_use_cassette('test_crawl_s3-pipeline1'):
        out = run_pipeline(pipeline)
    eq_(out, [{'datalad_stats': ActivityStats()}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats())


@use_cassette('test_crawl_s3')
@with_tempfile
def test_crawl_s3_commit_versions(path):
    annex = _annex(path)

    # Fancier setup so we could do any of desired actions within a single sweep
    pipeline = [
        crawl_s3('datalad-test0-versioned', strategy='commit-versions', repo=annex.repo),
        switch('datalad_action',
               {
                   'commit': annex.finalize(tag=True),
                   'remove': annex.remove,
                   'annex':  annex,
               })
    ]

    with externals_use_cassette('test_crawl_s3-pipeline1'):
        with swallow_logs() as cml:
            out = run_pipeline(pipeline)
            assert_in("There is already a tag %s" % target_version, cml.out)
    # things are committed and thus stats are empty
    eq_(out, [{'datalad_stats': ActivityStats()}])
    total_stats = out[0]['datalad_stats'].get_total()

    eq_(set(total_stats.versions), {target_version})  # we have a bunch of them since not uniq'ing them and they are all the same
    # override for easier checking
    total_stats.versions = []
    eq_(total_stats,
        # Deletions come as 'files' as well atm
        ActivityStats(files=17, overwritten=3, downloaded=14, urls=14, add_annex=14, removed=3, downloaded_size=112))
    tags = annex.repo.repo.tags
    assert_in(target_version, tags)
    # and we actually got 7 more commits
    for t in range(1, 8):
        assert_in(target_version + "+%d" % t, tags)

    # if we rerun -- nothing new should have been done.  I.e. it is the
    # and ATM we can reuse the same cassette
    with externals_use_cassette('test_crawl_s3-pipeline1'):
        with swallow_logs() as cml:
            out = run_pipeline(pipeline)
            assert_not_in("There is already a tag %s" % target_version, cml.out)
    eq_(out, [{'datalad_stats': ActivityStats()}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats())  # Really nothing was done