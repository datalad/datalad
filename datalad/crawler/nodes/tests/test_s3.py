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
from ....tests.utils import assert_in
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

    get_test_providers('s3://datalad-test0-versioned')  # to skip if no credentials
    return annex

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
            crawl_s3('datalad-test0-versioned', strategy='naive'),
            annex
        ],
        annex.finalize()
    ]

    with externals_use_cassette('test_crawl_s3-pipeline1'):
        out = run_pipeline(pipeline)
    # things are committed and thus stats are empty
    eq_(out, [{'datalad_stats': ActivityStats()}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats(files=14, overwritten=5, downloaded=14, urls=14, add_annex=14, downloaded_size=112))

    # if we rerun -- nothing new should have been done.  I.e. it is the
    # and ATM we can reuse the same cassette
    with externals_use_cassette('test_crawl_s3-pipeline1'):
        out = run_pipeline(pipeline)
    raise SkipTest("TODO:  should track prev version and next rerun should be nothing new")
    eq_(out, [{'datalad_stats': ActivityStats()}])
    eq_(out[0]['datalad_stats'].get_total(), ActivityStats())
    # TODO: could be boto f.ck ups (e.g. build 1000 for python3) due to recent rename of aws -> s3?
    # but they don't reproduce locally


@use_cassette('test_crawl_s3')
@with_tempfile
def test_crawl_s3_commit_versions(path):
    target_version = '0.0.20151107'
    annex = _annex(path)

    # Fancier setup so we could do any of desired actions within a single sweep
    pipeline = [
        crawl_s3('datalad-test0-versioned', strategy='commit-versions'),
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
            raise SkipTest("TODO:  should track prev version and next rerun should be nothing new")
            assert_not_in("There is already a tag %s" % target_version, cml.out)
    eq_(out, [{'datalad_stats': ActivityStats()}])
