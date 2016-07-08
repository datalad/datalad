# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test install action

"""

import os
import shutil
from os.path import join as opj, abspath, isdir
from os.path import exists
from os.path import realpath

from mock import patch

from ..dataset import Dataset
from datalad.api import create
from datalad.api import install
from datalad.consts import DATASETS_TOPURL
from datalad.distribution.install import get_containing_subdataset
from datalad.distribution.install import _get_installationpath_from_url
from datalad.distribution.install import _get_git_url_from_source
from datalad.utils import chpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileInGitError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.cmd import Runner

from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner

from nose.tools import ok_, eq_, assert_false
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_equal, assert_true
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import swallow_logs


def test_insufficient_args():
    assert_raises(InsufficientArgumentsError, install)


def test_installationpath_from_url():
    for p in ('lastbit',
              'lastbit/',
              '/lastbit',
              'lastbit.git',
              'lastbit.git/',
              'http://example.com/lastbit',
              'http://example.com/lastbit.git',
              ):
        assert_equal(_get_installationpath_from_url(p), 'lastbit')


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


@with_tree(tree={'test.txt': 'whatever'})
def test_get_containing_subdataset(path):

    ds = create(path, force=True)
    ds.install(path='test.txt')
    ds.save("Initial commit")
    subds = ds.install("sub", source=path)
    eq_(get_containing_subdataset(ds, opj("sub", "some")).path, subds.path)
    eq_(get_containing_subdataset(ds, "some").path, ds.path)
    # make sure the subds is found, even when it is not present, but still
    # known
    shutil.rmtree(subds.path)
    eq_(get_containing_subdataset(ds, opj("sub", "some")).path, subds.path)

    outside_path = opj(os.pardir, "somewhere", "else")
    assert_raises(ValueError, get_containing_subdataset, ds, outside_path)
    assert_raises(ValueError, get_containing_subdataset, ds,
                  opj(os.curdir, outside_path))
    assert_raises(ValueError, get_containing_subdataset, ds,
                  abspath(outside_path))


@with_tree(tree={'test.txt': 'some', 'test2.txt': 'other'})
@with_tempfile(mkdir=True)
def test_install_plain_git(src, path):
    # make plain git repo
    gr = GitRepo(src, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    # now install it somewhere else
    ds = install(path=path, source=src)
    # stays plain Git repo
    ok_(isinstance(ds.repo, GitRepo))
    # now go back to original
    ds = Dataset(src)
    ok_(isinstance(ds.repo, GitRepo))
    # installing a file must fail, as we decided not to perform magical upgrades
    # GitRepo -> AnnexRepo
    assert_raises(RuntimeError, ds.install, path='test2.txt', source=opj(src, 'test2.txt'))
    # but works when forced
    ifiles = ds.install(path='test2.txt', source=opj(src, 'test2.txt'), add_data_to_git=True)
    ok_startswith(ifiles, ds.path)
    ok_(ifiles.endswith('test2.txt'))
    ok_('test2.txt' in ds.repo.get_indexed_files())


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_dataset_from(url, path):
    ds = install(path=path, source=url)
    eq_(ds.path, path)
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_dataset_from_just_source(url, path):

    with chpwd(path, mkdir=True):
        ds = install(source=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=False)


@with_testrepos(flavors=['network'])
@with_tempfile
def test_install_dataset_from_just_source_via_path(url, path):
    # for remote urls only, the source could be given to `path`
    # to allows for simplistic cmdline calls

    with chpwd(path, mkdir=True):
        ds = install(path=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_clean_git(ds.path, annex=False)
    assert_true(os.path.lexists(opj(ds.path, 'test-annex.dat')))


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


def test_install_list():
    raise SkipTest("TODO")


def test_install_missing_arguments():
    raise SkipTest("TODO")


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_recursive(src, path):
    ds = install(path=path, source=src, recursive=True)
    ok_(ds.is_installed())
    for sub in ds.get_subdatasets(recursive=True):
        ok_(Dataset(opj(path, sub)).is_installed(), "Not installed: %s" % opj(path, sub))


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_recursive_with_data(src, path):

    # now again; with data:
    ds = install(path=path, source=src, recursive='data')
    ok_(ds.is_installed())
    if isinstance(ds.repo, AnnexRepo):
        ok_(all(ds.repo.file_has_content(ds.repo.get_annexed_files())))
    for sub in ds.get_subdatasets(recursive=True):
        subds = Dataset(opj(path, sub))
        ok_(subds.is_installed(), "Not installed: %s" % opj(path, sub))
        if isinstance(subds.repo, AnnexRepo):
            ok_(all(subds.repo.file_has_content(subds.repo.get_annexed_files())))


# TODO: Is there a way to test result renderer?
#  MIH: cmdline tests have run_main() which capture the output.


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
