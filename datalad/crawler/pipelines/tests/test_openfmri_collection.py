# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
from glob import glob
from os.path import join as opj, exists

from ...pipeline import run_pipeline, FinishPipeline

from ...nodes.annex import Annexificator, initiate_dataset

from ....support.stats import ActivityStats
from ....support.gitrepo import GitRepo

from ....utils import chpwd
from ....tests.utils import with_tree
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import assert_in, assert_not_in
from ....tests.utils import skip_if_no_module
from ....tests.utils import with_tempfile
from ....tests.utils import serve_path_via_http
from ....tests.utils import skip_if_no_network
from ....tests.utils import use_cassette
from ....tests.utils import ok_file_has_content
from ....tests.utils import ok_file_under_git
from ....distribution.dataset import Dataset
from ....distribution.dataset import Dataset
from ....consts import CRAWLER_META_CONFIG_PATH

from datalad.api import crawl
from ..openfmri import superdataset_pipeline as ofcpipeline

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')

# if we decide to emulate change (e.g. new dataset added)
_PLUG_HERE = '<!-- PLUG HERE -->'


@with_tree(tree={
    'index.html': """<html><body>
                        <a href="/dataset/ds000001/">ds001</a>
                        <a href="/dataset/ds000002/">ds002</a>
                        %s
                      </body></html>""" % _PLUG_HERE,
    },
)
@serve_path_via_http
@with_tempfile
def test_openfmri_superdataset_pipeline1(ind, topurl, outd):

    list(initiate_dataset(
        template="openfmri",
        template_func="superdataset_pipeline",
        template_kwargs={'url': topurl},
        path=outd,
    )())

    with chpwd(outd):
        crawl()
        #pipeline = ofcpipeline(url=topurl)
        #out = run_pipeline(pipeline)
    #eq_(out, [{'datalad_stats': ActivityStats()}])

    # TODO: replace below command with the one listing subdatasets
    subdatasets = ['ds000001', 'ds000002']
    eq_(Dataset(outd).subdatasets(fulfilled=True, result_xfm='relpaths'),
        subdatasets)

    # Check that crawling configuration was created for every one of those
    for sub in subdatasets:
        repo = GitRepo(opj(outd, sub))
        assert(not repo.dirty)
        assert(exists(opj(repo.path, CRAWLER_META_CONFIG_PATH)))

    # TODO: check that configuration for the crawler is up to the standard
    # Ideally should also crawl some fake datasets I guess
