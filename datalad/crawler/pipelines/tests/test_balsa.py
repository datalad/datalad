# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines
from ..balsa import pipeline as ofpipeline, superdataset_pipeline
import os
from glob import glob
from os.path import join as opj
from mock import patch

from ...nodes.crawl_url import crawl_url
from ...nodes.matches import *
from ...pipeline import run_pipeline, FinishPipeline

from ...nodes.misc import Sink, assign, range_node, interrupt_if
from ...nodes.annex import Annexificator, initiate_dataset
from ...pipeline import load_pipeline_from_module

from ....support.stats import ActivityStats
from ....support.gitrepo import GitRepo
from ....support.annexrepo import AnnexRepo

from ....utils import chpwd
from ....utils import find_files
from ....utils import swallow_logs
from ....tests.utils import with_tree
from ....tests.utils import SkipTest
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import assert_in, assert_not_in
from ....tests.utils import skip_if_no_module
from ....tests.utils import with_tempfile
from ....tests.utils import serve_path_via_http
from ....tests.utils import skip_if_no_network
from ....tests.utils import use_cassette
from ....tests.utils import ok_file_has_content
from ....tests.utils import ok_file_under_git

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


def test_smoke_pipelines():
    yield _test_smoke_pipelines, superdataset_pipeline, []


_PLUG_HERE = '<!-- PLUG HERE -->'


@with_tree(tree={

    'study': {
        'show': {
            'WG33': {
                'index.html': """<html><body>
                                    <a href="/study/download/WG33.zip">thetarball.zip</a>
                                    <a href="/file/show/JX5V">file1.nii</a>
                                    <a href="/file/show/R1BX">dir1 / file2.nii</a>
                                    %s
                                  </body></html>""" % _PLUG_HERE,
            },
        },
        'download': {
            'WG33.zip': {
                'file1.nii': "content of file1.nii",
                'dir1': {
                    'file2.nii': "content of file2.nii",
                }
            }
        }
    },

    'file': {
        'show': {
                'JX5V': "content of file1.nii",
                'R1BX': "content of file2.nii",
            },
        },
    },
    archives_leading_dir=False
)
@serve_path_via_http
@with_tempfile
@with_tempfile
def test_balsa_pipeline(ind, topurl, outd, clonedir):
  #  import pdb; pdb.set_trace()
    list(initiate_dataset(
        template="balsa",
        dataset_name='dataladtest-WG33',
        path=outd,
        data_fields=['dataset_id'])({'dataset_id': 'WG33'}))

    with chpwd(outd):
        pipeline = ofpipeline('WG33', url=topurl)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    repo = AnnexRepo(outd, create=False)
    branches = {'master', 'incoming', 'incoming-processed', 'git-annex'}
    eq_(set(repo.get_branches()), branches)
    # assert_not_equal(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # assert_not_equal(repo.get_hexsha('incoming'), repo.get_hexsha('incoming-processed'))

    #
    # commits = {b: list(repo.get_branch_commits(b)) for b in branches}
    # commits_hexsha = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    # commits_l = {b: list(repo.get_branch_commits(b, limit='left-only')) for b in branches}
    # eq_(len(commits['incoming']), 2)
    # eq_(len(commits_l['incoming']), 2)
    # eq_(len(commits['incoming-processed']), 4)
    # eq_(len(commits_l['incoming-processed']), 3)  # because original merge has only 1 parent - incoming
    # eq_(len(commits['master']), 7)  # all commits out there -- init + 2*(incoming, processed, merge)
    # eq_(len(commits_l['master']), 3)

