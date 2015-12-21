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
from ...api import crawl

from ...tests.utils import assert_cwd_unchanged

@assert_cwd_unchanged(ok_to_chdir=True)
@patch('datalad.utils.chpwd')
@patch('datalad.crawler.pipeline.load_pipeline_from_config', return_value=['pipeline'])
@patch('datalad.crawler.pipeline.run_pipeline')
# Note that order of patched things as args is reverse for some reason :-/
def test_crawl_api_chdir(run_pipeline_, load_pipeline_from_config_, chpwd_):
    crawl('some_path_not_checked', chdir='somedir')

    chpwd_.assert_called_with('somedir')
    load_pipeline_from_config_.assert_called_with('some_path_not_checked')
    run_pipeline_.assert_called_with(['pipeline'])
