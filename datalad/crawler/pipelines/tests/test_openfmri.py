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
from ....tests.utils import eq_, assert_not_equal, ok_, assert_raises
from ....tests.utils import assert_in, assert_not_in
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

def check_dropall_get(repo):
    # drop all annex content for all revisions, clean the cache, get the content for all files in
    # master in all of its revisions
    t1w_fpath = opj(repo.path, 'sub-1', 'anat', 'sub-1_T1w.dat')
    ok_file_has_content(t1w_fpath, "mighty load 2.0.0")
    # --force since it would fail to verify presence in case we remove archives keys... TODO
    repo._annex_custom_command([], ["git", "annex", "drop", "--all", "--force"])
    clean(dataset=repo.path)  # remove possible extracted archives
    with assert_raises(AssertionError):
        ok_file_has_content(t1w_fpath, "mighty load 2.0.0")
    repo.get('.')
    ok_file_has_content(t1w_fpath, "mighty load 2.0.0")


def add_to_index(index_file, content):
    with open(index_file) as f:
        old_index = f.read()
    with open(index_file, 'w') as f:
        f.write(old_index.replace(_PLUG_HERE, content + _PLUG_HERE))


def remove_from_index(index_file, regexp):
    with open(index_file) as f:
        old_index = f.read()
    with open(index_file, 'w') as f:
        f.write(re.sub(regexp, '', old_index))


@skip_if_no_network
@use_cassette('openfmri')
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
    all_aws_entries = sink2.get_values(['dataset', 'url_text', 'url'])
    ok_(len(all_aws_entries) > len(urls))  # that we have at least as many ;-)
    #print('\n'.join(map(str, all_aws_entries)))
    all_licenses = sink_licenses.get_values(['dataset', 'url_text', 'url'])
    eq_(len(all_licenses), len(urls))
    #print('\n'.join(map(str, all_licenses)))


@skip_if_no_network
@use_cassette('openfmri-1')
@with_tempfile(mkdir=True)
def __test_basic_openfmri_dataset_pipeline_with_annex(path):
    skip_if_no_module('scrapy')  # e.g. not present under Python3
    dataset_index = 1
    dataset_name = 'ds%06d' % dataset_index
    dataset_url = 'https://openfmri.org/dataset/' + dataset_name
    # needs to be a non-existing directory
    dataset_path = opj(path, dataset_name)
    # we need to pre-initiate dataset
    list(initiate_dataset('openfmri', dataset_index, path=dataset_path)())

    annex = Annexificator(
        dataset_path,
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

_versioned_files = """
                            <a href="ds666_R1.0.0.tar.gz">Raw data on AWS version 1</a>
                            <a href="ds666_R1.0.1.tar.gz">Raw data on AWS version 2</a>
                            <a href="ds666-beh_R1.0.1.tar.gz">Beh data on AWS version 2</a>
"""

@with_tree(tree={
    'ds666': {
        # there could also be a case of a file with "unique" name without versioned counterpart
        # e.g. ds666_models.tar.gz  which seems to be not treated correctly (not placed into any
        # version in case of ds000017)
        'index.html': """<html><body>
                            <a href="release_history.txt">Release History</a>
                            <a href="ds666.tar.gz">Raw data on AWS, no version</a>
                            %s
                          </body></html>""" % _PLUG_HERE,
        'release_history.txt': '1.0.1 fixed\n1.0.0 whatever',
        'ds666.tar.gz':     {'ds-666': {'sub1': {'anat': {'sub-1_T1w.dat': "mighty load in old format"}}}},
        'ds666_R1.0.0.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 1.0.0"}}}},
        'ds666_R1.0.1.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 1.0.1"}}}},
        'ds666-beh_R1.0.1.tar.gz': {'beh.tar.gz': {'ds666': {'sub-1': {'beh': {'responses.tsv': "1"}}}}},
        'ds666_R2.0.0.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 2.0.0"}}}},
    }},
    archives_leading_dir=False
)
@serve_path_via_http
@with_tempfile
@with_tempfile
def test_openfmri_pipeline1(ind, topurl, outd, clonedir):
    index_html = opj(ind, 'ds666', 'index.html')

    list(initiate_dataset(
        template="openfmri",
        dataset_name='dataladtest-ds666',
        path=outd,
        data_fields=['dataset'])({'dataset': 'ds666'}))

    with chpwd(outd):
        pipeline = ofpipeline('ds666', versioned_urls=False, topurl=topurl)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    repo = AnnexRepo(outd, create=False)  # to be used in the checks
    # Inspect the tree -- that we have all the branches
    branches = {'master', 'incoming', 'incoming-processed', 'git-annex'}
    eq_(set(repo.get_branches()), branches)
    # We do not have custom changes in master yet, so it just follows incoming-processed atm
    # eq_(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # Since we did initiate_dataset -- now we have separate master!
    assert_not_equal(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # and that one is different from incoming
    assert_not_equal(repo.get_hexsha('incoming'), repo.get_hexsha('incoming-processed'))

    t1w_fpath_nover = opj(outd, 'sub1', 'anat', 'sub-1_T1w.dat')
    ok_file_has_content(t1w_fpath_nover, "mighty load in old format")

    #
    # And now versioned files were specified!
    #
    add_to_index(index_html, content=_versioned_files)

    with chpwd(outd):
        pipeline = ofpipeline('ds666', versioned_urls=False, topurl=topurl)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    ok_(not exists(t1w_fpath_nover),
        "%s file should no longer be there if unversioned files get removed correctly" % t1w_fpath_nover)
    repo = AnnexRepo(outd, create=False)  # to be used in the checks
    # Inspect the tree -- that we have all the branches
    branches = {'master', 'incoming', 'incoming-processed', 'git-annex'}
    eq_(set(repo.get_branches()), branches)
    # We do not have custom changes in master yet, so it just follows incoming-processed atm
    # eq_(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # Since we did initiate_dataset -- now we have separate master!
    assert_not_equal(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # and that one is different from incoming
    assert_not_equal(repo.get_hexsha('incoming'), repo.get_hexsha('incoming-processed'))

    # actually the tree should look quite neat with 1.0.0 tag having 1 parent in incoming
    # 1.0.1 having 1.0.0 and the 2nd commit in incoming as parents

    commits = {b: list(repo.get_branch_commits(b)) for b in branches}
    commits_hexsha = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    commits_l = {b: list(repo.get_branch_commits(b, limit='left-only')) for b in branches}
    eq_(len(commits['incoming']), 3)
    eq_(len(commits_l['incoming']), 3)
    eq_(len(commits['incoming-processed']), 6)
    eq_(len(commits_l['incoming-processed']), 4)  # because original merge has only 1 parent - incoming
    eq_(len(commits['master']), 12)  # all commits out there -- dataset init, crawler init + 3*(incoming, processed, meta data aggregation, merge)
    eq_(len(commits_l['master']), 6)

    # Check tags for the versions
    eq_(out[0]['datalad_stats'].get_total().versions, ['1.0.0', '1.0.1'])
    # +1 because original "release" was assumed to be 1.0.0
    eq_([x.name for x in repo.repo.tags], ['1.0.0', '1.0.0+1', '1.0.1'])
    eq_(repo.repo.tags[0].commit.hexsha, commits_l['master'][-4].hexsha)  # next to the last one
    eq_(repo.repo.tags[-1].commit.hexsha, commits_l['master'][0].hexsha)  # the last one

    def hexsha(l):
        return l.__class__(x.hexsha for x in l)

    # Verify that we have desired tree of merges
    eq_(hexsha(commits_l['incoming-processed'][0].parents), (commits_l['incoming-processed'][1].hexsha,
                                                             commits_l['incoming'][0].hexsha))
    eq_(hexsha(commits_l['incoming-processed'][2].parents), (commits_l['incoming'][2].hexsha,))

    eq_(hexsha(commits_l['master'][0].parents), (commits_l['master'][1].hexsha,
                                                 commits_l['incoming-processed'][0].hexsha))

    eq_(hexsha(commits_l['master'][1].parents), (commits_l['master'][2].hexsha,
                                                 commits_l['incoming-processed'][1].hexsha))

    with chpwd(outd):
        eq_(set(glob('*')), {'changelog.txt', 'sub-1'})
        all_files = sorted(find_files('.'))

    t1w_fpath = opj(outd, 'sub-1', 'anat', 'sub-1_T1w.dat')
    ok_file_has_content(t1w_fpath, "mighty load 1.0.1")
    ok_file_under_git(opj(outd, 'changelog.txt'), annexed=False)
    ok_file_under_git(t1w_fpath, annexed=True)

    target_files = {
        './.datalad/config',
        './.datalad/meta/meta.json',
        './.datalad/crawl/crawl.cfg',
        # no more!
        # './.datalad/config.ttl', './.datalad/datalad.ttl',
        './.datalad/crawl/statuses/incoming.json',
        './.datalad/crawl/versions/incoming.json',
        './changelog.txt', './sub-1/anat/sub-1_T1w.dat', './sub-1/beh/responses.tsv'}
    target_incoming_files = {
        '.gitattributes',  # we marked default backend right in the incoming
        'changelog.txt',
        'ds666.tar.gz',
        'ds666-beh_R1.0.1.tar.gz', 'ds666_R1.0.0.tar.gz', 'ds666_R1.0.1.tar.gz', 'ds666_R2.0.0.tar.gz',
        '.datalad/crawl/statuses/incoming.json',
        '.datalad/crawl/versions/incoming.json'
    }
    eq_(set(all_files), target_files)

    # check that -beh was committed in 2nd commit in incoming, not the first one
    assert_not_in('ds666-beh_R1.0.1.tar.gz', repo.get_files(commits_l['incoming'][-1]))
    assert_in('ds666-beh_R1.0.1.tar.gz', repo.get_files(commits_l['incoming'][0]))

    # rerun pipeline -- make sure we are on the same in all branches!
    with chpwd(outd):
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    commits_hexsha_ = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    eq_(commits_hexsha, commits_hexsha_)  # i.e. nothing new
    # actually we do manage to add_git 1 (README) since it is generated committed directly to git
    # BUT now fixed -- if not committed (was the same), should be marked as skipped
    # Nothing was committed so stats leaked all the way up
    eq_(out[0]['datalad_stats'], ActivityStats(files=5, skipped=5, urls=5))
    eq_(out[0]['datalad_stats'], out[0]['datalad_stats'].get_total())

    # rerun pipeline when new content is available
    # add new revision, rerun pipeline and check that stuff was processed/added correctly
    add_to_index(index_html,
                 content='<a href="ds666_R2.0.0.tar.gz">Raw data on AWS version 2.0.0</a>')

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
    commits_ = {b: list(repo.get_branch_commits(b)) for b in branches}
    commits_hexsha_ = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    commits_l_ = {b: list(repo.get_branch_commits(b, limit='left-only')) for b in branches}

    assert_not_equal(commits_hexsha, commits_hexsha_)
    eq_(out[0]['datalad_stats'], ActivityStats())  # commit happened so stats were consumed
    # numbers seems to be right
    total_stats = out[0]['datalad_stats'].get_total()
    # but for some reason downloaded_size fluctuates.... why? probably archiving...?
    total_stats.downloaded_size = 0
    eq_(total_stats,
        ActivityStats(files=8, skipped=5, downloaded=1, renamed=1, urls=6,
                      add_annex=2,  # add_git=1, # README
                      versions=['2.0.0'],
                      merges=[['incoming', 'incoming-processed']]))

    check_dropall_get(repo)

    # Let's see if pipeline would remove files we stopped tracking
    remove_from_index(index_html, '<a href=.ds666_R1.0.0[^<]*</a>')
    with chpwd(outd):
        with swallow_logs(new_level=logging.WARNING) as cml:
            out = run_pipeline(pipeline)
            # since files get removed in incoming, but repreprocessed completely
            # incomming-processed and merged into master -- new commits will come
            # They shouldn't have any difference but still should be new commits
            assert_in("There is already a tag 2.0.0 in the repository", cml.out)
    eq_(len(out), 1)
    incoming_files = repo.get_files('incoming')
    target_incoming_files.remove('ds666_R1.0.0.tar.gz')
    eq_(set(incoming_files), target_incoming_files)
    commits_hexsha_removed = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    # our 'statuses' database should have recorded the change thus got a diff
    # which propagated through all branches
    for b in 'master', 'incoming-processed':
        # with non persistent DB we had no changes
        # eq_(repo.repo.branches[b].commit.diff(commits_hexsha_[b][0]), [])
        eq_(repo.repo.branches[b].commit.diff(commits_hexsha_[b][0])[0].a_path,
            '.datalad/crawl/statuses/incoming.json')
    dincoming = repo.repo.branches['incoming'].commit.diff(commits_hexsha_['incoming'][0])
    eq_(len(dincoming), 2)  # 2 diff objects -- 1 file removed, 1 statuses updated
    eq_(set([d.a_path for d in dincoming]),
        {'.datalad/crawl/statuses/incoming.json', 'ds666_R1.0.0.tar.gz'})
    # since it seems to diff "from current to the specified", it will be listed as new_file
    assert any(d.new_file for d in dincoming)

    eq_(out[0]['datalad_stats'].get_total().removed, 1)
    assert_not_equal(commits_hexsha_, commits_hexsha_removed)

    # we will check if a clone would be crawling just as good
    from datalad.api import crawl

    # make a brand new clone
    GitRepo.clone(outd, clonedir)

    def _pipeline(*args, **kwargs):
        """Helper to mock openfmri.pipeline invocation so it looks at our 'server'"""
        kwargs = updated(kwargs, {'topurl': topurl, 'versioned_urls': False})
        return ofpipeline(*args,  **kwargs)

    with chpwd(clonedir), patch.object(openfmri, 'pipeline', _pipeline):
        output, stats = crawl()  # we should be able to recrawl without doing anything
        ok_(stats, ActivityStats(files=6, skipped=6, urls=5))

test_openfmri_pipeline1.tags = ['integration']


@with_tree(tree={
    'ds666': {
        'index.html': """<html><body>
                            <a href="release_history.txt">Release History</a>
                            <a href="ds666.tar.gz">Raw data on AWS version 1</a>
                            %s
                          </body></html>""" % _PLUG_HERE,
        'release_history.txt': '1.0.1 fixed\n1.0.0 whatever',
        'ds666.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "1.0.0"}}}},
        # this one will get renamed, not added to index
        'ds666_R2.0.0.tar.gz':     {'ds666': {'sub-1': {'anat': {'sub-1_T1w.dat': "mighty load 2.0.0"}}}},
    }},
    archives_leading_dir=False
)
@serve_path_via_http
@with_tempfile
def test_openfmri_pipeline2(ind, topurl, outd):
    # no versioned files -- should still work! ;)

    list(initiate_dataset(
        template="openfmri",
        dataset_name='dataladtest-ds666',
        path=outd,
        data_fields=['dataset'])({'dataset': 'ds666'}))

    with chpwd(outd):
        pipeline = ofpipeline('ds666', versioned_urls=False, topurl=topurl)
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    repo = AnnexRepo(outd, create=False)  # to be used in the checks
    # Inspect the tree -- that we have all the branches
    branches = {'master', 'incoming', 'incoming-processed', 'git-annex'}
    eq_(set(repo.get_branches()), branches)
    # We do not have custom changes in master yet, so it just follows incoming-processed atm
    # eq_(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # Since we did initiate_dataset -- now we have separate master!
    assert_not_equal(repo.get_hexsha('master'), repo.get_hexsha('incoming-processed'))
    # and that one is different from incoming
    assert_not_equal(repo.get_hexsha('incoming'), repo.get_hexsha('incoming-processed'))

    # actually the tree should look quite neat with 1.0.0 tag having 1 parent in incoming
    # 1.0.1 having 1.0.0 and the 2nd commit in incoming as parents

    commits = {b: list(repo.get_branch_commits(b)) for b in branches}
    commits_hexsha = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    commits_l = {b: list(repo.get_branch_commits(b, limit='left-only')) for b in branches}
    eq_(len(commits['incoming']), 1)
    eq_(len(commits_l['incoming']), 1)
    eq_(len(commits['incoming-processed']), 2)
    eq_(len(commits_l['incoming-processed']), 2)  # because original merge has only 1 parent - incoming
    # to avoid 'dataset init' commit create() needs save=False
    eq_(len(commits['master']), 6)  # all commits out there, dataset init, crawler, init, incoming, incoming-processed, meta data aggregation, merge
    eq_(len(commits_l['master']), 4)  # dataset init, init, meta data aggregation, merge

    # rerun pipeline -- make sure we are on the same in all branches!
    with chpwd(outd):
        out = run_pipeline(pipeline)
    eq_(len(out), 1)

    commits_hexsha_ = {b: list(repo.get_branch_commits(b, value='hexsha')) for b in branches}
    eq_(commits_hexsha, commits_hexsha_)  # i.e. nothing new
    eq_(out[0]['datalad_stats'], ActivityStats(files=2, skipped=2, urls=2))
    eq_(out[0]['datalad_stats'], out[0]['datalad_stats'].get_total())

    os.rename(opj(ind, 'ds666', 'ds666_R2.0.0.tar.gz'), opj(ind, 'ds666', 'ds666.tar.gz'))

    with chpwd(outd):
        out = run_pipeline(pipeline)
    eq_(len(out), 1)
    eq_(out[0]['datalad_stats'], ActivityStats())  # was committed
    stats_total = out[0]['datalad_stats'].get_total()
    stats_total.downloaded_size = 0
    eq_(stats_total,
        ActivityStats(files=4, overwritten=1, skipped=1, downloaded=1,
                      merges=[['incoming', 'incoming-processed']],
                      versions=['1.0.0'],
                      renamed=1, urls=2, add_annex=2))
    # in reality there is also 1.0.0+1 tag since file changed but no version suffix
    eq_([x.name for x in repo.repo.tags], ['1.0.0', '1.0.0+1'])

    check_dropall_get(repo)
test_openfmri_pipeline2.tags = ['integration']


from ..openfmri_s3 import collection_pipeline, pipeline


# TODO: RF to provide a generic/reusable test for this
@with_tempfile(mkdir=True)
def test_smoke_pipelines(d):
    # Just to verify that we can correctly establish the pipelines
    AnnexRepo(d, create=True)
    with chpwd(d):
        with swallow_logs():
            for p in [pipeline('bogus'), collection_pipeline()]:
                ok_(len(p) > 1)
