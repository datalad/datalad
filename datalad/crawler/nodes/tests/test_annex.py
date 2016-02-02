# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os.path import join as opj, exists, lexists
from datalad.tests.utils import with_tempfile, eq_, ok_, SkipTest

from ..annex import initiate_handle
from ..annex import Annexificator
from ....tests.utils import assert_equal, assert_in
from ....tests.utils import assert_raises
from ....tests.utils import assert_true, assert_false
from ....tests.utils import with_tree, serve_path_via_http
from ....tests.utils import ok_file_under_git
from ....tests.utils import ok_file_has_content
from ....tests.utils import assert_cwd_unchanged
from ...pipeline import load_pipeline_from_config
from ....consts import CRAWLER_META_CONFIG_PATH, DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE
from ....support.stats import ActivityStats

@with_tempfile(mkdir=True)
def test_initialize_handle(path):
    handle_path = opj(path, 'test')
    datas = list(initiate_handle('template', 'testhandle', path=handle_path)())
    assert_equal(len(datas), 1)
    data = datas[0]
    eq_(data['handle_path'], handle_path)
    crawl_cfg = opj(handle_path, CRAWLER_META_CONFIG_PATH)
    ok_(exists, crawl_cfg)
    pipeline = load_pipeline_from_config(crawl_cfg)
    raise SkipTest("TODO much more")


@with_tree(tree=[
    ('d1', (
        ('1.dat', '1.dat load'),
    ))
])
@serve_path_via_http()
@with_tempfile(mkdir=True)
def _test_annex_file(mode, topdir, topurl, outdir):
    annex = Annexificator(path=outdir, mode=mode, options=["-c", "annex.largefiles=exclude=*.txt"])

    input = {'url': "%sd1/1.dat" % topurl, 'filename': '1-copy.dat'}
    tfile = opj(outdir, '1-copy.dat')
    expected_output = [input.copy()]   # nothing to be added/changed
    output = list(annex(input))
    assert_equal(output, expected_output)

    # addurl is batched, and we haven't forced annex flushing so there should
    # be a batched process
    assert_equal(len(annex.repo._batched), 1)
    assert_raises(AssertionError, ok_file_under_git, tfile, annexed=True)
    # if we finalize, it should flush batched annexes and commit
    list(annex.finalize({}))
    assert(lexists(tfile))

    ok_file_under_git(tfile, annexed=True)
    if mode == 'full':
        ok_file_has_content(tfile, '1.dat load')
    else:
        # in fast or relaxed mode there must not be any content
        assert_raises(AssertionError, ok_file_has_content, tfile, '1.dat load')

    whereis = annex.repo.annex_whereis(tfile)
    assert_in(annex.repo.WEB_UUID, whereis)  # url must have been added
    assert_equal(len(whereis), 1 + int(mode == 'full'))
    # TODO: check the url
    # Neither file should not be attempted to download again, since nothing changed
    # and by default we do use files db
    output = list(annex(input))
    assert_equal(output, [])  # nothing was done, so annex didn't yield data
    annex.yield_non_updated = True

    input_with_stats = input.copy()
    input_with_stats['datalad_stats'] = ActivityStats()
    output = list(annex(input_with_stats))
    assert_equal(output[0]['datalad_stats'], ActivityStats(files=1, urls=1, skipped=1))

    # but if we change that file, it should re-download it now
    with open(opj(topdir, 'd1', '1.dat'), 'a') as f:
        f.write("+")
    output = list(annex(input_with_stats))
    stats = output[0]['datalad_stats']
    stats.downloaded_time = 0
    # 2 since we are reusing the same stats
    download_stats = dict(downloaded=1, downloaded_size=11) if mode == 'full' else {}
    addskip_stats = dict(add_annex=0, skipped=2, overwritten=0) if mode == 'relaxed' else dict(add_annex=1, skipped=1, overwritten=1)
    kwargs = download_stats.copy()
    kwargs.update(addskip_stats)
    assert_equal(stats, ActivityStats(files=2, urls=2, **kwargs))

    # Download into a file which will be added to git
    # TODO: for now added to git only in full mode. in --fast or --relaxed, still goes to annex
    # http://git-annex.branchable.com/bugs/treatment_of_largefiles_is_not_working_for_addurl_--fast___40__or_--relaxed__41__/
    input = {'url': "%sd1/1.dat" % topurl, 'filename': '1.txt', 'datalad_stats': ActivityStats()}
    tfile = opj(outdir, '1.txt')
    output = list(annex(input))
    annexed = mode not in {'full'}
    list(annex.finalize({}))
    if not annexed:
        ok_file_has_content(tfile, '1.dat load+')
    else:
        assert_raises(AssertionError, ok_file_has_content, tfile, '1.dat load+')
    ok_file_under_git(tfile, annexed=annexed)
    assert_equal(len(output), 1)
    stats = output[0]['datalad_stats']
    # reset varying metric
    stats.downloaded_time = 0
    assert_equal(stats, ActivityStats(files=1, urls=1, add_git=1-int(annexed), add_annex=int(annexed), **download_stats))

    # Let's add a file without specifying URL
    sfilepath = opj(outdir, 'sample.txt')
    with open(sfilepath, 'w') as f:
        f.write("sample")
    ok_file_has_content(sfilepath, "sample")
    output = list(annex({'filename': 'sample.txt', 'datalad_stats': ActivityStats()}))
    ok_file_under_git(sfilepath, annexed=False)
    assert(output)
    assert_equal(output[0]['datalad_stats'], ActivityStats(files=1, add_git=1))


def test_annex_file():
    for mode in ('full', 'fast', 'relaxed',):
        yield _test_annex_file, mode


@assert_cwd_unchanged()  # we are passing annex, not chpwd
@with_tree(tree={'1.tar': {'file.txt': 'load',
                           '1.dat': 'load2'}})
def _test_add_archive_content_tar(direct, repo_path):
    mode = 'full'
    annex = Annexificator(path=repo_path,
                          allow_dirty=True,
                          mode=mode,
                          direct=direct,
                          special_remotes=[DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE],
                          options=["-c", "annex.largefiles=exclude=*.txt and exclude=SOMEOTHER"])
    output_add = list(annex({'filename': '1.tar'}))  # adding it to annex
    assert_equal(output_add, [{'filename': '1.tar'}])

    #stats = ActivityStats()
    #output_add[0]['datalad_stats'] = ActivityStats()
    output_addarchive = list(
        annex.add_archive_content(
            existing='archive-suffix',
            strip_leading_dirs=True,)(output_add[0]))
    assert_equal(output_addarchive,
                 [{'datalad_stats': ActivityStats(add_annex=1, add_git=1, files=3, renamed=2),
                   'filename': '1.tar'}])
    if not direct:  # Notimplemented otherwise
        assert_true(annex.repo.dirty)
    annex.repo.commit("added")
    ok_file_under_git(repo_path, 'file.txt', annexed=False)
    ok_file_under_git(repo_path, '1.dat', annexed=True)
    assert_false(lexists(opj(repo_path, '1.tar')))
    if not direct:  # Notimplemented otherwise
        assert_false(annex.repo.dirty)

def test_add_archive_content_tar():
    for direct in (True, False):
        yield _test_add_archive_content_tar, direct