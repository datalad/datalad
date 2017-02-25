# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from os import listdir
from os.path import join as opj, exists, lexists, basename
from collections import OrderedDict
from datalad.tests.utils import with_tempfile, eq_, ok_, SkipTest
from mock import patch

from ..annex import initiate_dataset
from ..annex import Annexificator
from ....tests.utils import assert_equal, assert_in
from ....tests.utils import assert_raises
from ....tests.utils import assert_true, assert_false
from ....tests.utils import with_tree, serve_path_via_http
from ....tests.utils import ok_file_under_git
from ....tests.utils import ok_file_has_content
from ....tests.utils import assert_cwd_unchanged
from ....tests.utils import put_file_under_git
from ...pipeline import load_pipeline_from_config
from ....consts import CRAWLER_META_CONFIG_PATH, DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE
from ....support.stats import ActivityStats
from ....support.annexrepo import AnnexRepo
from ....support.external_versions import external_versions


@with_tempfile(mkdir=True)
def test_annexificator_no_git_if_dirty(outdir):

    eq_(listdir(outdir), [])

    filepath = opj(outdir, '.myfile')
    with open(filepath, 'w'):
        pass

    eq_(listdir(outdir), ['.myfile'])
    assert_raises(RuntimeError, Annexificator, path=outdir)
    eq_(listdir(outdir), ['.myfile'])

    Annexificator(path=outdir, allow_dirty=True)
    eq_(sorted(listdir(outdir)), sorted(['.myfile', '.git']))


@with_tempfile(mkdir=True)
@with_tempfile()
def test_initiate_dataset(path, path2):
    dataset_path = opj(path, 'test')
    datas = list(initiate_dataset('template', 'testdataset', path=dataset_path)())
    assert_equal(len(datas), 1)
    data = datas[0]
    eq_(data['dataset_path'], dataset_path)
    crawl_cfg = opj(dataset_path, CRAWLER_META_CONFIG_PATH)
    ok_(exists, crawl_cfg)
    pipeline = load_pipeline_from_config(crawl_cfg)

    # by default we should initiate to MD5E backend
    fname = 'test.dat'
    f = opj(dataset_path, fname)
    annex = put_file_under_git(f, content="test", annexed=True)
    eq_(annex.get_file_backend(f), 'MD5E')

    # and even if we clone it -- nope -- since persistence is set by Annexificator
    # so we don't need to explicitly to commit it just in master since that might
    # not be the branch we will end up working in
    annex2 = AnnexRepo.clone(path=path2, url=dataset_path)
    annex3 = put_file_under_git(path2, 'test2.dat', content="test2", annexed=True)
    eq_(annex3.get_file_backend('test2.dat'), 'MD5E')

    raise SkipTest("TODO much more")


@with_tree(tree=[
    ('d1', (
        ('1.dat', '1.dat load'),
    ))
])
@serve_path_via_http()
@with_tempfile(mkdir=True)
def _test_annex_file(mode, topdir, topurl, outdir):
    annex = Annexificator(path=outdir, mode=mode,
                          statusdb='fileattr',
                          options=["-c", "annex.largefiles=exclude=*.txt"])

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
    list(annex.finalize()({}))
    assert(lexists(tfile))

    ok_file_under_git(tfile, annexed=True)
    if mode == 'full':
        ok_file_has_content(tfile, '1.dat load')
    else:
        # in fast or relaxed mode there must not be any content
        assert_raises(AssertionError, ok_file_has_content, tfile, '1.dat load')

    whereis = annex.repo.whereis(tfile)
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
    list(annex.finalize()({}))
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
    special_remotes = [DATALAD_SPECIAL_REMOTE, ARCHIVES_SPECIAL_REMOTE]
    annex = Annexificator(path=repo_path,
                          allow_dirty=True,
                          mode=mode,
                          direct=direct,
                          special_remotes=special_remotes,
                          options=["-c", "annex.largefiles=exclude=*.txt and exclude=SOMEOTHER"])
    output_add = list(annex({'filename': '1.tar'}))  # adding it to annex
    assert_equal(output_add, [{'filename': '1.tar'}])

    if external_versions['cmd:annex'] >= '6.20170208':
        # should have fixed remotes
        from datalad.consts import DATALAD_SPECIAL_REMOTES_UUIDS
        for remote in special_remotes:
            eq_(annex.repo.get_description(uuid=DATALAD_SPECIAL_REMOTES_UUIDS[remote]),
                '[%s]' % remote)

    #stats = ActivityStats()
    #output_add[0]['datalad_stats'] = ActivityStats()
    output_addarchive = list(
        annex.add_archive_content(
            existing='archive-suffix',
            delete=True,
            strip_leading_dirs=True,)(output_add[0]))
    assert_equal(output_addarchive,
                 [{'datalad_stats': ActivityStats(add_annex=1, add_git=1, files=3, renamed=2),
                   'filename': '1.tar'}])
    if not direct:  # Notimplemented otherwise
        assert_true(annex.repo.dirty)
    annex.repo.commit("added")
    ok_file_under_git(annex.repo.path, 'file.txt', annexed=False)
    ok_file_under_git(annex.repo.path, '1.dat', annexed=True)
    assert_false(lexists(opj(repo_path, '1.tar')))
    if not direct:  # Notimplemented otherwise
        assert_false(annex.repo.dirty)


def test_add_archive_content_tar():
    for direct in (True, False):
        yield _test_add_archive_content_tar, direct


@assert_cwd_unchanged()
@with_tempfile(mkdir=True)
@with_tree(tree={'file': 'load'})
@serve_path_via_http
def test_add_dir_file(repo_path, p, topurl):
    # test whenever file becomes a directory and then back a file.  Should all work!
    annex = Annexificator(path=repo_path, auto_finalize=False)
    url = "%s/file" % topurl

    path1 = opj(repo_path, 'd')
    data1 = {'filename': 'd', 'url': url}
    out1 = list(annex(data1))

    # becomes a directory which carries a file
    data2 = {'filename': 'f', 'url': url, 'path': 'd'}
    # but since we didn't commit previous file yet -- should puke!
    assert_raises(RuntimeError, list, annex(data2))
    list(annex.finalize()({}))  # so it gets committed
    ok_file_under_git(path1, annexed=True)

    # and after that it should proceed normally
    #import pdb; pdb.set_trace()
    out2 = list(annex(data2))
    path2 = opj(repo_path, 'd', 'f')
    ok_(exists(path2))

    # tricky one -- becomes back a file... what if repo was dirty and files under dir were staged? TODO
    assert_raises(RuntimeError, list, annex(data1))
    list(annex.finalize()({}))  # so it gets committed
    ok_file_under_git(path2, annexed=True)

    list(annex(data1))
    list(annex.finalize()({}))  # so it gets committed
    ok_file_under_git(path1, annexed=True)

    # with auto_finalize (default) it should go smoother ;)
    annex = Annexificator(path=repo_path)
    list(annex(data2))
    # wouldn't happen without explicit finalize to commit whatever new is staged
    # ok_file_under_git(path2, annexed=True)
    list(annex(data1))
    list(annex.finalize()({}))  # so it gets committed
    ok_file_under_git(path1, annexed=True)


def test_commit_versions():
    raise SkipTest("TODO: is tested only as a part of test_openfmri.py")


@with_tempfile(mkdir=True)
def test_remove_other_versions(repo_path):
    annex = Annexificator(path=repo_path, create=True)

    class version_db:
        version = '1.0.0'
        versions = OrderedDict([
            ('10.0.0', {}),  # wrong order -- will fail and we will pop it
            ('1.0.0', {'a': 'a_1.0.0'}),
            ('2.0.0', {'b': 'b_2.0.0', 'c': 'c_2.0.0'}),
            ('2.0.1', {'c': 'c_2.0.1'}),  # if no overlay, b is gone, overlay=2 should keep b
            ('2.1.1', {'c': 'c_2.1.1'}),  # b should disappear if overlay=2, but stay if
            ('3', {'d': 'd_3'}),
        ])

    assert_raises(ValueError,
                  annex.remove_other_versions,
                  'name', db=version_db)

    data = {'datalad_stats': ActivityStats()}
    rov = annex.remove_other_versions(db=version_db)  # generator

    # we have that incorrectly ordered version inside
    assert_raises(AssertionError, next, rov(data))
    version_db.versions.pop('10.0.0')  # remove the abuser

    class Unlinker(object):

        def __init__(self):
            self.unlinked = []
            self.allfiles = set()
            # Let's also record all present files
            for vfs in version_db.versions.values():
                self.allfiles.update(vfs.values())
            self._remaining = self.allfiles.copy()

        def Find_files(self):
            """To provide another mock callable"""
            def find_files(*args, **kwargs):
                assert_equal(kwargs.get('topdir'), repo_path)
                # return full path
                return [opj(repo_path, x) for x in self._remaining]
            return find_files

        def __call__(self, s):
            bs = basename(s)
            assert(bs in self._remaining)
            self.unlinked.append(bs)
            self._remaining.remove(bs)

        @property
        def remaining(self):
            # strip the repopath
            return self._remaining


    def _check(version, remaining=None, unlinked=None, **kwargs):
        """Helper - for a given version and kwargs for remove_ - what to expect"""
        version_db.version = version
        data = {'datalad_stats': ActivityStats()}
        rov = annex.remove_other_versions(db=version_db, **kwargs)  # generator
        with patch('os.unlink', new_callable=Unlinker) as cmunlink, \
                patch('os.path.lexists', return_value=True),\
                patch('datalad.crawler.nodes.annex.find_files', new_callable=cmunlink.Find_files):
            out = list(rov(data))
        assert_equal(len(out), 1)
        eq_(out[0]['datalad_stats'].versions, [version])
        if remaining is not None:
            eq_(cmunlink.remaining, remaining)
        if unlinked is not None:
            eq_(cmunlink.unlinked, unlinked)
        eq_(cmunlink.remaining.union(cmunlink.unlinked), cmunlink.allfiles)

    def check(*args, **kwargs):
        _check(*args, **kwargs)
        kwargs = kwargs.copy()   # without remove unversioned
        # in our test results should be the same
        kwargs['remove_unversioned'] = True
        _check(*args, **kwargs)  # remove_unversioned=True

    check('1.0.0', remaining={'a_1.0.0'})
    # even though due to overlay=0 all versions are identical, there were no
    # version before 1.0.0, and all later are removed regardless or overlay
    check('1.0.0', remaining={'a_1.0.0'}, overlay=0)

    check('2.0.0', remaining={'b_2.0.0', 'c_2.0.0'})
    check('2.0.0', remaining={'b_2.0.0', 'c_2.0.0'}, overlay=1)
    check('2.0.0', remaining={'b_2.0.0', 'c_2.0.0'}, overlay=lambda x: x[:1])
    # but with overlay=0 we would also get files from 1
    check('2.0.0', remaining={'a_1.0.0', 'b_2.0.0', 'c_2.0.0'}, overlay=0)

    check('2.0.1', remaining={'c_2.0.1'})
    check('2.0.1', remaining={'b_2.0.0', 'c_2.0.1'}, overlay=1)
    check('2.0.1', remaining={'b_2.0.0', 'c_2.0.1'}, overlay=2)
    check('2.0.1', remaining={'a_1.0.0', 'b_2.0.0', 'c_2.0.1'}, overlay=0)

    check('2.1.1', remaining={'c_2.1.1'})
    check('2.1.1', remaining={'c_2.1.1'}, overlay=2)
    check('2.1.1', remaining={'b_2.0.0', 'c_2.1.1'}, overlay=1)
    check('2.1.1', remaining={'a_1.0.0', 'b_2.0.0', 'c_2.1.1'}, overlay=0)

    check('3', remaining={'d_3'})
    check('3', remaining={'d_3'}, overlay=1)
    check('3', remaining={'d_3'}, overlay=2)
    check('3', remaining={'a_1.0.0', 'b_2.0.0', 'c_2.1.1', 'd_3'}, overlay=0)

    # if name changes
    version_db.versions['2.1.1'] = {'c00.dat': 'c00_2.1.1'}
    # if we don't do anything special, it would have its own life:
    check('2.1.1', remaining={'c00_2.1.1'})
    check('2.1.1', remaining={'c00_2.1.1'}, overlay=2)
    check('2.1.1', remaining={'b_2.0.0', 'c_2.0.1', 'c00_2.1.1'}, overlay=1)
    check('2.1.1', remaining={'a_1.0.0', 'b_2.0.0', 'c_2.0.1', 'c00_2.1.1'}, overlay=0)
    # but we should be able to specify to "unify" unversioned name more by providing
    # replacement pattern
    kw = dict(fpath_subs=[('c00', 'c'), ('\.dat', '')])
    check('2.1.1', remaining={'b_2.0.0', 'c00_2.1.1'}, overlay=1, **kw)
    check('2.1.1', remaining={'a_1.0.0', 'b_2.0.0', 'c00_2.1.1'}, overlay=0, **kw)
