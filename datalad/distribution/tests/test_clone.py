# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test clone action

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
from datalad.api import clone
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
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_message
from datalad.tests.utils import assert_in_results
from datalad.tests.utils import assert_not_in_results
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import use_cassette
from datalad.tests.utils import skip_if_no_network
from datalad.utils import _path_
from datalad.utils import rmtree

from ..dataset import Dataset
from ..utils import _get_installationpath_from_url
from ..utils import _get_git_url_from_source


@with_tempfile(mkdir=True)
def test_invalid_args(path):
    assert_raises(ValueError, clone, 'Zoidberg', path='Zoidberg')
    # install to an invalid URL
    assert_raises(ValueError, clone, 'Zoidberg', path='ssh://mars:Zoidberg')
    # install to a remote location
    assert_raises(ValueError, clone, 'Zoidberg', path='ssh://mars/Zoidberg')
    # make fake dataset
    ds = create(path)
    assert_raises(IncompleteResultsError, ds.clone, '/higherup.', 'Zoidberg')


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_crcns(tdir, ds_path):
    with chpwd(tdir):
        res = clone('///', path="all-nonrecursive", on_failure='ignore')
        assert_status('ok', res)

    # again, but into existing dataset:
    ds = create(ds_path)
    crcns = ds.clone("///crcns", result_xfm='datasets', return_type='item-or-list')
    ok_(crcns.is_installed())
    eq_(crcns.path, opj(ds_path, "crcns"))
    assert_in(crcns.path, ds.get_subdatasets(absolute=True))


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tree(tree={'sub': {}})
def test_clone_datasets_root(tdir):
    with chpwd(tdir):
        ds = clone("///", result_xfm='datasets', return_type='item-or-list')
        ok_(ds.is_installed())
        eq_(ds.path, opj(tdir, 'datasets.datalad.org'))

        # do it a second time:
        res = clone("///", on_failure='ignore')
        assert_message(
            "dataset %s was already cloned from '%s'",
            res)
        assert_status('notneeded', res)

        # and a third time into an existing something, that is not a dataset:
        with open(opj(tdir, 'sub', 'a_file.txt'), 'w') as f:
            f.write("something")

        res = clone('///', path="sub", on_failure='ignore')
        assert_message(
            'target path already exists and not empty, refuse to clone into target path',
            res)
        assert_status('error', res)


@with_testrepos('.*basic.*', flavors=['local-url', 'network', 'local'])
@with_tempfile(mkdir=True)
def test_clone_simple_local(src, path):
    origin = Dataset(path)

    # now install it somewhere else
    ds = clone(src, path, result_xfm='datasets', return_type='item-or-list')
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
    res = clone(src, path)
    assert_status('notneeded', res)
    assert_message("dataset %s was already cloned from '%s'", res)
    ok_(ds.is_installed())
    if isinstance(origin.repo, AnnexRepo):
        eq_(uuid_before, ds.repo.uuid)


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_clone_dataset_from_just_source(url, path):
    with chpwd(path, mkdir=True):
        ds = clone(url, result_xfm='datasets', return_type='item-or-list')

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    ok_clean_git(ds.path, annex=None)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_clone_dataladri(src, topurl, path):
    # make plain git repo
    ds_path = opj(src, 'ds')
    gr = GitRepo(ds_path, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    Runner(cwd=gr.path)(['git', 'update-server-info'])
    # now install it somewhere else
    with patch('datalad.support.network.DATASETS_TOPURL', topurl):
        ds = clone('///ds', path, result_xfm='datasets', return_type='item-or-list')
    eq_(ds.path, path)
    ok_clean_git(path, annex=False)
    ok_file_has_content(opj(path, 'test.txt'), 'some')


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_recursive(src, path_nr, path_r):
    # first clone non-recursive:
    ds = clone(src, path_nr, recursive=False,
               result_xfm='datasets', return_type='item-or-list')
    ok_(ds.is_installed())
    for sub in ds.get_subdatasets(recursive=True):
        ok_(not Dataset(opj(path_nr, sub)).is_installed(),
            "Unintentionally installed: %s" % opj(path_nr, sub))
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.get_subdatasets(recursive=True, fulfilled=False)),
        {'subm 1', 'subm 2'})

    # now recursively:
    ds_list = clone(src, path_r, recursive=True, result_xfm='datasets')
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


@with_testrepos(flavors=['local'])
# 'local-url', 'network'
# TODO: Somehow annex gets confused while initializing installed ds, whose
# .git/config show a submodule url "file:///aaa/bbb%20b/..."
# this is delivered by with_testrepos as the url to clone
@with_tempfile
def test_clone_into_dataset(source, top_path):

    ds = create(top_path)
    ok_clean_git(ds.path)

    subds = ds.clone(source, "sub",
                     result_xfm='datasets', return_type='item-or-list')
    if isinstance(subds.repo, AnnexRepo) and subds.repo.is_direct_mode():
        ok_(exists(opj(subds.path, '.git')))
    else:
        ok_(isdir(opj(subds.path, '.git')))
    ok_(subds.is_installed())
    assert_in('sub', ds.get_subdatasets())
    # sub is clean:
    ok_clean_git(subds.path, annex=None)
    # top is clean:
    ok_clean_git(ds.path, annex=None)

    # but we could also save while installing and there should be no side-effect
    # of saving any other changes if we state to not auto-save changes
    # Create a dummy change
    create_tree(ds.path, {'dummy.txt': 'buga'})
    ok_clean_git(ds.path, untracked=['dummy.txt'])
    subds_ = ds.clone(source, "sub2",
                      result_xfm='datasets', return_type='item-or-list')
    eq_(subds_.path, opj(ds.path, "sub2"))  # for paranoid yoh ;)
    ok_clean_git(ds.path, untracked=['dummy.txt'])


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_notclone_known_subdataset(src, path):
    # get the superdataset:
    ds = clone(src, path,
               result_xfm='datasets', return_type='item-or-list')

    # subdataset not installed:
    subds = Dataset(opj(path, 'subm 1'))
    assert_false(subds.is_installed())
    assert_in('subm 1', ds.get_subdatasets(fulfilled=False))
    assert_not_in('subm 1', ds.get_subdatasets(fulfilled=True))
    # clone is not meaningful
    res = ds.clone('subm 1', on_failure='ignore')
    assert_status('error', res)
    assert_message('Failed to clone data from any candidate source URL: %s',
                   res)
    # get does the job
    res = ds.get(path='subm 1', get_data=False)
    assert_status('ok', res)
    ok_(subds.is_installed())
    ok_(AnnexRepo.is_valid_repo(subds.path, allow_noninitialized=False))
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    eq_(set(subds.repo.get_indexed_files()),
        {'test.dat', 'INFO.txt', 'test-annex.dat'})
    assert_not_in('subm 1', ds.get_subdatasets(fulfilled=False))
    assert_in('subm 1', ds.get_subdatasets(fulfilled=True))


@with_tempfile(mkdir=True)
def test_failed_clone(dspath):
    ds = create(dspath)
    res = ds.clone("http://nonexistingreallyanything.somewhere/bla", "sub",
                   on_failure='ignore')
    assert_status('error', res)
    assert_message('Failed to clone data from any candidate source URL: %s',
                   res)


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_reckless(path, top_path):
    ds = clone(path, top_path, reckless=True,
               result_xfm='datasets', return_type='item-or-list')
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
def test_clone_noautoget_data(src, path):
    subsub_src = Dataset(opj(src, 'sub 1', 'subsub')).create(force=True)
    sub1_src = Dataset(opj(src, 'sub 1')).create(force=True)
    Dataset(opj(src, 'sub 2')).create(force=True)
    top_src = Dataset(src).create(force=True)
    top_src.add('.', recursive=True)

    # install top level:
    cdss = clone(src, path, recursive=True,
                 result_xfm='datasets', return_type='item-or-list')
    # there should only be datasets in the list of installed items,
    # and none of those should have any data for their annexed files yet
    for ds in cdss:
        assert_false(any(ds.repo.file_has_content(ds.repo.get_annexed_files())))


@with_tempfile
@with_tempfile
def test_install_source_relpath(src, dest):
    create(src)
    src_ = basename(src)
    with chpwd(dirname(src)):
        clone(src_, dest)
