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
from os.path import join as opj
from os.path import exists
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

from ....api import clean
from ....utils import chpwd
from ....utils import find_files
from ....utils import swallow_logs
from ....tests.utils import with_tree
from ....tests.utils import SkipTest
from ....tests.utils import eq_, assert_not_equal, ok_, ok_startswith
from ....tests.utils import assert_in, assert_is_generator
from ....tests.utils import skip_if_no_module
from ....tests.utils import with_tempfile
from ....tests.utils import serve_path_via_http
from ....tests.utils import skip_if_no_network
from ....tests.utils import use_cassette
from ....tests.utils import ok_file_has_content
from ....tests.utils import ok_file_under_git

from .. import openfmri
from ..openfmri import pipeline as ofpipeline

import logging
from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


#
# Some helpers
#

from ..xnat import XNATServer
from ..xnat import PROJECT_ACCESS_TYPES
from ..xnat import superdataset_pipeline
from ..xnat import pipeline
from datalad.tests.utils import skip_if_no_network

NITRC_IR = 'https://www.nitrc.org/ir'
CENTRAL_XNAT = 'https://central.xnat.org'


def check_basic_xnat_interface(url, project, subjects):
    nitrc = XNATServer(url)
    projects = nitrc.get_projects()
    # verify that we still have projects we want!

    assert_in(project, projects)
    projects_public = nitrc.get_projects(limit='public')
    import json
    print json.dumps(projects_public, indent=2)
    assert len(projects_public) < len(projects)
    assert not set(projects_public).difference(projects)
    eq_(set(projects),
        set(nitrc.get_projects(limit=PROJECT_ACCESS_TYPES)))

    subjects_ = nitrc.get_subjects(project)
    assert len(subjects_)
    experiments = nitrc.get_experiments(project, subjects[0])
    # NOTE: assumption that there is only one experiment
    files1 = nitrc.get_files(project, subjects[0], experiments.keys()[0])
    assert files1

    experiments = nitrc.get_experiments(project, subjects[1])
    files2 = nitrc.get_files(project, subjects[1], experiments.keys()[0])
    assert files2

    ok_startswith(files1[0]['uri'], '/data')
    gen = nitrc.get_all_files_for_project(project,
                                          subjects=subjects,
                                          experiments=[experiments.keys()[0]])
    assert_is_generator(gen)
    all_files = list(gen)
    if len(experiments) == 1:
        eq_(len(all_files), len(files1) + len(files2))
    else:
        # there should be more files due to multiple experiments which we didn't actually check
        assert len(all_files) > len(files1) + len(files2)


# THIS SOMEHOW CAUSES the test to not run!!! wtf? TODO
#@skip_if_no_network
@use_cassette('test_basic_xnat_interface')
def test_basic_xnat_interface():
    for url, project, subjects in [
        (NITRC_IR, 'fcon_1000', ['xnat_S00401', 'xnat_S00447']),
        (CENTRAL_XNAT, 'CENTRAL_OASIS_LONG', ['OAS2_0001', 'OAS2_0176']),
    # Should have worked, since we do have authentication setup for hcp, but
    # failed to authenticate.  need to recall what is differently done for the test
    # since it downloads just fine using download-url
    #   ('https://db.humanconnectome.org', 'HCP_Retest', ['103818', '149741']),
    ]:
        yield check_basic_xnat_interface, url, project, subjects


@skip_if_no_network
@with_tempfile(mkdir=True)
def test_smoke_pipelines(d):
    # Just to verify that we can correctly establish the pipelines
    AnnexRepo(d, create=True)
    with chpwd(d):
        with swallow_logs():
            for p in [superdataset_pipeline(NITRC_IR)]:
                print p
                ok_(len(p) > 1)


@skip_if_no_network
@with_tempfile(mkdir=True)
def test_nitrc_superpipeline(outd):
    with chpwd(outd):
        pipeline = superdataset_pipeline(NITRC_IR)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)
    # TODO: actual tests on what stuff was crawled
test_nitrc_superpipeline.tags = ['integration']


@skip_if_no_network
@with_tempfile
def test_nitrc_pipeline(outd):
    from datalad.distribution.dataset import Dataset
    ds = Dataset(outd).create()
    with chpwd(outd):
        out = run_pipeline(
            pipeline(NITRC_IR, dataset='fcon_1000', subjects=['xnat_S00401'])
        )
    eq_(len(out), 1)
test_nitrc_superpipeline.tags = ['integration']
