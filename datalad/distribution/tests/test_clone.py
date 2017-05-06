# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test clone action

"""


from os.path import join as opj
from os.path import isdir
from os.path import exists
from os.path import basename
from os.path import dirname

from mock import patch

from datalad.api import create
from datalad.api import clone
from datalad.utils import chpwd
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.gitrepo import GitRepo
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
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_result_values_equal
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import use_cassette
from datalad.tests.utils import skip_if_no_network

from ..dataset import Dataset


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_invalid_args(path, otherpath, alienpath):
    assert_raises(ValueError, clone, 'Zoidberg', path='Zoidberg')
    # install to an invalid URL
    assert_raises(ValueError, clone, 'Zoidberg', path='ssh://mars:Zoidberg')
    # install to a remote location
    assert_raises(ValueError, clone, 'Zoidberg', path='ssh://mars/Zoidberg')
    # make fake dataset
    ds = create(path)
    assert_raises(IncompleteResultsError, ds.clone, '/higherup.', 'Zoidberg')
    # make real dataset, try to install outside
    ds_target = create(opj(otherpath, 'target'))
    assert_raises(ValueError, ds_target.clone, ds.path, path=ds.path)
    assert_status('error', ds_target.clone(ds.path, path=alienpath, on_failure='ignore'))


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
    assert_in(crcns.path, ds.subdatasets(result_xfm='paths'))


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
    ds = clone(src, path, description='mydummy',
               result_xfm='datasets', return_type='item-or-list')
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
        eq_(ds.repo.get_description(), 'mydummy')

    # installing it again, shouldn't matter:
    res = clone(src, path)
    assert_result_values_equal(res, 'source_url', [src])
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
def test_clone_isnot_recursive(src, path_nr, path_r):
    ds = clone(src, path_nr, result_xfm='datasets', return_type='item-or-list')
    ok_(ds.is_installed())
    # check nothin is unintentionally installed
    subdss = ds.subdatasets(recursive=True)
    assert_result_count(subdss, len(subdss), state='absent')
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.subdatasets(recursive=True, fulfilled=False, result_xfm='relpaths')),
        {'subm 1', 'subm 2'})


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
    assert_in('sub', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))
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
    assert_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_not_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))
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
    assert_not_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))


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


@with_tempfile
@with_tempfile
def test_install_source_relpath(src, dest):
    create(src)
    src_ = basename(src)
    with chpwd(dirname(src)):
        clone(src_, dest)


@with_tempfile
@with_tempfile
def test_clone_isnt_a_smartass(origin_path, path):
    origin = create(origin_path)
    cloned = clone(origin, path,
                   result_xfm='datasets', return_type='item-or-list')
    with chpwd(path):
        # no were are inside a dataset clone, and we make another one
        # we do not want automatic subdatasetification without given a dataset
        # explicitely
        clonedsub = clone(origin, 'testsub',
                          result_xfm='datasets', return_type='item-or-list')
    # correct destination
    assert clonedsub.path.startswith(path)
    # no subdataset relation
    eq_(cloned.subdatasets(), [])
