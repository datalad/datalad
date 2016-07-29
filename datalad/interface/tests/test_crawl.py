# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for crawl command

"""

__docformat__ = 'restructuredtext'

from mock import patch
from mock import call
from ...api import crawl

from ...tests.utils import assert_cwd_unchanged
from ...tests.utils import assert_equal
from ...tests.utils import with_tempfile
from ...support.stats import ActivityStats
from ...utils import chpwd
from ...utils import find_files


@assert_cwd_unchanged(ok_to_chdir=True)
@patch('datalad.utils.chpwd')
@patch('datalad.crawler.pipeline.load_pipeline_from_config', return_value=['pipeline'])
@patch('datalad.crawler.pipeline.run_pipeline', return_value=None)
# Note that order of patched things as args is reverse for some reason :-/
def test_crawl_api_chdir(run_pipeline_, load_pipeline_from_config_, chpwd_):
    output, stats = crawl('some_path_not_checked', chdir='somedir')
    assert_equal(stats, ActivityStats(datasets_crawled=1))  # nothing was done but we got it
    assert_equal(output, None)

    chpwd_.assert_called_with('somedir')
    load_pipeline_from_config_.assert_called_with('some_path_not_checked')
    run_pipeline_.assert_called_with(['pipeline'], stats=ActivityStats(datasets_crawled=1))


# XXX we could also mock run_pipeline to adjust stats etc more so we
#def run_pipeline_se(output, stats):
#    stats.add_git += 1
#    return output, stats


@patch('datalad.utils.chpwd')
@patch('datalad.crawler.pipeline.get_repo_pipeline_script_path', return_value='script_path')
@patch('datalad.crawler.pipeline.load_pipeline_from_config', return_value=['pipeline'])
@patch('datalad.crawler.pipeline.run_pipeline', return_value=None)
@patch('datalad.distribution.dataset.Dataset.get_subdatasets',  # return_value=['path1', 'path2'])
    side_effect=[
        ['path1', 'path2'],
        ['path1_1'],  # sub-dataset of the first sub-dataset
        [],  # so it would get crawled and have no further sub-datasets
        [],  # no sub-datasets in path2
    ]
)
# Note that order of patched things as args is reverse for some reason :-/
@with_tempfile(mkdir=True)
def test_crawl_api_recursive(get_subdatasets_, run_pipeline_, load_pipeline_from_config_, get_repo_pipeline_script_path_,
                             chpwd_, tdir):
    with chpwd(tdir):
        output, stats = crawl(recursive=True)
    assert_equal(output, [None]*4)  # for now output is just a list of outputs
    assert_equal(stats, ActivityStats(datasets_crawled=4))  # nothing was done but we got it crawled
    chpwd_.assert_has_calls(
        [
            call(None),
            call('path1'),
            call('path1_1'),
            call('path2'),
        ],
        any_order=True
    )
    assert_equal(list(find_files('.*', tdir, exclude_vcs=False)), [])  # no files were generated