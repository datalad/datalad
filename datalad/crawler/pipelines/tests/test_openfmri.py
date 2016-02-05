# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from glob import glob
from os.path import join as opj

from ...nodes.crawl_url import crawl_url
from ...nodes.matches import *
from ...pipeline import run_pipeline, FinishPipeline

from ...nodes.misc import Sink, assign, range_node, interrupt_if
from ...nodes.annex import Annexificator, initiate_handle
from ...pipeline import load_pipeline_from_script

from ....support.stats import ActivityStats
from ....support.annexrepo import AnnexRepo

from ....utils import chpwd
from ....utils import find_files
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

from ..openfmri import pipeline as ofpipeline

from logging import getLogger
lgr = getLogger('datalad.crawl.tests')


@skip_if_no_network
@use_cassette('fixtures/vcr_cassettes/openfmri.yaml')
def __test_basic_openfmri_top_pipeline():
    skip_if_no_module('scrapy')  # e.g. not present under Python3
    sink1 = Sink()
    sink2 = Sink()
    sink_licenses = Sink()
    pipeline = [
        crawl_url("https://openfmri.org/data-sets"),
        a_href_match(".*/dataset/(?P<dataset_dir>ds0*(?P<dataset>[1-9][0-9]*))$"),
        # if we wanted we could instruct to crawl inside
        [
            crawl_url(),
            [# and collect all URLs under "AWS Link"
                css_match('.field-name-field-aws-link a',
                           xpaths={'url': '@href',
                                   'url_text': 'text()'}),
                sink2
             ],
            [# and license information
                css_match('.field-name-field-license a',
                           xpaths={'url': '@href',
                                   'url_text': 'text()'}),
                sink_licenses
            ],
        ],
        sink1
    ]

    run_pipeline(pipeline)
    # we should have collected all the URLs to the datasets
    urls = [e['url'] for e in sink1.data]
    ok_(len(urls) > 20)  # there should be at least 20 listed there
    ok_(all([url.startswith('https://openfmri.org/dataset/ds00') for url in urls]))
    # got our dataset_dir entries as well
    ok_(all([e['dataset_dir'].startswith('ds0') for e in sink1.data]))

    # and sink2 should collect everything downloadable from under AWS Link section
    # test that we got all needed tags etc propagated properly!
    all_aws_entries = sink2.get_values('dataset', 'url_text', 'url')
    ok_(len(all_aws_entries) > len(urls))  # that we have at least as many ;-)
    #print('\n'.join(map(str, all_aws_entries)))
    all_licenses = sink_licenses.get_values('dataset', 'url_text', 'url')
    eq_(len(all_licenses), len(urls))
    #print('\n'.join(map(str, all_licenses)))


@skip_if_no_network
@use_cassette('fixtures/vcr_cassettes/openfmri-1.yaml')
@with_tempfile(mkdir=True)
def __test_basic_openfmri_dataset_pipeline_with_annex(path):
    skip_if_no_module('scrapy')  # e.g. not present under Python3
    dataset_index = 1
    dataset_name = 'ds%06d' % dataset_index
    dataset_url = 'https://openfmri.org/dataset/' + dataset_name
    # needs to be a non-existing directory
    handle_path = opj(path, dataset_name)
    # we need to pre-initiate handle
    list(initiate_handle('openfmri', dataset_index, path=handle_path)())

    annex = Annexificator(
        handle_path,
        create=False,  # must be already initialized etc
        options=["-c", "annex.largefiles=exclude=*.txt and exclude=README"])

    pipeline = [
        crawl_url(dataset_url),
        [  # changelog
               a_href_match(".*release_history.txt"),  # , limit=1
               assign({'filename': 'changelog.txt'}),
               annex,
        ],
        [  # and collect all URLs under "AWS Link"
            css_match('.field-name-field-aws-link a',
                      xpaths={'url': '@href',
                              'url_text': 'text()'}),
            # TODO:  here we need to provide means to rename some files
            # but first those names need to be extracted... pretty much
            # we need conditional sub-pipelines which do yield (or return?)
            # some result back to the main flow, e.g.
            # get_url_filename,
            # [ {'yield_result': True; },
            #   field_matches_re(filename='.*release_history.*'),
            #   assign({'filename': 'license:txt'}) ]
            annex,
        ],
        [  # and license information
            css_match('.field-name-field-license a',
                      xpaths={'url': '@href',
                              'url_text': 'text()'}),
            assign({'filename': 'license.txt'}),
            annex,
        ],
    ]

    run_pipeline(pipeline)

_PLUG_HERE = '<!-- PLUG HERE -->'
@with_tree(tree={
    'ds666': {
        'index.html': """<html><body>
                            <a href="release_history.txt">Release History</a>
                            <a href="ds666_R1.0.0.tar.gz">Raw data on AWS version 1</a>
                            <a href="ds666_R1.0.1.tar.gz">Raw data on AWS version 2</a>
                            <a href="ds666-beh_R1.0.1.tar.gz">Beh data on AWS version 2</a>
                            %s
                          </body></html>""" % _PLUG_HERE,
        'release_history.txt': '1.0.1 fixed\n1.0.0 whatever',
        'ds666_R1.0.0.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 1.0.0"}}}},
        'ds666_R1.0.1.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 1.0.1"}}}},
        'ds666-beh_R1.0.1.tar.gz': {'beh.tar.gz': {'ds666': {'sub-1': {'beh': {'responses.tsv': "1"}}}}},
        'ds666_R2.0.0.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 2.0.0"}}}},
    }},
    archives_leading_dir=False
)
@serve_path_via_http
@with_tempfile
def test_openfmri_pipeline1(ind, topurl, outd):

    list(initiate_handle(
        template="openfmri",
        handle_name='dataladtest-ds666',
        path=outd,
        data_fields=['dataset'])({'dataset': 'ds666'}))

    with chpwd(outd):
        pipeline = ofpipeline('ds666', versioned_urls=False, topurl=topurl)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    repo = AnnexRepo(outd, create=False)  # to be used in the checks
    # Inspect the tree -- that we have all the branches
    branches = {'master', 'incoming', 'incoming-processed', 'git-annex'}
    eq_(set(repo.git_get_branches()), branches)
    # We do not have custom changes in master yet, so it just follows incoming-processed atm
    # eq_(repo.git_get_hexsha('master'), repo.git_get_hexsha('incoming-processed'))
    # Since we did initiate_handle -- now we have separate master!
    assert_not_equal(repo.git_get_hexsha('master'), repo.git_get_hexsha('incoming-processed'))
    # and that one is different from incoming
    assert_not_equal(repo.git_get_hexsha('incoming'), repo.git_get_hexsha('incoming-processed'))

    # TODO: tags for the versions
    # actually the tree should look quite neat with 1.0.0 tag having 1 parent in incoming
    # 1.0.1 having 1.0.0 and the 2nd commit in incoming as parents

    commits = {b: list(repo.git_get_branch_commits(b)) for b in branches}
    commits_hexsha = {b: list(repo.git_get_branch_commits(b, value='hexsha')) for b in branches}
    commits_l = {b: list(repo.git_get_branch_commits(b, limit='left-only')) for b in branches}
    eq_(len(commits['incoming']), 2)
    eq_(len(commits_l['incoming']), 2)
    eq_(len(commits['incoming-processed']), 4)
    eq_(len(commits_l['incoming-processed']), 3)  # because original merge has only 1 parent - incoming
    eq_(len(commits['master']), 8)  # all commits out there
    eq_(len(commits_l['master']), 4)

    def hexsha(l):
        return l.__class__(x.hexsha for x in l)

    # Verify that we have desired tree of merges
    eq_(hexsha(commits_l['incoming-processed'][0].parents), (commits_l['incoming-processed'][1].hexsha,
                                                             commits_l['incoming'][0].hexsha))
    eq_(hexsha(commits_l['incoming-processed'][1].parents), (commits_l['incoming'][1].hexsha,))

    eq_(hexsha(commits_l['master'][0].parents), (commits_l['master'][1].hexsha,
                                                 commits_l['incoming-processed'][0].hexsha))

    eq_(hexsha(commits_l['master'][1].parents), (commits_l['master'][2].hexsha,
                                                 commits_l['incoming-processed'][1].hexsha))

    with chpwd(outd):
        eq_(set(glob('*')), {'changelog.txt', 'README.txt', 'sub-1'})
        all_files = sorted(find_files('.'))

    ok_file_has_content(opj(outd, 'sub-1', 'anat', 'sub-1_T1w.dat'), "mighty load 1.0.1")
    ok_file_under_git(opj(outd, 'changelog.txt'), annexed=False)
    ok_file_under_git(opj(outd, 'README.txt'), annexed=False)
    ok_file_under_git(opj(outd, 'sub-1', 'anat', 'sub-1_T1w.dat'), annexed=True)

    target_files = {'./.datalad/config.ttl', './.datalad/crawl/crawl.cfg', './.datalad/crawl/versions/incoming.json', './.datalad/datalad.ttl', './README.txt', './changelog.txt',
            './sub-1/anat/sub-1_T1w.dat', './sub-1/beh/responses.tsv'}
    eq_(set(all_files), target_files)

    # check that -beh was committed in 2nd commit in incoming, not the first one
    assert_not_in('ds666-beh_R1.0.1.tar.gz', repo.git_get_files(commits_l['incoming'][-1]))
    assert_in('ds666-beh_R1.0.1.tar.gz', repo.git_get_files(commits_l['incoming'][0]))

    # TODO: fix up commit messages in incoming

    # rerun pipeline -- make sure we are on the same in all branches!
    with chpwd(outd):
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    commits_hexsha_ = {b: list(repo.git_get_branch_commits(b, value='hexsha')) for b in branches}
    eq_(commits_hexsha, commits_hexsha_)  # i.e. nothing new
    # actually we do manage to download 1 since it is committed directly to git
    # eq_(out[0]['datalad_stats'], ActivityStats())
    # Nothing was committed so stats leaked all the way up
    eq_(out[0]['datalad_stats'], ActivityStats(files=4, overwritten=1, skipped=3, downloaded=1, add_git=1, urls=4, downloaded_size=26))
    eq_(out[0]['datalad_stats'], out[0]['datalad_stats'].get_total())

    # add new revision, rerun pipeline and check that stuff was processed/added correctly
    with open(opj(ind, 'ds666', 'index.html')) as f:
        old_index = f.read()
    with open(opj(ind, 'ds666', 'index.html'), 'w') as f:
        f.write(old_index.replace(_PLUG_HERE, '<a href="ds666_R2.0.0.tar.gz">Raw data on AWS version 2.0.0</a>'))

    # rerun pipeline when new content is available
    with chpwd(outd):
        out = run_pipeline(pipeline)
        all_files_updated = sorted(find_files('.'))
    eq_(len(out), 1)
    assert_not_equal(out[0]['datalad_stats'].get_total(), ActivityStats())
    # there is no overlays ATM, so behav would be gone since no 2.0.0 for it!
    target_files.remove('./sub-1/beh/responses.tsv')
    eq_(set(all_files_updated), target_files)

    # new instance so it re-reads git stuff etc
    # repo = AnnexRepo(outd, create=False)  # to be used in the checks
    commits_ = {b: list(repo.git_get_branch_commits(b)) for b in branches}
    commits_hexsha_ = {b: list(repo.git_get_branch_commits(b, value='hexsha')) for b in branches}
    commits_l_ = {b: list(repo.git_get_branch_commits(b, limit='left-only')) for b in branches}

    assert_not_equal(commits_hexsha, commits_hexsha_)
    eq_(out[0]['datalad_stats'], ActivityStats())  # commit happened so stats were consumed
    # numbers seems to be right
    total_stats = out[0]['datalad_stats'].get_total()
    # but for some reason downloaded_size fluctuates.... why? TODO
    total_stats.downloaded_size = 0
    eq_(total_stats,
        ActivityStats(files=7, skipped=4, downloaded=1,
                      merges=[['incoming', 'incoming-processed']], renamed=1, urls=5, add_annex=2))

    # TODO: drop all annex content for all revisions, clean the cache, get the content for all files in
    # master in all of its revisions

test_openfmri_pipeline1.tags = ['intergration']