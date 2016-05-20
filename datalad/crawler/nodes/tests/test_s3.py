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
from ....utils import rmtree

from ....tests.utils import eq_
from ....tests.utils import assert_not_equal
from ....tests.utils import assert_in, assert_not_in
from ....tests.utils import skip_if_no_network
from ....tests.utils import use_cassette
from ....tests.utils import externals_use_cassette
from ....tests.utils import with_tempfile


def _annex(path):
    annex = Annexificator(path, special_remotes=[DATALAD_SPECIAL_REMOTE])

    url = 's3://datalad-test0-versioned'
    providers = get_test_providers(url)  # to skip if no credentials
    # start with a fresh bucket each time so we could reuse the same vcr tapes work
    providers.get_provider(url).get_downloader(url).reset()
    return annex

target_version = '0.0.20151107'


@skip_if_no_network
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
    eq_(out, [{'datalad_stats': ActivityStats(skipped=17)}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats(skipped=17))


@skip_if_no_network
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
    eq_(out, [{'datalad_stats': ActivityStats(skipped=17)}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats(skipped=17))  # Really nothing was done


@skip_if_no_network
@use_cassette('test_crawl_s3_commit_versions_one_at_a_time')
@with_tempfile
def test_crawl_s3_commit_versions_one_at_a_time(path):
    annex = _annex(path)

    # Fancier setup so we could do any of desired actions within a single sweep
    pipeline = [
        crawl_s3('datalad-test0-versioned', strategy='commit-versions', repo=annex.repo, ncommits=1),
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
            assert_not_in("There is already a tag %s" % target_version, cml.out)
    # things are committed and thus stats are empty
    eq_(out, [{'datalad_stats': ActivityStats()}])
    total_stats_all = total_stats = out[0]['datalad_stats'].get_total()
    eq_(total_stats,
        # Deletions come as 'files' as well atm
        ActivityStats(files=3, downloaded=3, urls=3, add_annex=3, downloaded_size=24, versions=[target_version]))

    # and there should be 7 more, every time changing the total stats
    for t in range(1, 8):
        with externals_use_cassette('test_crawl_s3-pipeline1'):
            with swallow_logs() as cml:
                out = run_pipeline(pipeline)
                assert_in("There is already a tag %s" % target_version, cml.out)
        total_stats_ = out[0]['datalad_stats'].get_total()
        assert_not_equal(total_stats, total_stats_)
        total_stats = total_stats_
        total_stats_all += total_stats

    # with total stats at the end to be the same as if all at once
    total_stats_all.versions = []
    eq_(total_stats_all,
        # Deletions come as 'files' as well atm
        ActivityStats(files=17, skipped=72, overwritten=3, downloaded=14, urls=14, add_annex=14, removed=3, downloaded_size=112))


#
# Theoretically could be a test without invoking S3 where file gets later renamed into a directory
# and the other way around.  annex should handle that.  So this one serves more as integration
# test
#
@skip_if_no_network
@use_cassette('test_crawl_s3_file_to_directory')
@with_tempfile
def test_crawl_s3_file_to_directory(path):
    annex = _annex(path)

    # with auto_finalize (default), Annexificator will finalize whenever it runs into a conflict
    pipeline = [
        crawl_s3('datalad-test1-dirs-versioned', repo=annex.repo),
    #    annex
        switch('datalad_action',
               {
                   'commit': annex.finalize(tag=True),
                   'remove': annex.remove,
                   'annex':  annex,
               })
    ]
    with externals_use_cassette('test_crawl_s3_file_to_directory-pipeline1'):
        with swallow_logs() as cml:
            out = run_pipeline(pipeline)
    assert(annex.repo.dirty)
    list(annex.finalize()(out[0]))
    # things are committed and thus stats are empty
    eq_(out, [{'datalad_stats': ActivityStats()}])
    total_stats_all = total_stats = out[0]['datalad_stats'].get_total()
    eq_(total_stats,
        # Deletions come as 'files' as well atm
        ActivityStats(files=3, downloaded=3, overwritten=2, urls=3, add_annex=3, downloaded_size=12, versions=['0.0.20160303']))
