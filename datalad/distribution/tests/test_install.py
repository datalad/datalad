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

from ..dataset import Dataset
from datalad.api import create
from datalad.api import install
from datalad.distribution.install import get_containing_subdataset
from datalad.distribution.install import _installationpath_from_url
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
        assert_equal(_installationpath_from_url(p), 'lastbit')


@with_tree(tree={'test.txt': 'whatever'})
def test_get_containing_subdataset(path):

    ds = create(path)
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


@with_tempfile
def test_create(path):
    # install doesn't create anymore
    assert_raises(RuntimeError, Dataset(path).install)
    # only needs a path
    ds = create(path, no_annex=True)
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)
    ok_(isinstance(ds.repo, GitRepo))

    ds = create(path, description="funny")
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)
    # any dataset created from scratch has an annex
    ok_(isinstance(ds.repo, AnnexRepo))
    # check default backend
    assert_equal(
        ds.repo.repo.config_reader().get_value("annex", "backends"),
        'MD5E')
    runner = Runner()
    # check description in `info`
    cmd = ['git-annex', 'info']
    cmlout = runner.run(cmd, cwd=path)
    assert_in('funny [here]', cmlout[0])


    sub_path_1 = opj(path, "sub")
    subds1 = create(sub_path_1)
    ok_(subds1.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    # wasn't installed into ds:
    assert_not_in("sub", ds.get_dataset_handles())

    # add it inplace:
    added_subds = ds.install("sub", source=sub_path_1)
    ok_(added_subds.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    eq_(added_subds.path, sub_path_1)
    assert_true(isdir(opj(added_subds.path, '.git')))
    # will not list it unless committed
    assert_not_in("sub", ds.get_dataset_handles())
    ds.save("added submodule")
    # will still not list it, because without a single commit, it doesn't enter
    # the index
    assert_not_in("sub", ds.get_dataset_handles())
    # now for reals
    open(opj(added_subds.path, 'somecontent'), 'w').write('stupid')
    # next one will auto-annex the new file
    added_subds.save('initial commit')
    # as the submodule never entered the index, even this one won't work
    # ben: it currently does, since 'save' was changed to call git add as well
    # as git annex add. Therefore outcommenting. Please review, whether this is
    # intended behaviour. I think so.
    ds.save('submodule with content')
    # assert_not_in("sub", ds.get_dataset_handles())
    # # we need to install the submodule again in the parent
    # # an actual final commit is not required
    # added_subds = ds.install("sub", source=sub_path_1)
    assert_in("sub", ds.get_dataset_handles())

    # next one directly created within ds:
    sub_path_2 = opj(path, "sub2")
    # installing something without a source into a dataset at a path
    # that has no present content should not work
    assert_raises(InsufficientArgumentsError, install, ds, path=sub_path_2)


@with_tempfile
def test_create_curdir(path):
    with chpwd(path, mkdir=True):
        create()
    ok_(Dataset(path).is_installed())


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


@with_tree(tree={'test.txt': 'some',
                 'dir': {'testindir': 'someother',
                         'testindir2': 'none'}})
def test_install_files(path):
    ds = create(path)
    # install a single file
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install it again, should given same result
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install multiple files in a dir
    eq_(ds.install('dir', recursive=True),
        [opj(path, 'dir', 'testindir'),
         opj(path, 'dir', 'testindir2')])
    # TODO: check git


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

@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_into_dataset(source, top_path):
    ds = create(top_path)
    subds = ds.install(path="sub", source=source)
    assert_true(isdir(opj(subds.path, '.git')))
    ok_(subds.is_installed())
    # sub is clean:
    ok_clean_git(subds.path, annex=False)
    # top is not:
    assert_raises(AssertionError, ok_clean_git, ds.path, annex=False)
    # unless committed the subds should not show up in the parent
    # this is the same behavior that 'git submodule status' implements
    assert_not_in('sub', ds.get_dataset_handles())
    ds.save('addsub')
    assert_in('sub', ds.get_dataset_handles())


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_subdataset(src, path):
    # get the superdataset:
    ds = install(path=path, source=src)

    # subdataset not installed:
    subds = Dataset(opj(path, 'sub1'))
    assert_false(subds.is_installed())

    # install it:
    ds.install('sub1')
    assert_true(isdir(opj(subds.path, '.git')))

    ok_(subds.is_installed())
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    assert_equal(set(subds.repo.get_indexed_files()),
                 {'test.dat', 'INFO.txt', 'test-annex.dat'})

    # Now the obnoxious install an annex file within not yet
    # initialized repository!
    with swallow_outputs():  # progress bar
        ds.install(opj('sub2', 'test-annex.dat'))
    subds2 = Dataset(opj(path, 'sub2'))
    assert(subds2.is_installed())
    assert(subds2.repo.file_has_content('test-annex.dat'))
    # we shouldn't be able silently ignore attempt to provide source while
    # "installing" file under git
    assert_raises(FileInGitError, ds.install, opj('sub2', 'INFO.txt'), source="http://bogusbogus")


def test_install_list():
    raise SkipTest("TODO")


def test_install_missing_arguments():
    raise SkipTest("TODO")


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_recursive(src, path):
    ds = install(path=path, source=src, recursive=True)
    ok_(ds.is_installed())
    for sub in ds.get_dataset_handles(recursive=True):
        ok_(Dataset(opj(path, sub)).is_installed(), "Not installed: %s" % opj(path, sub))

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