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
import os

from os.path import join as opj
from os.path import isdir
from os.path import exists
from os.path import realpath
from os.path import basename
from os.path import dirname

from mock import patch

from datalad.api import create
from datalad.api import install
from datalad.api import get
from datalad.consts import DATASETS_TOPURL
from datalad.utils import chpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import InstallFailedError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.tests.utils import create_tree
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import assert_in
from datalad.tests.utils import with_tree
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_false
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
        installed = install(tdir, source=url)
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
    assert_raises(InsufficientArgumentsError, install, description="some")
    assert_raises(InsufficientArgumentsError, install, None)
    assert_raises(InsufficientArgumentsError, install, None, description="some")


@with_tempfile(mkdir=True)
def test_invalid_args(path):
    assert_raises(ValueError, install, 'Zoidberg', source='Zoidberg')
    # install to an invalid URL
    assert_raises(ValueError, install, 'ssh://mars:Zoidberg', source='Zoidberg')
    # install to a remote location
    assert_raises(ValueError, install, 'ssh://mars/Zoidberg', source='Zoidberg')
    # make fake dataset
    ds = create(path)
    assert_raises(ValueError, install, '/higherup.', 'Zoidberg', dataset=ds)


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_install_crcns(tdir, ds_path):
    with chpwd(tdir):
        with swallow_logs(new_level=logging.INFO) as cml:
            install("all-nonrecursive", source='///')
            # since we didn't log decorations such as log level atm while
            # swallowing so lets check if exit code is returned or not
            # I will test both
            assert_not_in('ERROR', cml.out)
            # below one must not fail alone! ;)
            assert_not_in('with exit code', cml.out)

        # should not hang in infinite recursion
        with chpwd('all-nonrecursive'):
            get("crcns")
        ok_(exists(_path_("all-nonrecursive/crcns/.git/config")))
        # and we could repeat installation and get the same result
        ds1 = install(_path_("all-nonrecursive/crcns"))
        ds2 = Dataset('all-nonrecursive').install('crcns')
        ok_(ds1.is_installed())
        eq_(ds1, ds2)
        eq_(ds1.path, ds2.path)  # to make sure they are a single dataset

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
            assert_in("was already installed from", cml.out)
            eq_(result, ds)

        # and a third time into an existing something, that is not a dataset:
        with open(opj(tdir, 'sub', 'a_file.txt'), 'w') as f:
            f.write("something")

        with swallow_logs(new_level=logging.WARNING) as cml:
            result = install("sub", source='///')
            assert_in("already exists and is not an installed dataset", cml.out)
            ok_(result is None)


@with_testrepos('.*basic.*', flavors=['local-url', 'network', 'local'])
@with_tempfile(mkdir=True)
def test_install_simple_local(src, path):
    origin = Dataset(path)

    # now install it somewhere else
    ds = install(path, source=src)
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
        uuid_before = ds.repo.uuid

    # installing it again, shouldn't matter:
    with swallow_logs(new_level=logging.INFO) as cml:
        ds = install(path, source=src)
        cml.assert_logged(msg="{0} was already installed from".format(ds),
                          regex=False, level="INFO")
        ok_(ds.is_installed())
        if isinstance(origin.repo, AnnexRepo):
            eq_(uuid_before, ds.repo.uuid)


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
        ds = install(url)

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
        ds = install(path, source='///ds')
    eq_(ds.path, path)
    ok_clean_git(path, annex=False)
    ok_file_has_content(opj(path, 'test.txt'), 'some')


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_install_recursive(src, path_nr, path_r):
    # first install non-recursive:
    ds = install(path_nr, source=src, recursive=False)
    ok_(ds.is_installed())
    for sub in ds.get_subdatasets(recursive=True):
        ok_(not Dataset(opj(path_nr, sub)).is_installed(),
            "Unintentionally installed: %s" % opj(path_nr, sub))
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.get_subdatasets(recursive=True, fulfilled=False)),
        {'subm 1', 'subm 2'})

    # now recursively:
    ds_list = install(path_r, source=src, recursive=True)
    # installed a dataset and two subdatasets
    eq_(len(ds_list), 3)
    eq_(sum([isinstance(i, Dataset) for i in ds_list]), 3)
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
    ds_list = install(path, source=src, recursive=True, get_data=True)
    # installed a dataset and two subdatasets, and two files:
    eq_(len(ds_list), 5)
    eq_(sum([isinstance(i, Dataset) for i in ds_list]), 3)
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
    ok_clean_git(ds.path)

    subds = ds.install("sub", source=source, save=False)
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

    # but we could also save while installing and there should be no side-effect
    # of saving any other changes if we state to not auto-save changes
    # Create a dummy change
    create_tree(ds.path, {'dummy.txt': 'buga'})
    ok_clean_git(ds.path, untracked=['dummy.txt'])
    subds_ = ds.install("sub2", source=source, if_dirty='ignore')
    eq_(subds_.path, opj(ds.path, "sub2"))  # for paranoid yoh ;)
    ok_clean_git(ds.path, untracked=['dummy.txt'])

    # and we should achieve the same behavior if we create a dataset
    # and then decide to "add" it
    create(_path_(top_path, 'sub3'), if_dirty='ignore')
    ok_clean_git(ds.path, untracked=['dummy.txt', 'sub3/'])
    ds.install('sub3', if_dirty='ignore')
    ok_clean_git(ds.path, untracked=['dummy.txt'])


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile
def test_failed_install_multiple(top_path):
    ds = create(top_path)

    create(_path_(top_path, 'ds1'))
    create(_path_(top_path, 'ds3'))
    ok_clean_git(ds.path, annex=False, untracked=['ds1/', 'ds3/'])

    # specify install with multiple paths and one non-existing
    with assert_raises(IncompleteResultsError) as cme:
        ds.install(['ds1', 'ds2', '///crcns', '///nonexisting', 'ds3'])

    ok_clean_git(ds.path, annex=False)
    # those which succeeded should be saved now
    eq_(ds.get_subdatasets(), ['crcns', 'ds1', 'ds3'])
    # and those which didn't -- listed
    eq_(set(cme.exception.failed), {'///nonexisting', _path_(top_path, 'ds2')})

    # but if there was only a single installation requested -- it will be
    # InstallFailedError to stay consistent with single install behavior
    # TODO: unify at some point
    with assert_raises(InstallFailedError) as cme:
        ds.install('ds2')
    with assert_raises(InstallFailedError) as cme:
        ds.install('///nonexisting')


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_known_subdataset(src, path):

    # get the superdataset:
    ds = install(path, source=src)

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

    # now, get the data by reinstalling with -g:
    ok_(subds.repo.file_has_content('test-annex.dat') is False)
    with chpwd(ds.path):
        result = get(path='subm 1', dataset=os.curdir)
        eq_(len(result), 1)
        eq_(result[0]['file'], opj('subm 1', 'test-annex.dat'))
        ok_(subds.repo.file_has_content('test-annex.dat') is True)
        ok_(subds.is_installed())


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
    ds = install(dst, source=src)
    ok_(ds.is_installed())

    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # fail on obscure non-existing one
    assert_raises(InstallFailedError, ds.install, source='obscure')

    # install 3rd level and therefore implicitly the 2nd:
    result = ds.install(path=opj("sub", "subsub"))
    ok_(sub.is_installed())
    ok_(subsub.is_installed())
    eq_(result, subsub)

    # fail on obscure non-existing one in subds
    assert_raises(InstallFailedError, ds.install, source=opj('sub', 'obscure'))

    # clean up:
    rmtree(dst, chmod_files=True)
    ok_(not exists(dst))

    # again first toplevel:
    ds = install(dst, source=src)
    ok_(ds.is_installed())
    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # now implicit but without an explicit dataset to install into
    # (deriving from CWD):
    with chpwd(dst):
        result = get(path=opj("sub", "subsub"))
        ok_(sub.is_installed())
        ok_(subsub.is_installed())
        eq_(result, [subsub])


@with_tempfile(mkdir=True)
def test_failed_install(dspath):
    ds = create(dspath)
    assert_raises(InstallFailedError,
                  ds.install,
                  "sub",
                  source="http://nonexistingreallyanything.somewhere/bla")


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_list(path, top_path):

    # we want to be able to install several things, if these are known
    # (no 'source' allowed). Therefore first toplevel:
    ds = install(top_path, source=path, recursive=False)
    assert_not_in('annex.hardlink', ds.config)
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
    # and if we request it again via get, result should be empty
    get_result = ds.get(path=['subm 1', 'subm 2'], get_data=False)
    eq_(get_result, [])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_reckless(path, top_path):
    ds = install(top_path, source=path, reckless=True)
    eq_(ds.config.get('annex.hardlink', None), 'true')
    eq_(ds.repo.repo_info()['untrusted repositories'][0]['here'], True)


@with_tree(tree={'top_file.txt': 'some',
                 'sub 1': {'sub1file.txt': 'something else',
                           'subsub': {'subsubfile.txt': 'completely different',
                                      }
                           },
                 'sub 2': {'sub2file.txt': 'meaningless',
                           }
                 })
@with_tempfile(mkdir=True)
def test_install_recursive_repeat(src, path):
    subsub_src = Dataset(opj(src, 'sub 1', 'subsub')).create(force=True)
    sub1_src = Dataset(opj(src, 'sub 1')).create(force=True)
    sub2_src = Dataset(opj(src, 'sub 2')).create(force=True)
    top_src = Dataset(src).create(force=True)
    top_src.save(auto_add_changes=True, recursive=True)

    # install top level:
    top_ds = install(path, source=src)
    ok_(top_ds.is_installed() is True)
    sub1 = Dataset(opj(path, 'sub 1'))
    ok_(sub1.is_installed() is False)
    sub2 = Dataset(opj(path, 'sub 2'))
    ok_(sub2.is_installed() is False)
    subsub = Dataset(opj(path, 'sub 1', 'subsub'))
    ok_(subsub.is_installed() is False)

    # install again, now with data and recursive, but recursion_limit 1:
    result = get(os.curdir, dataset=path, recursive=True, recursion_limit=1)
    # top-level dataset was not reobtained
    assert_not_in(top_ds, result)
    assert_in(sub1, result)
    assert_in(sub2, result)
    assert_not_in(subsub, result)
    ok_(top_ds.repo.file_has_content('top_file.txt') is True)
    ok_(sub1.repo.file_has_content('sub1file.txt') is True)
    ok_(sub2.repo.file_has_content('sub2file.txt') is True)

    # install sub1 again, recursively and with data
    top_ds.install('sub 1', recursive=True, get_data=True)
    ok_(subsub.is_installed())
    ok_(subsub.repo.file_has_content('subsubfile.txt'))


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile
def test_install_skip_list_arguments(src, path, path_outside):
    ds = install(path, source=src)
    ok_(ds.is_installed())

    # install a list with valid and invalid items:
    with swallow_logs(new_level=logging.WARNING) as cml:
        with assert_raises(IncompleteResultsError) as cme:
            ds.install(
                path=['subm 1', 'not_existing', path_outside, 'subm 2'],
                get_data=False)
        result = cme.exception.results
        for skipped in [opj(ds.path, 'not_existing'), path_outside]:
            cml.assert_logged(msg="ignored non-existing paths: {}\n".format(
                              [opj(ds.path, 'not_existing'), path_outside]),
                              regex=False, level='WARNING')
            pass
        ok_(isinstance(result, list))
        eq_(len(result), 2)
        for sub in [Dataset(opj(path, 'subm 1')), Dataset(opj(path, 'subm 2'))]:
            assert_in(sub, result)
            ok_(sub.is_installed())

    # return of get is always a list, even if just one thing was gotten
    # in this case 'subm1' was already obtained above, so this will get this
    # content of the subdataset
    with assert_raises(IncompleteResultsError) as cme:
        ds.install(path=['subm 1', 'not_existing'])
    with assert_raises(IncompleteResultsError) as cme:
        ds.get(path=['subm 1', 'not_existing'])
    result = cme.exception.results
    eq_(len(result), 1)
    eq_(result[0]['file'], 'subm 1/test-annex.dat')


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_skip_failed_recursive(src, path):

    # install top level:
    ds = install(path, source=src)
    sub1 = Dataset(opj(path, 'subm 1'))
    sub2 = Dataset(opj(path, 'subm 2'))
    # sabotage recursive installation of 'subm 1' by polluting the target:
    with open(opj(path, 'subm 1', 'blocking.txt'), "w") as f:
        f.write("sdfdsf")

    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(os.curdir, recursive=True)
        # toplevel dataset was in the house already
        assert_not_in(ds, result)
        assert_in(sub2, result)
        assert_not_in(sub1, result)
        cml.assert_logged(
            msg="Target {} already exists and is not an installed dataset. Skipped.".format(sub1.path),
            regex=False, level='WARNING')


@with_tree(tree={'top_file.txt': 'some',
                 'sub 1': {'sub1file.txt': 'something else',
                           'subsub': {'subsubfile.txt': 'completely different',
                                      }
                           },
                 'sub 2': {'sub2file.txt': 'meaningless',
                           }
                 })
@with_tempfile(mkdir=True)
def test_install_noautoget_data(src, path):
    subsub_src = Dataset(opj(src, 'sub 1', 'subsub')).create(force=True)
    sub1_src = Dataset(opj(src, 'sub 1')).create(force=True)
    sub2_src = Dataset(opj(src, 'sub 2')).create(force=True)
    top_src = Dataset(src).create(force=True)
    top_src.save(auto_add_changes=True, recursive=True)

    # install top level:
    cdss = install(path, source=src, recursive=True)
    # there should only be datasets in the list of installed items,
    # and none of those should have any data for their annexed files yet
    for ds in cdss:
        assert_false(any(ds.repo.file_has_content(ds.repo.get_annexed_files())))


@with_tempfile
@with_tempfile
def test_install_source_relpath(src, dest):
    ds1 = create(src)
    src_ = basename(src)
    with chpwd(dirname(src)):
        ds2 = install(dest, source=src_)