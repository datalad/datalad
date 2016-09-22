# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test install action

"""

import logging

from os.path import join as opj
from os.path import isdir
from os.path import exists
from os.path import realpath

from mock import patch

from datalad.api import create
from datalad.api import install
from datalad.consts import DATASETS_TOPURL
from datalad.utils import chpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import InstallFailedError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_in
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_false
from datalad.tests.utils import SkipTest
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import use_cassette
from datalad.tests.utils import skip_if_no_network
from datalad.utils import _path_
from datalad.utils import rmtree

from ..dataset import Dataset
from ..install import _get_installationpath_from_url
from ..install import _get_git_url_from_source

###############
# Test helpers:
###############


def test_installationpath_from_url():
    for p in ('lastbit',
              'lastbit/',
              '/lastbit',
              'lastbit.git',
              'lastbit.git/',
              'http://example.com/lastbit',
              'http://example.com/lastbit.git',
              ):
        eq_(_get_installationpath_from_url(p), 'lastbit')


def test_get_git_url_from_source():

    # resolves datalad RIs:
    eq_(_get_git_url_from_source('///subds'), DATASETS_TOPURL + 'subds')
    assert_raises(NotImplementedError, _get_git_url_from_source,
                  '//custom/subds')

    # doesn't harm others:
    eq_(_get_git_url_from_source('http://example.com'), 'http://example.com')
    eq_(_get_git_url_from_source('/absolute/path'), '/absolute/path')
    eq_(_get_git_url_from_source('file://localhost/some'),
        'file://localhost/some')
    eq_(_get_git_url_from_source('localhost/another/path'),
        'localhost/another/path')
    eq_(_get_git_url_from_source('user@someho.st/mydir'),
        'user@someho.st/mydir')
    eq_(_get_git_url_from_source('ssh://somewhe.re/else'),
        'ssh://somewhe.re/else')
    eq_(_get_git_url_from_source('git://github.com/datalad/testrepo--basic--r1'),
        'git://github.com/datalad/testrepo--basic--r1')


@with_tree(tree={'file.txt': '123'})
@serve_path_via_http
@with_tempfile
def _test_guess_dot_git(annex, path, url, tdir):
    repo = (AnnexRepo if annex else GitRepo)(path, create=True)
    repo.add('file.txt', commit=True, git=not annex)

    # we need to prepare to be served via http, otherwise it must fail
    with swallow_logs() as cml:
        assert_raises(GitCommandError, install, path=tdir, source=url)
    ok_(not exists(tdir))

    Runner(cwd=path)(['git', 'update-server-info'])

    with swallow_logs() as cml:
        installed = install(path=tdir, source=url)
        assert_not_in("Failed to get annex.uuid", cml.out)
    eq_(realpath(installed.path), realpath(tdir))
    ok_(exists(tdir))
    ok_clean_git(tdir, annex=annex)


def test_guess_dot_git():
    for annex in False, True:
        yield _test_guess_dot_git, annex


######################
# Test actual Install:
######################

def test_insufficient_args():
    assert_raises(InsufficientArgumentsError, install)
    assert_raises(TypeError, install, [])
    assert_raises(InsufficientArgumentsError, install, description="some")


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_install_crcns(tdir, ds_path):
    with chpwd(tdir):
        with swallow_logs(new_level=logging.INFO) as cml:
            install("all-nonrecursive", source="///")
            # since we didn't log decorations such as log level atm while
            # swallowing so lets check if exit code is returned or not
            # I will test both
            assert_not_in('ERROR', cml.out)
            # below one must not fail alone! ;)
            assert_not_in('with exit code', cml.out)

        # should not hang in infinite recursion
        install(_path_("all-nonrecursive/crcns"))
        ok_(exists(_path_("all-nonrecursive/crcns/.git/config")))

    # again, but into existing dataset:
    ds = create(ds_path)
    crcns = ds.install("///crcns")
    ok_(crcns.is_installed())
    eq_(crcns.path, opj(ds_path, "crcns"))
    assert_in(crcns.path, ds.get_subdatasets(absolute=True))


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tree(tree={'sub': {}})
def test_install_datasets_root(tdir):
    with chpwd(tdir):
        ds = install("///")
        ok_(ds.is_installed())
        eq_(ds.path, opj(tdir, 'datasets.datalad.org'))

        # do it a second time:
        with swallow_logs(new_level=logging.INFO) as cml:
            result = install("///")
            assert_in("appears to be installed already.", cml.out)
            eq_(result, ds)

        # and a third time into an existing something, that is not a dataset:
        with open(opj(tdir, 'sub', 'a_file.txt'), 'w') as f:
            f.write("something")

        with swallow_logs(new_level=logging.WARNING) as cml:
            result = install(path="sub", source="///")
            assert_in("already exists and is not an installed dataset", cml.out)
            ok_(result is None)


@with_testrepos('.*basic.*', flavors=['local-url', 'network', 'local'])
@with_tempfile(mkdir=True)
def test_install_simple_local(src, path):
    origin = Dataset(path)

    # now install it somewhere else
    ds = install(path=path, source=src)
    eq_(ds.path, path)
    ok_(ds.is_installed())
    if not isinstance(origin.repo, AnnexRepo):
        # this means it is a GitRepo
        ok_(isinstance(origin.repo, GitRepo))
        # stays plain Git repo
        ok_(isinstance(ds.repo, GitRepo))
        ok_(not isinstance(ds.repo, AnnexRepo))
        ok_(GitRepo.is_valid_repo(ds.path))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt'})
        ok_clean_git(path, annex=False)
    else:
        # must be an annex
        ok_(isinstance(ds.repo, AnnexRepo))
        ok_(AnnexRepo.is_valid_repo(ds.path, allow_noninitialized=False))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt', 'test-annex.dat'})
        ok_clean_git(path, annex=True)
        # no content was installed:
        ok_(not ds.repo.file_has_content('test-annex.dat'))


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_dataset_from_just_source(url, path):
    with chpwd(path, mkdir=True):
        ds = install(source=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    ok_clean_git(ds.path, annex=False)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@with_testrepos(flavors=['network'])
@with_tempfile
def test_install_dataset_from_just_source_via_path(url, path):
    # for remote urls only, the source could be given to `path`
    # to allows for simplistic cmdline calls
    # Q (ben): remote urls only? Sure? => TODO

    with chpwd(path, mkdir=True):
        ds = install(path=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    ok_clean_git(ds.path, annex=False)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_install_dataladri(src, topurl, path):
    # make plain git repo
    ds_path = opj(src, 'ds')
    gr = GitRepo(ds_path, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    Runner(cwd=gr.path)(['git', 'update-server-info'])
    # now install it somewhere else
    with patch('datalad.support.network.DATASETS_TOPURL', topurl), \
        swallow_logs():
        ds = install(path=path, source='///ds')
    eq_(ds.path, path)
    ok_clean_git(path, annex=False)
    ok_file_has_content(opj(path, 'test.txt'), 'some')


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_install_recursive(src, path_nr, path_r):
    # first install non-recursive:
    ds = install(path=path_nr, source=src, recursive=False)
    ok_(ds.is_installed())
    for sub in ds.get_subdatasets(recursive=True):
        ok_(not Dataset(opj(path_nr, sub)).is_installed(),
            "Unintentionally installed: %s" % opj(path_nr, sub))
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.get_subdatasets(recursive=True, fulfilled=False)),
        {'subm 1', 'subm 2'})

    # now recursively:
    ds_list = install(path=path_r, source=src, recursive=True)
    # installed a dataset and two subdatasets:
    eq_(len(ds_list), 3)
    ok_(all([isinstance(i, Dataset) for i in ds_list]))
    # we recurse top down during installation, so toplevel should appear at
    # first position in returned list
    eq_(ds_list[0].path, path_r)
    top_ds = ds_list[0]
    ok_(top_ds.is_installed())

    # the subdatasets are contained in returned list:
    # (Note: Until we provide proper (singleton) instances for Datasets,
    # need to check for their paths)
    assert_in(opj(top_ds.path, 'subm 1'), [i.path for i in ds_list])
    assert_in(opj(top_ds.path, 'subm 2'), [i.path for i in ds_list])

    eq_(len(top_ds.get_subdatasets(recursive=True)), 2)

    for sub in top_ds.get_subdatasets(recursive=True):
        subds = Dataset(opj(path_r, sub))
        ok_(subds.is_installed(),
            "Not installed: %s" % opj(path_r, sub))
        # no content was installed:
        ok_(not any(subds.repo.file_has_content(
            subds.repo.get_annexed_files())))
    # no unfulfilled subdatasets:
    ok_(top_ds.get_subdatasets(recursive=True, fulfilled=False) == [])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_recursive_with_data(src, path):

    # now again; with data:
    ds_list = install(path=path, source=src, recursive=True, get_data=True)
    # installed a dataset and two subdatasets:
    eq_(len(ds_list), 3)
    ok_(all([isinstance(i, Dataset) for i in ds_list]))
    # we recurse top down during installation, so toplevel should appear at
    # first position in returned list
    eq_(ds_list[0].path, path)
    top_ds = ds_list[0]
    ok_(top_ds.is_installed())
    if isinstance(top_ds.repo, AnnexRepo):
        ok_(all(top_ds.repo.file_has_content(top_ds.repo.get_annexed_files())))
    for sub in top_ds.get_subdatasets(recursive=True):
        subds = Dataset(opj(path, sub))
        ok_(subds.is_installed(), "Not installed: %s" % opj(path, sub))
        if isinstance(subds.repo, AnnexRepo):
            ok_(all(subds.repo.file_has_content(subds.repo.get_annexed_files())))


@with_testrepos(flavors=['local'])
# 'local-url', 'network'
# TODO: Somehow annex gets confused while initializing installed ds, whose
# .git/config show a submodule url "file:///aaa/bbb%20b/..."
# this is delivered by with_testrepos as the url to clone
@with_tempfile
def test_install_into_dataset(source, top_path):

    ds = create(top_path)

    subds = ds.install(path="sub", source=source, save=False)
    if isinstance(subds.repo, AnnexRepo) and subds.repo.is_direct_mode():
        ok_(exists(opj(subds.path, '.git')))
    else:
        ok_(isdir(opj(subds.path, '.git')))
    ok_(subds.is_installed())
    assert_in('sub', ds.get_subdatasets())
    # sub is clean:
    ok_clean_git(subds.path, annex=False)
    # top is not:
    assert_raises(AssertionError, ok_clean_git, ds.path, annex=False)
    ds.save('addsub')
    # now it is:
    ok_clean_git(ds.path, annex=False)


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_known_subdataset(src, path):

    # get the superdataset:
    ds = install(path=path, source=src)

    # subdataset not installed:
    subds = Dataset(opj(path, 'subm 1'))
    assert_false(subds.is_installed())
    assert_in('subm 1', ds.get_subdatasets(fulfilled=False))
    assert_not_in('subm 1', ds.get_subdatasets(fulfilled=True))
    # install it:
    ds.install('subm 1')
    ok_(subds.is_installed())
    ok_(AnnexRepo.is_valid_repo(subds.path, allow_noninitialized=False))
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    eq_(set(subds.repo.get_indexed_files()),
        {'test.dat', 'INFO.txt', 'test-annex.dat'})
    assert_not_in('subm 1', ds.get_subdatasets(fulfilled=False))
    assert_in('subm 1', ds.get_subdatasets(fulfilled=True))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_implicit_install(src, dst):

    origin_top = create(src)
    origin_sub = origin_top.create("sub")
    origin_subsub = origin_sub.create("subsub")
    with open(opj(origin_top.path, "file1.txt"), "w") as f:
        f.write("content1")
    origin_top.add("file1.txt")
    with open(opj(origin_sub.path, "file2.txt"), "w") as f:
        f.write("content2")
    origin_sub.add("file2.txt")
    with open(opj(origin_subsub.path, "file3.txt"), "w") as f:
        f.write("content3")
    origin_subsub.add("file3.txt")
    origin_top.save(auto_add_changes=True)

    # first, install toplevel:
    ds = install(path=dst, source=src)
    ok_(ds.is_installed())

    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # install 3rd level and therefore implicitly the 2nd:
    result = ds.install(path=opj("sub", "subsub"))
    ok_(sub.is_installed())
    ok_(subsub.is_installed())
    eq_(result, subsub)

    # clean up:
    rmtree(dst, chmod_files=True)
    ok_(not exists(dst))

    # again first toplevel:
    ds = install(path=dst, source=src)
    ok_(ds.is_installed())
    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # now implicit but wihtout an explicit dataset to install into
    # (deriving from CWD):
    with chpwd(dst):
        result = install(path=opj("sub", "subsub"))
        ok_(sub.is_installed())
        ok_(subsub.is_installed())
        eq_(result, subsub)


@with_tempfile(mkdir=True)
def test_failed_install(dspath):
    ds = create(dspath)
    assert_raises(InstallFailedError,
                  ds.install,
                  path="sub",
                  source="http://nonexistingreallyanything.somewhere/bla")


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_list(path, top_path):

    # we want to be able to install several things, if these are known
    # (no 'source' allowed). Therefore first toplevel:
    ds = install(path=top_path, source=path, recursive=False)
    ok_(ds.is_installed())
    sub1 = Dataset(opj(top_path, 'subm 1'))
    sub2 = Dataset(opj(top_path, 'subm 2'))
    ok_(not sub1.is_installed())
    ok_(not sub2.is_installed())

    # fails, when `source` is passed:
    assert_raises(ValueError, ds.install,
                  path=['subm 1', 'subm 2'],
                  source='something')

    # now should work:
    result = ds.install(path=['subm 1', 'subm 2'])
    ok_(sub1.is_installed())
    ok_(sub2.is_installed())
    eq_(set([i.path for i in result]), {sub1.path, sub2.path})


