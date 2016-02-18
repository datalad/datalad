# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
# now with some recursive structure of directories

from glob import glob
from os.path import exists, join as opj
from datalad.tests.utils import eq_, ok_
from datalad.tests.utils import serve_path_via_http, with_tree
from ..crawl_url import crawl_url
from ..misc import skip_if
from ..crawl_url import parse_checksums
from ..matches import a_href_match
from ....tests.utils import assert_equal
from ....tests.utils import assert_false
from ....tests.utils import SkipTest
from ....tests.utils import use_cassette
from ....utils import updated
from ....utils import chpwd
from ....downloaders.tests.utils import get_test_providers
from ....tests.utils import with_tempfile
from ..annex import Annexificator
from ...pipeline import run_pipeline
from ....consts import DATALAD_SPECIAL_REMOTE
from ....support.stats import ActivityStats

from ..s3 import crawl_s3

# @use_cassette('fixtures/vcr_cassettes/test_crawl_s3')
@with_tempfile
def test_crawl_s3(path):
    #crawler = crawl_s3('datalad-test0-versioned')
    #print '\n'.join(map(str, list(crawler({}))))
    annex = Annexificator(path)
    # TODO:  we need helper functions for those two and RF all copies of such code
    annex.repo.annex_initremote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'autoenable=true'])

    """
    For now we are using/testing only the basic simplest pipeline which doesn't care
    about multiple versions etc.  But we should think about how to possibly make it
    split/iterate over "versions" within the bucket, e.g. possible solutions:
    [
        crawl_s3('datalad-test0-versioned', mark_command='datalad-command'),
        [
            skip_if({'datalad-command': 'commit'}),
            annex
        ],
        [
            skip_if({'datalad-command': 'commit'}, negate=True),
            annex.finalize(tag=True),
        ]
    ]

    or may be to come up with a helper to `switch` between pipelines

    [
        crawl_s3('datalad-test0-versioned', mark_command='datalad-command'),
        switch('datalad-command',
           {
           'commit': annex.finalize(tag=True),
           'remove': annex.remove,
           },
           default=annex  # for no match
        )
    ]

    and also to rely on crawl_s3 spitting out 'commit' command at the end if still needed to be
    committed
    """
    get_test_providers('s3://datalad-test0-versioned')  # to skip if no credentials

    # But for now a very simple one which doesn't give a damn about files being removed
    # so we just get the "most recent existed" view of all of them without having commits
    # for previous versions but  annex  processing them thus doing all house-keeping
    # necessary
    pipeline = [[crawl_s3('datalad-test0-versioned', strategy='naive'), annex], annex.finalize()]

    out = run_pipeline(pipeline)
    eq_(out, [{'datalad_stats': ActivityStats(files=14, overwritten=5, downloaded=14, urls=14, add_annex=14, downloaded_size=112)}])

    # if we rerun -- nothing new should have been done.  I.e. it is the
    out = run_pipeline(pipeline)
    raise SkipTest("TODO:  should track prev version and next rerun should be nothing new")
    eq_(out, [{'datalad_stats': ActivityStats()}])
    # TODO: could be boto f.ck ups (e.g. build 1000 for python3) due to recent rename of aws -> s3?
    # but they don't reproduce locally