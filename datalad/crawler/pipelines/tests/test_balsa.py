# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import exists
from ....utils import chpwd
from ....tests.utils import assert_true, assert_raises
from ....tests.utils import with_tempfile, skip_if_no_network, use_cassette
from datalad.crawler.pipelines.tests.utils import _test_smoke_pipelines
from datalad.crawler.pipelines.balsa import *
from datalad.crawler.pipeline import run_pipeline

import logging
from logging import getLogger
lgr = getLogger('datalad.crawl.tests')

from ..balsa import pipeline


def test_smoke_pipelines():
    yield _test_smoke_pipelines, pipeline, 'bogus'
