# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test clone action

"""

import logging
import os.path as op
import stat
from unittest.mock import patch

import pytest

from datalad import consts
from datalad.api import (
    clone,
    create,
    remove,
)
from datalad.cmd import GitWitlessRunner
from datalad.cmd import WitlessRunner as Runner
from datalad.config import ConfigManager
from datalad.core.distributed.clone import (
    _get_installationpath_from_url,
    decode_source_spec,
)
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import GitRepo
from datalad.support.network import get_local_file_url
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_false,
    assert_in,
    assert_in_results,
    assert_message,
    assert_not_in,
    assert_not_is_instance,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_result_values_equal,
    assert_status,
    create_tree,
    eq_,
    get_datasets_topdir,
    has_symlink_capability,
    integration,
    known_failure,
    known_failure_githubci_win,
    known_failure_osx,
    known_failure_windows,
    neq_,
    nok_,
    ok_,
    ok_file_has_content,
    ok_startswith,
    patch_config,
    serve_path_via_http,
    set_date,
    skip_if_adjusted_branch,
    skip_if_no_network,
    skip_if_on_windows,
    skip_ssh,
    slow,
    swallow_logs,
    with_sameas_remote,
    with_tempfile,
    with_tree,
)
from datalad.utils import (
    Path,
    chpwd,
    get_home_envvars,
    on_windows,
    rmtree,
)

# this is the dataset ID of our test dataset in the main datalad RIA store
datalad_store_testds_id = '76b6ca66-36b1-11ea-a2e6-f0d5bf7b5561'


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_invalid_args(path=None, otherpath=None, alienpath=None):
    # source == path
    assert_raises(ValueError, clone, 'Zoidberg', path='Zoidberg')
    assert_raises(ValueError, clone, 'ssh://mars/Zoidberg', path='ssh://mars/Zoidberg')

    # "invalid URL" is a valid filepath... and since no clone to remote
    # is possible - we can just assume that it is the (legit) file path
    # which is provided, not a URL.  So both below should fail as any
    # other clone from a non-existing source and not for the reason of
    # "invalid something".  Behavior is similar to how Git performs - can
    # clone into a URL-like path.

    # install to an "invalid URL" path
    res = clone('Zoidberg', path='ssh://mars:Zoidberg', on_failure='ignore',
                result_xfm=None)
    assert_status('error', res)

    # install to a "remote location" path
    res = clone('Zoidberg', path='ssh://mars/Zoidberg', on_failure='ignore',
                result_xfm=None)
    assert_status('error', res)

    # make fake dataset
    ds = create(path)
    assert_raises(IncompleteResultsError, ds.clone, '/higherup.', 'Zoidberg')
    # make real dataset, try to install outside
    ds_target = create(Path(otherpath) / 'target')
    assert_raises(ValueError, ds_target.clone, ds.path, path=ds.path)
    assert_status('error', ds_target.clone(ds.path, path=alienpath,
                                           on_failure='ignore', result_xfm=None))


@integration
@skip_if_no_network
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_crcns(tdir=None, ds_path=None):
    with chpwd(tdir):
        res = clone('///', path="all-nonrecursive", on_failure='ignore',
                    result_xfm=None, return_type='list')
        assert_status('ok', res)

    # again, but into existing dataset:
    ds = create(ds_path)
    crcns = ds.clone("///crcns", result_xfm='datasets', return_type='item-or-list')
    ok_(crcns.is_installed())
    eq_(crcns.pathobj, ds.pathobj / "crcns")
    assert_in(crcns.path, ds.subdatasets(result_xfm='paths'))


@integration
@skip_if_no_network
@with_tree(tree={'sub': {}})
def test_clone_datasets_root(tdir=None):
    tdir = Path(tdir)
    with chpwd(tdir):
        ds = clone("///")
        ok_(ds.is_installed())
        eq_(ds.pathobj, tdir / get_datasets_topdir())

        # do it a second time:
        res = clone("///", on_failure='ignore', result_xfm=None, return_type='list')
        assert_message(
            "dataset %s was already cloned from '%s'",
            res)
        assert_status('notneeded', res)

        # and a third time into an existing something, that is not a dataset:
        (tdir / 'sub' / 'a_file.txt').write_text("something")

        res = clone('///', path="sub", on_failure='ignore', result_xfm=None)
        assert_message(
            'target path already exists and not empty, refuse to clone into target path',
            res)
        assert_status('error', res)


@with_tempfile(mkdir=True)
def check_clone_simple_local(src, path):
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
            {'test.dat', 'INFO.txt', '.noannex',
             str(Path('.datalad', 'config'))})
        assert_repo_status(path, annex=False)
    else:
        # must be an annex
        ok_(isinstance(ds.repo, AnnexRepo))
        ok_(AnnexRepo.is_valid_repo(ds.path, allow_noninitialized=False))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat',
             'INFO.txt',
             'test-annex.dat',
             str(Path('.datalad', 'config')),
             str(Path('.datalad', '.gitattributes')),
             '.gitattributes'})
        assert_repo_status(path, annex=True)
        # no content was installed:
        ok_(not ds.repo.file_has_content('test-annex.dat'))
        uuid_before = ds.repo.uuid
        ok_(uuid_before)  # make sure we actually have an uuid
        eq_(ds.repo.get_description(), 'mydummy')

    # installing it again, shouldn't matter:
    res = clone(src, path, result_xfm=None, return_type='list')
    assert_result_values_equal(res, 'source_url', [src])
    assert_status('notneeded', res)
    assert_message("dataset %s was already cloned from '%s'", res)
    ok_(ds.is_installed())
    if isinstance(origin.repo, AnnexRepo):
        eq_(uuid_before, ds.repo.uuid)


@with_tempfile(mkdir=True)
@serve_path_via_http
def test_clone_simple_local(src=None, url=None):
    srcobj = Path(src)
    gitds = Dataset(srcobj / 'git').create(annex=False)
    annexds = Dataset(srcobj/ 'annex').create(annex=True)
    (annexds.pathobj / "test-annex.dat").write_text('annexed content')
    annexds.save()
    for ds in (gitds, annexds):
        (ds.pathobj / 'test.dat').write_text('content')
        (ds.pathobj / 'INFO.txt').write_text('content2')
        ds.save(to_git=True)
        ds.repo.call_git(["update-server-info"])
    check_clone_simple_local(gitds.path)
    check_clone_simple_local(gitds.pathobj)
    check_clone_simple_local(f'{url}git')
    check_clone_simple_local(annexds.path)
    check_clone_simple_local(annexds.pathobj)
    check_clone_simple_local(f'{url}annex')


@with_tempfile
def check_clone_dataset_from_just_source(url, path):
    with chpwd(path, mkdir=True):
        ds = clone(url, result_xfm='datasets', return_type='item-or-list')

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    assert_repo_status(ds.path, annex=None)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@with_tempfile(mkdir=True)
@serve_path_via_http
def test_clone_dataset_from_just_source(src=None, url=None):
    ds = Dataset(src).create()
    (ds.pathobj / 'INFO.txt').write_text('content')
    ds.save()
    ds.repo.call_git(["update-server-info"])
    check_clone_dataset_from_just_source(ds.path)
    check_clone_dataset_from_just_source(ds.pathobj)
    check_clone_dataset_from_just_source(url)


# test fails randomly, likely a bug in one of the employed test helpers
# https://github.com/datalad/datalad/pull/3966#issuecomment-571267932
@known_failure
@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_clone_dataladri(src=None, topurl=None, path=None):
    # make plain git repo
    ds_path = Path(src) / 'ds'
    gr = GitRepo(ds_path, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    Runner(cwd=gr.path).run(['git', 'update-server-info'])
    # now install it somewhere else
    with patch('datalad.consts.DATASETS_TOPURL', topurl):
        ds = clone('///ds', path, result_xfm='datasets', return_type='item-or-list')
    eq_(ds.path, path)
    assert_repo_status(path, annex=False)
    ok_file_has_content(ds.pathobj / 'test.txt', 'some')


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_isnot_recursive(path_src=None, path_nr=None, path_r=None):
    src = Dataset(path_src).create()
    src.create('subm 1')
    src.create('2')

    ds = clone(src, path_nr, result_xfm='datasets', return_type='item-or-list')
    ok_(ds.is_installed())
    # check nothing is unintentionally installed
    subdss = ds.subdatasets(recursive=True)
    assert_result_count(subdss, len(subdss), state='absent')
    # this also means, subdatasets to be listed as absent:
    eq_(set(ds.subdatasets(recursive=True, state='absent', result_xfm='relpaths')),
        {'subm 1', '2'})


@with_tempfile
@with_tempfile
def test_clone_into_dataset(source_path=None, top_path=None):
    source = Dataset(source_path).create()
    ds = create(top_path)
    assert_repo_status(ds.path)
    # Note, we test against the produced history in DEFAULT_BRANCH, not what it
    # turns into in an adjusted branch!
    hexsha_before = ds.repo.get_hexsha(DEFAULT_BRANCH)
    subds = ds.clone(source, "sub",
                     result_xfm='datasets', return_type='item-or-list')
    ok_((subds.pathobj / '.git').is_dir())
    ok_(subds.is_installed())
    assert_in('sub', ds.subdatasets(state='present', result_xfm='relpaths'))
    # sub is clean:
    assert_repo_status(subds.path, annex=None)
    # top is clean:
    assert_repo_status(ds.path, annex=None)
    # source is recorded in .gitmodules:
    sds = ds.subdatasets("sub")
    assert_result_count(sds, 1, action='subdataset')
    eq_(sds[0]['gitmodule_datalad-url'], source.path)
    # Clone produced one commit including the addition to .gitmodule:
    commits = list(ds.repo.get_branch_commits_(
        branch=DEFAULT_BRANCH,
        stop=hexsha_before
    ))
    assert_not_in(hexsha_before, commits)
    eq_(len(commits), 1)

    # but we could also save while installing and there should be no side-effect
    # of saving any other changes if we state to not auto-save changes
    # Create a dummy change
    create_tree(ds.path, {'dummy.txt': 'buga'})
    assert_repo_status(ds.path, untracked=['dummy.txt'])
    subds_ = ds.clone(source, "sub2",
                      result_xfm='datasets', return_type='item-or-list')
    eq_(subds_.pathobj, ds.pathobj / "sub2")  # for paranoid yoh ;)
    assert_repo_status(ds.path, untracked=['dummy.txt'])

    # don't do anything to the dataset, when cloning fails (gh-6138)
    create_tree(ds.path, {'subdir': {'dummy2.txt': 'whatever'}})
    assert_repo_status(ds.path,
                       untracked=[str(ds.pathobj / 'subdir'),
                                  'dummy.txt'])
    hexsha_before = ds.repo.get_hexsha(DEFAULT_BRANCH)
    results = ds.clone(source, "subdir",
                       result_xfm=None,
                       return_type='list',
                       on_failure='ignore')
    assert_in_results(results, status='error')
    # status unchanged
    assert_repo_status(ds.path,
                       untracked=[str(ds.pathobj / 'subdir'),
                                  'dummy.txt'])
    # nothing was committed
    eq_(hexsha_before, ds.repo.get_hexsha(DEFAULT_BRANCH))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_notclone_known_subdataset(src_path=None, path=None):
    src = Dataset(src_path).create()
    sub = src.create('subm 1')
    sub_id = sub.id
    # get the superdataset:
    ds = clone(src, path,
               result_xfm='datasets', return_type='item-or-list')

    # subdataset not installed:
    subds = Dataset(ds.pathobj / 'subm 1')
    assert_false(subds.is_installed())
    assert_in('subm 1', ds.subdatasets(state='absent', result_xfm='relpaths'))
    assert_not_in('subm 1', ds.subdatasets(state='present', result_xfm='relpaths'))
    # clone is not meaningful
    res = ds.clone('subm 1', on_failure='ignore', result_xfm=None)
    assert_status('error', res)
    assert_message("Failed to clone from any candidate source URL. "
                   "Encountered errors per each url were:\n- %s",
                   res)
    # get does the job
    res = ds.get(path='subm 1', get_data=False)
    assert_status('ok', res)
    ok_(subds.is_installed())
    ok_(AnnexRepo.is_valid_repo(subds.path, allow_noninitialized=False))
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    eq_(subds.id, sub_id)
    assert_not_in('subm 1', ds.subdatasets(state='absent', result_xfm='relpaths'))
    assert_in('subm 1', ds.subdatasets(state='present', result_xfm='relpaths'))


@with_tempfile(mkdir=True)
def test_failed_clone(dspath=None):
    ds = create(dspath)
    res = ds.clone("http://nonexistingreallyanything.datalad.org/bla", "sub",
                   on_failure='ignore', result_xfm=None)
    assert_status('error', res)
    assert_message("Failed to clone from any candidate source URL. "
                   "Encountered errors per each url were:\n- %s",
                   res)


@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@with_tempfile
def test_clone_missing_commit(source=None, clone=None):

    from datalad.core.distributed.clone import clone_dataset

    source = Path(source)
    clone = Path(clone)

    # Commit SHA from another repository - should never be recreated in a fresh
    # dataset:
    commit_sha = "c29691b37b05b78ffa76e5fdf0044e9df673e8f1"

    origin = Dataset(source).create(force=True)
    origin.save()

    # clone origin but request commit_sha to be checked out:

    results = [x for x in
               clone_dataset(srcs=[source], destds=Dataset(clone),
                             checkout_gitsha=commit_sha)
               ]
    # expected error result:
    assert_result_count(results, 1)
    assert_in_results(results, status='error', action='install',
                      path=str(clone), type='dataset')
    assert_in("Target commit c29691b3 does not exist in the clone",
              results[0]['message'])
    # failed attempt was removed:
    assert_false(clone.exists())


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def check_reckless(annex, src_path, top_path, sharedpath):
    # super with or without annex
    src = Dataset(src_path).create(annex=annex)
    # sub always with annex
    srcsub = src.create('sub')

    # and for the actual test
    ds = clone(src.path, top_path, reckless=True,
               result_xfm='datasets', return_type='item-or-list')

    is_crippled = srcsub.repo.is_managed_branch()

    if annex and not is_crippled:
        eq_(ds.config.get('annex.hardlink', None), 'true')

    # actual value is 'auto', because True is a legacy value and we map it
    eq_(ds.config.get('datalad.clone.reckless', None), 'auto')
    if annex:
        eq_(ds.repo.repo_info()['untrusted repositories'][0]['here'], True)
    # now, if we clone another repo into this one, it will inherit the setting
    # without having to provide it explicitly
    newsub = ds.clone(srcsub, 'newsub', result_xfm='datasets', return_type='item-or-list')
    # and `get` the original subdataset
    origsub = ds.get('sub', result_xfm='datasets', return_type='item-or-list')
    for sds in (newsub, origsub):
        eq_(sds.config.get('datalad.clone.reckless', None), 'auto')
        if not is_crippled:
            eq_(sds.config.get('annex.hardlink', None), 'true')

    if is_crippled:
        raise SkipTest("Remainder of test needs proper filesystem permissions")

    if annex:
        if ds.repo.git_annex_version < "8.20200908":
            # TODO: Drop when GIT_ANNEX_MIN_VERSION is at least 8.20200908.

            # the standard setup keeps the annex locks accessible to the user only
            nok_((ds.pathobj / '.git' / 'annex' / 'index.lck').stat().st_mode \
                 & stat.S_IWGRP)
        else:
            # umask might be such (e.g. 002) that group write permissions are inherited, so
            # for the next test we should check if that is the case on some sample file
            dltmp_path = ds.pathobj / '.git' / "dltmp"
            dltmp_path.write_text('')
            default_grp_write_perms = dltmp_path.stat().st_mode & stat.S_IWGRP
            dltmp_path.unlink()
            # the standard setup keeps the annex locks following umask inheritance
            eq_((ds.pathobj / '.git' / 'annex' / 'index.lck').stat().st_mode \
                 & stat.S_IWGRP, default_grp_write_perms)

        # but we can set it up for group-shared access too
        sharedds = clone(
            src, sharedpath,
            reckless='shared-group',
            result_xfm='datasets',
            return_type='item-or-list')
        ok_((sharedds.pathobj / '.git' / 'annex' / 'index.lck').stat().st_mode \
            & stat.S_IWGRP)


@pytest.mark.parametrize('reckless', [True, False])
def test_reckless(reckless):
    check_reckless(reckless)


@with_tempfile
@with_tempfile
def test_install_source_relpath(src=None, dest=None):
    src = Path(src)
    create(src)
    src_ = src.name
    with chpwd(src.parent):
        clone(src_, dest)


@with_tempfile
@with_tempfile
def test_clone_isnt_a_smartass(origin_path=None, path=None):
    origin = create(origin_path)
    cloned = clone(origin, path,
                   result_xfm='datasets', return_type='item-or-list')
    with chpwd(path):
        # no were are inside a dataset clone, and we make another one
        # we do not want automatic subdatasetification without given a dataset
        # explicitly
        clonedsub = clone(origin, 'testsub',
                          result_xfm='datasets', return_type='item-or-list')
    # correct destination
    assert clonedsub.path.startswith(path)
    # no subdataset relation
    eq_(cloned.subdatasets(), [])


@with_tempfile(mkdir=True)
def test_clone_report_permission_issue(tdir=None):
    pdir = Path(tdir) / 'protected'
    pdir.mkdir()
    # make it read-only
    pdir.chmod(0o555)
    with chpwd(pdir):
        # first check the premise of the test. If we can write (strangely
        # mounted/crippled file system, subsequent assumptions are violated
        # and we can stop
        probe = Path('probe')
        try:
            probe.write_text('should not work')
            raise SkipTest
        except PermissionError:
            # we are indeed in a read-only situation
            pass
        res = clone('///', result_xfm=None, return_type='list', on_failure='ignore')
        assert_status('error', res)
        assert_result_count(
            res, 1, status='error',
            message="could not create work tree dir '%s/%s': Permission denied"
                    % (pdir, get_datasets_topdir())
        )


@skip_if_no_network
@with_tempfile
def test_autoenabled_remote_msg(path=None):
    # Verify that no message about a remote not been enabled is displayed
    # whenever the remote we clone is the  type=git special remote, so the name
    # of the remote might not match
    with swallow_logs(new_level=logging.INFO) as cml:
        res = clone('///repronim/containers', path, result_xfm=None, return_type='list')
        assert_status('ok', res)
        assert_not_in("not auto-enabled", cml.out)


@with_sameas_remote(autoenabled=True)
@with_tempfile(mkdir=True)
def test_clone_autoenable_msg_handles_sameas(repo=None, clone_path=None):
    ds = Dataset(repo.path)
    with swallow_logs(new_level=logging.INFO) as cml:
        res = clone(ds, clone_path, result_xfm=None, return_type='list')
        assert_status('ok', res)
        assert_in("r_dir", cml.out)
        assert_in("not auto-enabled", cml.out)
        # The rsyncurl remote was enabled.
        assert_not_in("r_rsync", cml.out)
    ds_cloned = Dataset(clone_path)
    remotes = ds_cloned.repo.get_remotes()
    assert_in("r_rsync", remotes)
    assert_not_in("r_dir", remotes)


def test_installationpath_from_url():
    # cases for all OSes
    cases = [
        'http://example.com/lastbit',
        'http://example.com/lastbit.git',
        'http://lastbit:8000',
        # SSH
        'hostname:lastbit',
        'hostname:lastbit/',
        'hostname:subd/lastbit',
        'hostname:/full/path/lastbit',
        'hostname:lastbit/.git',
        'hostname:lastbit/.git/',
        'hostname:/full/path/lastbit/.git',
        'full.hostname.com:lastbit/.git',
        'user@full.hostname.com:lastbit/.git',
        'ssh://user:passw@full.hostname.com/full/path/lastbit',
        'ssh://user:passw@full.hostname.com/full/path/lastbit/',
        'ssh://user:passw@full.hostname.com/full/path/lastbit/.git',
    ]
    # OS specific cases
    cases += [
        'C:\\Users\\mih\\AppData\\Local\\Temp\\lastbit',
        'C:\\Users\\mih\\AppData\\Local\\Temp\\lastbit\\',
        'Temp\\lastbit',
        'Temp\\lastbit\\',
        'lastbit.git',
        'lastbit.git\\',
    ] if on_windows else [
        'lastbit',
        'lastbit/',
        '/lastbit',
        'lastbit.git',
        'lastbit.git/',
    ]

    for p in cases:
        eq_(_get_installationpath_from_url(p), 'lastbit')
    # we need to deal with quoted urls
    for url in (
        # although some docs say that space could've been replaced with +
        'http://localhost:8000/+last%20bit',
        'http://localhost:8000/%2Blast%20bit',
        '///%2Blast%20bit',
        '///d1/%2Blast%20bit',
        '///d1/+last bit',
    ):
        eq_(_get_installationpath_from_url(url), '+last bit')
    # and the hostname alone
    eq_(_get_installationpath_from_url("http://hostname"), 'hostname')
    eq_(_get_installationpath_from_url("http://hostname/"), 'hostname')


# https://github.com/datalad/datalad/issues/3958
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_expanduser(srcpath=None, destpath=None):
    src = Dataset(Path(srcpath) / 'src').create()
    dest = Dataset(Path(destpath) / 'dest').create()

    # We switch away from home set up in datalad.setup_package(), so make sure
    # we have a valid identity.
    with open(op.join(srcpath, ".gitconfig"), "w") as fh:
        fh.write("[user]\n"
                 "name = DataLad oooooTester\n"
                 "email = test@example.com\n")

    with chpwd(destpath), patch.dict('os.environ', get_home_envvars(srcpath)):
        res = clone(op.join('~', 'src'), 'dest', result_xfm=None, return_type='list',
                    on_failure='ignore')
        assert_result_count(res, 1)
        assert_result_count(
            res, 1, action='install', status='error', path=dest.path,
            message='target path already exists and not empty, refuse to '
            'clone into target path')
        # wipe out destination, and try again
        assert_status('ok', remove(dataset=dest, reckless='kill'))
        # now it should do it, and clone the right one
        cloneds = clone(op.join('~', 'src'), 'dest')
        eq_(cloneds.pathobj, Path(destpath) / 'dest')
        eq_(src.id, cloneds.id)
        # and it shouldn't fail when doing it again, because it detects
        # the re-clone
        cloneds = clone(op.join('~', 'src'), 'dest')
        eq_(cloneds.pathobj, Path(destpath) / 'dest')


@with_tempfile(mkdir=True)
def test_cfg_originorigin(path=None):
    path = Path(path)
    origin = Dataset(path / 'origin').create()
    (origin.pathobj / 'file1.txt').write_text('content')
    origin.save()
    clone_lev1 = clone(origin, path / 'clone_lev1')
    clone_lev2 = clone(clone_lev1, path / 'clone_lev2')
    # the goal is to be able to get file content from origin without
    # the need to configure it manually
    assert_result_count(
        clone_lev2.get('file1.txt', on_failure='ignore'),
        1,
        action='get',
        status='ok',
        path=str(clone_lev2.pathobj / 'file1.txt'),
    )
    eq_((clone_lev2.pathobj / 'file1.txt').read_text(), 'content')
    eq_(
        Path(clone_lev2.siblings(
            'query',
            name=DEFAULT_REMOTE + '-2',
            return_type='item-or-list')['url']),
        origin.pathobj
    )

    # Clone another level, this time with a relative path. Drop content from
    # lev2 so that origin is the only place that the file is available from.
    clone_lev2.drop("file1.txt")
    with chpwd(path), swallow_logs(new_level=logging.DEBUG) as cml:
        clone_lev3 = clone('clone_lev2', 'clone_lev3')
        # we called git-annex-init; see gh-4367:
        cml.assert_logged(msg=r"[^[]*Run \[('git',.*'annex'|'git-annex'), 'init'",
                          match=False,
                          level='DEBUG')
    assert_result_count(
        clone_lev3.get('file1.txt', on_failure='ignore'),
        1,
        action='get',
        status='ok',
        path=str(clone_lev3.pathobj / 'file1.txt'))


# test fix for gh-2601/gh-3538
@known_failure
@with_tempfile()
def test_relative_submodule_url(path=None):
    Dataset(op.join(path, 'origin')).create()
    ds = Dataset(op.join(path, 'ds')).create()
    with chpwd(ds.path):
        ds_cloned = ds.clone(
            source=op.join(op.pardir, 'origin'),
            path='sources')

    # Check that a simple fetch call does not fail.
    ds_cloned.repo.fetch()

    subinfo = ds.subdatasets(return_type='item-or-list')
    eq_(subinfo['gitmodule_url'],
        # must be a relative URL, not platform-specific relpath!
        '../../origin')


@with_tree(tree={"subdir": {}})
@with_tempfile(mkdir=True)
def test_local_url_with_fetch(path=None, path_other=None):
    path = Path(path)
    path_other = Path(path_other)
    Dataset(path / "source").create()

    for where, source, path in [
            (path, "source", "a"),
            (path / "subdir", op.join(op.pardir, "source"), "a"),
            (path, "source", path_other / "a")]:
        with chpwd(where):
            ds_cloned = clone(source=source, path=path)
            # Perform a fetch to check that the URL points to a valid location.
            ds_cloned.repo.fetch()


def test_decode_source_spec():
    # resolves datalad RIs:
    eq_(decode_source_spec('///subds'),
        dict(source='///subds', giturl=consts.DATASETS_TOPURL + 'subds', version=None,
             type='dataladri', default_destpath='subds'))
    assert_raises(NotImplementedError, decode_source_spec,
                  '//custom/subds')

    # doesn't harm others:
    for url in (
            'http://example.com',
            '/absolute/path',
            'file://localhost/some',
            'localhost/another/path',
            'user@someho.st/mydir',
            'ssh://somewhe.re/else',
            'https://github.com/datalad/testrepo--basic--r1',
    ):
        props = decode_source_spec(url)
        dest = props.pop('default_destpath')
        eq_(props, dict(source=url, version=None, giturl=url, type='giturl'))

    # RIA URIs with and without version specification
    dsid = '6d69ca68-7e85-11e6-904c-002590f97d84'
    for proto, loc, version in (
            ('http', 'example.com', None),
            ('http', 'example.com', 'v1.0'),
            ('http', 'example.com', 'some_with@in_it'),
            ('ssh', 'example.com', 'some_with@in_it'),
    ):
        spec = 'ria+{}://{}{}{}'.format(
            proto,
            loc,
            '#{}'.format(dsid),
            '@{}'.format(version) if version else '')
        eq_(decode_source_spec(spec),
            dict(
                source=spec,
                giturl='{}://{}/{}/{}'.format(
                    proto,
                    loc,
                    dsid[:3],
                    dsid[3:]),
                version=version,
                default_destpath=dsid,
                type='ria')
        )
    # not a dataset UUID
    assert_raises(ValueError, decode_source_spec, 'ria+http://example.com#123')

    # literal dataset name/location
    eq_(decode_source_spec('ria+http://example.com#~rootds'),
        {'source': 'ria+http://example.com#~rootds',
         'version': None, 'type': 'ria',
         'giturl': 'http://example.com/alias/rootds',
         'default_destpath': 'rootds'})
    # version etc still works
    eq_(decode_source_spec('ria+http://example.com#~rootds@specialbranch'),
        {'source': 'ria+http://example.com#~rootds@specialbranch',
         'version': 'specialbranch', 'type': 'ria',
         'giturl': 'http://example.com/alias/rootds',
         'default_destpath': 'rootds'})


def _move2store(storepath, d):
    # make a bare clone of it into a local that matches the organization
    # of a ria dataset store
    store_loc = str(storepath / d.id[:3] / d.id[3:])
    d.repo.call_git(['clone', '--bare', d.path, store_loc])
    d.siblings('configure', name='store', url=str(store_loc),
               result_renderer='disabled')
    Runner(cwd=store_loc).run(['git', 'update-server-info'])


@slow  # 12sec on Yarik's laptop
@with_tree(tree={
    'ds': {
        'test.txt': 'some',
        'subdir': {
            'subds': {'testsub.txt': 'somemore'},
        },
    },
})
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_ria_http(lcl=None, storepath=None, url=None):
    # create a local dataset with a subdataset
    lcl = Path(lcl)
    storepath = Path(storepath)
    subds = Dataset(lcl / 'ds' / 'subdir' / 'subds').create(force=True)
    subds.save()
    ds = Dataset(lcl / 'ds').create(force=True)
    ds.save(version_tag='original')
    assert_repo_status(ds.path)
    for d in (ds, subds):
        _move2store(storepath, d)
    # location of superds in store
    storeds_loc = str(storepath / ds.id[:3] / ds.id[3:])
    # now we should be able to clone from a ria+http url
    # the super
    riaclone = clone(
        'ria+{}#{}'.format(url, ds.id),
        lcl / 'clone',
    )

    # due to default configuration, clone() should automatically look for the
    # subdataset in the store, too -- if not the following would fail, because
    # we never configured a proper submodule URL
    riaclonesub = riaclone.get(
        op.join('subdir', 'subds'), get_data=False,
        result_xfm='datasets', return_type='item-or-list')

    # both datasets came from the store and must be set up in an identical
    # fashion
    for origds, cloneds in ((ds, riaclone), (subds, riaclonesub)):
        eq_(origds.id, cloneds.id)
        if not ds.repo.is_managed_branch():
            # test logic cannot handle adjusted branches
            eq_(origds.repo.get_hexsha(), cloneds.repo.get_hexsha())
        ok_(cloneds.config.get(f'remote.{DEFAULT_REMOTE}.url').startswith(url))
        eq_(cloneds.config.get(f'remote.{DEFAULT_REMOTE}.annex-ignore'), 'true')
        eq_(cloneds.config.get('datalad.get.subdataset-source-candidate-200origin'),
            'ria+%s#{id}' % url)

    # now advance the source dataset
    (ds.pathobj / 'newfile.txt').write_text('new')
    ds.save()
    ds.push(to='store')
    Runner(cwd=storeds_loc).run(['git', 'update-server-info'])
    # re-clone as before
    riaclone2 = clone(
        'ria+{}#{}'.format(url, ds.id),
        lcl / 'clone2',
    )
    # and now clone a specific version, here given be the tag name
    riaclone_orig = clone(
        'ria+{}#{}@{}'.format(url, ds.id, 'original'),
        lcl / 'clone_orig',
    )
    if not ds.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        # we got the precise version we wanted
        eq_(riaclone.repo.get_hexsha(), riaclone_orig.repo.get_hexsha())
        # and not the latest
        eq_(riaclone2.repo.get_hexsha(), ds.repo.get_hexsha())
        neq_(riaclone2.repo.get_hexsha(), riaclone_orig.repo.get_hexsha())

    # attempt to clone a version that doesn't exist
    with swallow_logs():
        with assert_raises(IncompleteResultsError) as cme:
            clone('ria+{}#{}@impossible'.format(url, ds.id),
                  lcl / 'clone_failed')
        assert_in("not found in upstream", str(cme.value))

    # lastly test if URL rewriting is in effect
    # on the surface we clone from an SSH source identified by some custom
    # label, no full URL, but URL rewriting setup maps it back to the
    # HTTP URL used above
    with patch_config({
            'url.ria+{}#.insteadof'.format(url): 'ria+ssh://somelabel#'}):
        cloned_by_label = clone(
            'ria+ssh://somelabel#{}'.format(origds.id),
            lcl / 'cloned_by_label',
        )
    # so we get the same setup as above, but....
    eq_(origds.id, cloned_by_label.id)
    if not ds.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        eq_(origds.repo.get_hexsha(), cloned_by_label.repo.get_hexsha())
    ok_(cloned_by_label.config.get(
        f'remote.{DEFAULT_REMOTE}.url').startswith(url))
    eq_(cloned_by_label.config.get(f'remote.{DEFAULT_REMOTE}.annex-ignore'),
        'true')
    # ... the clone candidates go with the label-based URL such that
    # future get() requests acknowledge a (system-wide) configuration
    # update
    eq_(cloned_by_label.config.get('datalad.get.subdataset-source-candidate-200origin'),
        'ria+ssh://somelabel#{id}')

    if not has_symlink_capability():
        return
    # place a symlink in the store to serve as a dataset alias
    (storepath / 'alias').mkdir()
    (storepath / 'alias' / 'myname').symlink_to(storeds_loc)
    with chpwd(lcl):
        cloned_by_alias = clone('ria+{}#~{}'.format(url, 'myname'))
    # still get the same data
    eq_(cloned_by_alias.id, ds.id)
    # more sensible default install path
    eq_(cloned_by_alias.pathobj.name, 'myname')


@with_tempfile
@with_tempfile
def _test_ria_postclonecfg(url, dsid, clone_path, superds):
    # Test cloning from RIA store while ORA special remote autoenabling failed
    # due to an invalid URL from the POV of the cloner.
    # Origin's git-config-file should contain the UUID to enable. This needs to
    # work via HTTP, SSH and local cloning.

    # Autoenabling should fail initially by git-annex-init and we would report
    # on INFO level. Only postclone routine would deal with it.
    with swallow_logs(new_level=logging.INFO) as cml:
        # First, the super ds:
        riaclone = clone('ria+{}#{}'.format(url, dsid), clone_path)
        cml.assert_logged(msg="access to 1 dataset sibling store-storage not "
                              "auto-enabled",
                          level="INFO",
                          regex=False)

    # However, we now can retrieve content since clone should have enabled the
    # special remote with new URL (or origin in case of HTTP).
    res = riaclone.get('test.txt')
    assert_result_count(res, 1,
                        status='ok',
                        path=str(riaclone.pathobj / 'test.txt'),
                        message="from {}...".format(DEFAULT_REMOTE
                                                    if url.startswith('http')
                                                    else "store-storage"))

    # Second ORA remote is enabled and not reconfigured:
    untouched_remote = riaclone.siblings(name='anotherstore-storage',
                                         return_type='item-or-list')
    assert_not_is_instance(untouched_remote, list)
    untouched_url = riaclone.repo.get_special_remotes()[
        untouched_remote['annex-uuid']]['url']
    ok_(untouched_url.startswith("ria+file://"))
    ok_(not untouched_url.startswith("ria+{}".format(url)))

    # publication dependency was set for store-storage but not for
    # anotherstore-storage:
    eq_(riaclone.config.get(f"remote.{DEFAULT_REMOTE}.datalad-publish-depends",
                            get_all=True),
        "store-storage")

    # same thing for the sub ds (we don't need a store-url and id - get should
    # figure those itself):
    with swallow_logs(new_level=logging.INFO) as cml:
        riaclonesub = riaclone.get(
            op.join('subdir', 'subds'), get_data=False,
            result_xfm='datasets', return_type='item-or-list')
        cml.assert_logged(msg="access to 1 dataset sibling store-storage not "
                              "auto-enabled",
                          level="INFO",
                          regex=False)
    res = riaclonesub.get('testsub.txt')
    assert_result_count(res, 1,
                        status='ok',
                        path=str(riaclonesub.pathobj / 'testsub.txt'),
                        message="from {}...".format(DEFAULT_REMOTE
                                                    if url.startswith('http')
                                                    else "store-storage"))

    # publication dependency was set for store-storage but not for
    # anotherstore-storage:
    eq_(riaclonesub.config.get(f"remote.{DEFAULT_REMOTE}.datalad-publish-depends",
                               get_all=True),
        "store-storage")

    # finally get the plain git subdataset.
    # Clone should figure to also clone it from a ria+ URL
    # (subdataset-source-candidate), notice that there wasn't an autoenabled ORA
    # remote, but shouldn't stumble upon it, since it's a plain git.
    res = riaclone.get(op.join('subdir', 'subgit', 'testgit.txt'))
    assert_result_count(res, 1, status='ok', type='dataset', action='install')
    assert_result_count(res, 1, status='notneeded', type='file')
    assert_result_count(res, 2)
    # no ORA remote, no publication dependency:
    riaclonesubgit = Dataset(riaclone.pathobj / 'subdir' / 'subgit')
    eq_(riaclonesubgit.config.get(f"remote.{DEFAULT_REMOTE}.datalad-publish-depends",
                                  get_all=True),
        None)

    # Now, test that if cloning into a dataset, ria-URL is preserved and
    # post-clone configuration is triggered again, when we remove the subds and
    # retrieve it again via `get`:
    ds = Dataset(superds).create()
    ria_url = 'ria+{}#{}'.format(url, dsid)
    ds.clone(ria_url, 'sub')
    sds = ds.subdatasets('sub')
    eq_(len(sds), 1)
    eq_(sds[0]['gitmodule_datalad-url'], ria_url)
    assert_repo_status(ds.path)
    ds.drop('sub', what='all', reckless='kill', recursive=True)
    assert_repo_status(ds.path)

    # .gitmodules still there:
    sds = ds.subdatasets('sub')
    eq_(len(sds), 1)
    eq_(sds[0]['gitmodule_datalad-url'], ria_url)
    # get it again:

    # Autoenabling should fail initially by git-annex-init and we would report
    # on INFO level. Only postclone routine would deal with it.
    with swallow_logs(new_level=logging.INFO) as cml:
        ds.get('sub', get_data=False)
        cml.assert_logged(msg="access to 1 dataset sibling store-storage not "
                              "auto-enabled",
                          level="INFO",
                          regex=False)

    subds = Dataset(ds.pathobj / 'sub')
    # special remote is fine:
    res = subds.get('test.txt')
    assert_result_count(res, 1,
                        status='ok',
                        path=str(subds.pathobj / 'test.txt'),
                        message="from {}...".format(DEFAULT_REMOTE
                                                    if url.startswith('http')
                                                    else "store-storage"))


@with_tempfile
def _postclonetest_prepare(lcl, storepath, storepath2, link):

    from datalad.customremotes.ria_utils import (
        create_ds_in_store,
        create_store,
        get_layout_locations,
    )
    from datalad.distributed.ora_remote import LocalIO

    create_tree(lcl,
                tree={
                        'ds': {
                            'test.txt': 'some',
                            'subdir': {
                                'subds': {'testsub.txt': 'somemore'},
                                'subgit': {'testgit.txt': 'even more'}
                            },
                        },
                      })

    lcl = Path(lcl)
    storepath = Path(storepath)
    storepath2 = Path(storepath2)
    link = Path(link)
    link.symlink_to(storepath)

    # create a local dataset with a subdataset
    subds = Dataset(lcl / 'ds' / 'subdir' / 'subds').create(force=True)
    subds.save()
    # add a plain git dataset as well
    subgit = Dataset(lcl / 'ds' / 'subdir' / 'subgit').create(force=True,
                                                              annex=False)
    subgit.save()
    ds = Dataset(lcl / 'ds').create(force=True)
    ds.save(version_tag='original')
    assert_repo_status(ds.path)

    io = LocalIO()

    # Have a second store with valid ORA remote. This should not interfere with
    # reconfiguration of the first one, when that second store is not the one we
    # clone from. However, don't push data into it for easier get-based testing
    # later on.
    # Doing this first, so datasets in "first"/primary store know about this.
    create_store(io, storepath2, '1')
    url2 = "ria+{}".format(get_local_file_url(str(storepath2)))
    for d in (ds, subds, subgit):
        create_ds_in_store(io, storepath2, d.id, '2', '1')
        d.create_sibling_ria(url2, "anotherstore", new_store_ok=True)
        d.push('.', to='anotherstore', data='nothing')
        store2_loc, _, _ = get_layout_locations(1, storepath2, d.id)
        Runner(cwd=str(store2_loc)).run(['git', 'update-server-info'])

    # Now the store to clone from:
    create_store(io, storepath, '1')

    # URL to use for upload. Point is, that this should be invalid for the clone
    # so that autoenable would fail. Therefore let it be based on a to be
    # deleted symlink
    upl_url = "ria+{}".format(get_local_file_url(str(link)))

    for d in (ds, subds, subgit):

        # TODO: create-sibling-ria required for config! => adapt to RF'd
        #       creation (missed on rebase?)
        create_ds_in_store(io, storepath, d.id, '2', '1')
        d.create_sibling_ria(upl_url, "store", new_store_ok=True)

        if d is not subgit:
            # Now, simulate the problem by reconfiguring the special remote to
            # not be autoenabled.
            # Note, however, that the actual intention is a URL, that isn't
            # valid from the point of view of the clone (doesn't resolve, no
            # credentials, etc.) and therefore autoenabling on git-annex-init
            # when datalad-cloning would fail to succeed.
            Runner(cwd=d.path).run(['git', 'annex', 'enableremote',
                                    'store-storage',
                                    'autoenable=false'])
        d.push('.', to='store')
        store_loc, _, _ = get_layout_locations(1, storepath, d.id)
        Runner(cwd=str(store_loc)).run(['git', 'update-server-info'])

    link.unlink()
    # We should now have a store with datasets that have an autoenabled ORA
    # remote relying on an inaccessible URL.
    # datalad-clone is supposed to reconfigure based on the URL we cloned from.
    # Test this feature for cloning via HTTP, SSH and FILE URLs.

    return ds.id


# TODO?: make parametric again on _test_ria_postclonecfg
@known_failure_windows  # https://github.com/datalad/datalad/issues/5134
@slow  # 14 sec on travis
def test_ria_postclonecfg():

    if not has_symlink_capability():
        # This is needed to create an ORA remote using an URL for upload,
        # that is then invalidated later on (delete the symlink it's based on).
        raise SkipTest("Can't create symlinks")

    from datalad.utils import make_tempfile

    with make_tempfile(mkdir=True) as lcl, make_tempfile(mkdir=True) as store, \
            make_tempfile(mkdir=True) as store2:
        id = _postclonetest_prepare(lcl, store, store2)

        # test cloning via ria+file://
        _test_ria_postclonecfg(
              get_local_file_url(store, compatibility='git'), id
        )

        # Note: HTTP disabled for now. Requires proper implementation in ORA
        #       remote. See
        # https://github.com/datalad/datalad/pull/4203#discussion_r410284649

        # # test cloning via ria+http://
        # with HTTPPath(store) as url:
        #     yield _test_ria_postclonecfg, url, id

        # test cloning via ria+ssh://
        skip_ssh(_test_ria_postclonecfg)(
            "ssh://datalad-test:{}".format(Path(store).as_posix()), id
        )


@known_failure_windows
@skip_ssh
@with_tree(tree={'somefile.txt': 'some content'})
@with_tempfile
@with_tempfile
def test_no_ria_postclonecfg(dspath=None, storepath=None, clonepath=None):

    dspath = Path(dspath)
    storepath = Path(storepath)
    clonepath = Path(clonepath)

    # Test that particular configuration(s) do NOT lead to a reconfiguration
    # upon clone. (See gh-5628)

    from datalad.customremotes.ria_utils import create_store
    from datalad.distributed.ora_remote import LocalIO

    ds = Dataset(dspath).create(force=True)
    ds.save()
    assert_repo_status(ds.path)

    io = LocalIO()
    create_store(io, storepath, '1')
    file_url = "ria+{}".format(get_local_file_url(str(storepath)))
    ssh_url = "ria+ssh://datalad-test:{}".format(storepath.as_posix())
    ds.create_sibling_ria(file_url, "teststore",
                          push_url=ssh_url, alias="testds",
                          new_store_ok=True)
    ds.push('.', to='teststore')

    # Now clone via SSH. Should not reconfigure although `url` doesn't match the
    # URL we cloned from. However, `push-url` does.
    riaclone = clone('{}#{}'.format(ssh_url, ds.id), clonepath)

    # ORA remote is enabled (since URL still valid) but not reconfigured:
    untouched_remote = riaclone.siblings(name='teststore-storage',
                                         return_type='item-or-list')
    assert_not_is_instance(untouched_remote, list)
    ora_cfg = riaclone.repo.get_special_remotes()[
        untouched_remote['annex-uuid']]
    ok_(ora_cfg['url'] == file_url)
    ok_(ora_cfg['push-url'] == ssh_url)

    # publication dependency was still set (and it's the only one that was set):
    eq_(riaclone.config.get(f"remote.{DEFAULT_REMOTE}.datalad-publish-depends",
                            get_all=True),
        "teststore-storage")

    # we can still get the content
    ds.get("somefile.txt")


# fatal: Could not read from remote repository.
@known_failure_githubci_win  # in datalad/git-annex as e.g. of 20201218
@with_tempfile(mkdir=True)
@with_tempfile
@with_tempfile
def test_ria_postclone_noannex(dspath=None, storepath=None, clonepath=None):

    # Test for gh-5186: Cloning from local FS, shouldn't lead to annex
    # initializing origin.

    dspath = Path(dspath)
    storepath = Path(storepath)
    clonepath = Path(clonepath)

    from datalad.customremotes.ria_utils import (
        create_ds_in_store,
        create_store,
        get_layout_locations,
    )
    from datalad.distributed.ora_remote import LocalIO

    # First create a dataset in a RIA store the standard way
    somefile = dspath / 'a_file.txt'
    somefile.write_text('irrelevant')
    ds = Dataset(dspath).create(force=True)

    io = LocalIO()
    create_store(io, storepath, '1')
    lcl_url = "ria+{}".format(get_local_file_url(str(storepath)))
    create_ds_in_store(io, storepath, ds.id, '2', '1')
    ds.create_sibling_ria(lcl_url, "store", new_store_ok=True)
    ds.push('.', to='store')


    # now, remove annex/ tree from store in order to see, that clone
    # doesn't cause annex to recreate it.
    store_loc, _, _ = get_layout_locations(1, storepath, ds.id)
    annex = store_loc / 'annex'
    rmtree(str(annex))
    assert_false(annex.exists())

    clone_url = get_local_file_url(str(storepath), compatibility='git') + \
                '#{}'.format(ds.id)
    clone("ria+{}".format(clone_url), clonepath)

    # no need to test the cloning itself - we do that over and over in here

    # bare repo in store still has no local annex:
    assert_false(annex.exists())


@slow  # 17sec on Yarik's laptop
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_inherit_src_candidates(lcl=None, storepath=None, url=None):
    lcl = Path(lcl)
    storepath = Path(storepath)
    # dataset with a subdataset
    ds1 = Dataset(lcl / 'ds1').create()
    ds1sub = ds1.create('sub')
    # a different dataset into which we install ds1, but do not touch its subds
    ds2 = Dataset(lcl / 'ds2').create()
    ds2.clone(source=ds1.path, path='mysub')

    # we give no dataset a source candidate config!
    # move all dataset into the store
    for d in (ds1, ds1sub, ds2):
        _move2store(storepath, d)

    # now we must be able to obtain all three datasets from the store
    riaclone = clone(
        'ria+{}#{}'.format(
            # store URL
            url,
            # ID of the root dataset
            ds2.id),
        lcl / 'clone',
    )
    # what happens is the the initial clone call sets a source candidate
    # config, because it sees the dataset coming from a store
    # all obtained subdatasets get the config inherited on-clone
    datasets = riaclone.get('.', get_data=False, recursive=True, result_xfm='datasets')
    # we get two subdatasets
    eq_(len(datasets), 2)
    for ds in datasets:
        eq_(ConfigManager(dataset=ds, source='branch-local').get(
            'datalad.get.subdataset-source-candidate-200origin'),
            'ria+%s#{id}' % url)


@skip_if_no_network
@with_tempfile()
def test_ria_http_storedataladorg(path=None):
    # can we clone from the store w/o any dedicated config
    ds = clone('ria+http://store.datalad.org#{}'.format(datalad_store_testds_id), path)
    ok_(ds.is_installed())
    eq_(ds.id, datalad_store_testds_id)


@skip_if_on_windows  # see gh-4131
# Ephemeral clones cannot use adjusted mode repos
@skip_if_adjusted_branch
@with_tree(tree={
    'ds': {
        'test.txt': 'some',
        'subdir': {'testsub.txt': 'somemore'},
    },
})
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_ephemeral(origin_path=None, bare_path=None,
                   clone1_path=None, clone2_path=None, clone3_path=None):

    file_test = Path('ds') / 'test.txt'
    file_testsub = Path('ds') / 'subdir' / 'testsub.txt'

    origin = Dataset(origin_path).create(force=True)
    origin.save()
    # 1. clone via path
    clone1 = clone(origin_path, clone1_path, reckless='ephemeral')
    eq_(clone1.config.get("annex.private"), "true")

    can_symlink = has_symlink_capability()

    if can_symlink:
        clone1_annex = (clone1.repo.dot_git / 'annex')
        ok_(clone1_annex.is_symlink())
        ok_(clone1_annex.resolve().samefile(origin.repo.dot_git / 'annex'))
        if not clone1.repo.is_managed_branch():
            # TODO: We can't properly handle adjusted branch yet
            eq_((clone1.pathobj / file_test).read_text(), 'some')
            eq_((clone1.pathobj / file_testsub).read_text(), 'somemore')

    # 2. clone via file-scheme URL
    clone2 = clone('file://' + Path(origin_path).as_posix(), clone2_path,
                   reckless='ephemeral')
    eq_(clone2.config.get("annex.private"), "true")

    if can_symlink:
        clone2_annex = (clone2.repo.dot_git / 'annex')
        ok_(clone2_annex.is_symlink())
        ok_(clone2_annex.resolve().samefile(origin.repo.dot_git / 'annex'))
        if not clone2.repo.is_managed_branch():
            # TODO: We can't properly handle adjusted branch yet
            eq_((clone2.pathobj / file_test).read_text(), 'some')
            eq_((clone2.pathobj / file_testsub).read_text(), 'somemore')

    # 3. add something to clone1 and push back to origin availability from
    # clone1 should not be propagated (we declared 'here' dead to that end)

    (clone1.pathobj / 'addition.txt').write_text("even more")
    clone1.save()
    origin.config.set("receive.denyCurrentBranch", "updateInstead",
                      scope="local")
    # Note, that the only thing to test is git-annex-dead here,
    # if we couldn't symlink:
    clone1.push(to=DEFAULT_REMOTE, data='nothing' if can_symlink else 'auto')

    if external_versions['cmd:annex'] >= "8.20210428":
        # ephemeral clones are private (if supported by annex version). Despite
        # the push, clone1's UUID doesn't show up in origin
        recorded_locations = origin.repo.call_git(['cat-file', 'blob',
                                                   'git-annex:uuid.log'],
                                                  read_only=True)
        assert_not_in(clone1.config.get("annex.uuid"), recorded_locations)

    if not origin.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        eq_(origin.repo.get_hexsha(), clone1.repo.get_hexsha())
    res = origin.repo.whereis("addition.txt")
    if can_symlink:
        # obv. present in origin, but this is not yet known to origin:
        eq_(res, [])
        res = origin.repo.fsck()
        assert_result_count(res, 3, success=True)
        # TODO: Double check whether annex reports POSIX paths o windows!
        eq_({str(file_test), str(file_testsub), "addition.txt"},
            {r['file'] for r in res})
        # now origin knows:
    res = origin.repo.whereis("addition.txt")
    eq_(res, [origin.config.get("annex.uuid")])

    # 4. ephemeral clone from a bare repo
    runner = GitWitlessRunner()
    runner.run(['git', 'clone', '--bare', origin_path, bare_path])
    runner.run(['git', 'annex', 'init'], cwd=bare_path)

    eph_from_bare = clone(bare_path, clone3_path, reckless='ephemeral')
    can_symlink = has_symlink_capability()

    if can_symlink:
        # Bare repo uses dirhashlower by default, while a standard repo uses
        # dirhashmixed. Symlinking different object trees doesn't really work.
        # Don't test that here, since this is not a matter of the "ephemeral"
        # option alone. We should have such a setup in the RIA tests and test
        # for data access there.
        # Here we only test for the correct linking.
        eph_annex = eph_from_bare.repo.dot_git / 'annex'
        ok_(eph_annex.is_symlink())
        ok_(eph_annex.resolve().samefile(Path(bare_path) / 'annex'))


@with_tempfile(mkdir=True)
def test_clone_unborn_head(path=None):
    ds_origin = Dataset(op.join(path, "a")).create()
    repo = ds_origin.repo
    managed = repo.is_managed_branch()

    # The setup below is involved, mostly because it's accounting for adjusted
    # branches. The scenario itself isn't so complicated, though:
    #
    #   * a checked out default branch with no commits
    #   * a (potentially adjusted) "abc" branch with commits.
    #   * a (potentially adjusted) "chooseme" branch whose tip commit has a
    #     more recent commit than any in "abc".
    (ds_origin.pathobj / "foo").write_text("foo content")
    ds_origin.save(message="foo")
    for res in repo.for_each_ref_(fields="refname"):
        ref = res["refname"]
        if DEFAULT_BRANCH in ref:
            repo.update_ref(ref.replace(DEFAULT_BRANCH, "abc"), ref)
            repo.call_git(["update-ref", "-d", ref])
    repo.update_ref("HEAD",
                    "refs/heads/{}".format(
                        "adjusted/abc(unlocked)" if managed else "abc"),
                    symbolic=True)
    abc_ts = int(repo.format_commit("%ct"))
    repo.call_git(["checkout", "-b", "chooseme", "abc~1"])
    if managed:
        repo.adjust()
    (ds_origin.pathobj / "bar").write_text("bar content")
    with set_date(abc_ts + 1):
        ds_origin.save(message="bar")
    # Make the git-annex branch the most recently updated ref so that we test
    # that it is skipped.
    with set_date(abc_ts + 2):
        ds_origin.drop("bar", reckless='kill')
    ds_origin.repo.checkout(DEFAULT_BRANCH, options=["--orphan"])

    ds = clone(ds_origin.path, op.join(path, "b"))
    # We landed on the branch with the most recent commit, ignoring the
    # git-annex branch.
    branch = ds.repo.get_active_branch()
    eq_(ds.repo.get_corresponding_branch(branch) or branch,
        "chooseme")
    eq_(ds_origin.repo.get_hexsha("chooseme"),
        ds.repo.get_hexsha("chooseme"))
    # In the context of this test, the clone should be on an adjusted branch if
    # the source landed there initially because we're on the same file system.
    eq_(managed, ds.repo.is_managed_branch())


@with_tempfile(mkdir=True)
def test_clone_unborn_head_no_other_ref(path=None):
    ds_origin = Dataset(op.join(path, "a")).create(annex=False)
    ds_origin.repo.call_git(["update-ref", "-d",
                             "refs/heads/" + DEFAULT_BRANCH])
    with swallow_logs(new_level=logging.WARNING) as cml:
        clone(source=ds_origin.path, path=op.join(path, "b"))
        assert_in("could not find a branch with commits", cml.out)


@with_tempfile(mkdir=True)
def test_clone_unborn_head_sub(path=None):
    ds_origin = Dataset(op.join(path, "a")).create()
    ds_origin_sub = Dataset(op.join(path, "a", "sub")).create()
    managed = ds_origin_sub.repo.is_managed_branch()
    ds_origin.save(message="foo")
    sub_repo = ds_origin_sub.repo
    # As with test_clone_unborn_head(), the setup below is complicated mostly
    # because it's accounting for adjusted branches, but the scenario itself
    # isn't too complicated:
    #
    #   * a submodule's HEAD points to a checked out branch with no commits
    #     while a (potentially adjusted) "other" branch has commits
    #
    #   * the parent repo has the tip of "other" as the last recorded state
    for res in sub_repo.for_each_ref_(fields="refname"):
        ref = res["refname"]
        if DEFAULT_BRANCH in ref:
            sub_repo.update_ref(ref.replace(DEFAULT_BRANCH, "other"), ref)
            sub_repo.call_git(["update-ref", "-d", ref])
    sub_repo.update_ref(
        "HEAD",
        "refs/heads/{}".format(
            "adjusted/other(unlocked)" if managed else "other"),
        symbolic=True)
    # END complicated handling for adjusted branches
    ds_origin.save()
    ds_origin_sub.repo.checkout(DEFAULT_BRANCH, options=["--orphan"])

    ds_cloned = clone(source=ds_origin.path, path=op.join(path, "b"))
    ds_cloned_sub = ds_cloned.get(
        "sub", result_xfm="datasets", return_type="item-or-list")

    branch = ds_cloned_sub.repo.get_active_branch()
    eq_(ds_cloned_sub.repo.get_corresponding_branch(branch) or branch,
        "other")
    # In the context of this test, the clone should be on an adjusted branch if
    # the source landed there initially because we're on the same file system.
    eq_(managed, ds_cloned_sub.repo.is_managed_branch())


@skip_if_no_network
@with_tempfile
def test_gin_cloning(path=None):
    # can we clone a public ds anoynmously from gin and retrieve content
    ds = clone('https://gin.g-node.org/datalad/datalad-ci-target', path)
    ok_(ds.is_installed())
    annex_path = op.join('annex', 'two')
    git_path = op.join('git', 'one')
    eq_(ds.repo.file_has_content(annex_path), False)
    eq_(ds.repo.is_under_annex(git_path), False)
    result = ds.get(annex_path)
    assert_result_count(result, 1)
    assert_status('ok', result)
    eq_(result[0]['path'], op.join(ds.path, annex_path))
    ok_file_has_content(op.join(ds.path, annex_path), 'two\n')
    ok_file_has_content(op.join(ds.path, git_path), 'one\n')


# TODO: git-annex-init fails in the second clone call below when this is
# executed under ./tools/eval_under_testloopfs.
@skip_if_adjusted_branch
@with_tree(tree={"special": {"f0": "0"}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_fetch_git_special_remote(url_path=None, url=None, path=None):
    url_path = Path(url_path)
    path = Path(path)
    ds_special = Dataset(url_path / "special").create(force=True)
    ds_special.save()
    ds_special.repo.call_git(["update-server-info"])

    clone_url = url + "special/.git"
    ds_a = clone(clone_url, path / "a")
    ds_a.repo.call_annex(
        ["initremote", "special", "type=git", "autoenable=true",
         "location=" + clone_url])

    # Set up a situation where a file is present only on the special remote,
    # and its existence is known only to the special remote's git-annex branch.
    (ds_special.pathobj / "f1").write_text("1")
    ds_special.save()
    ds_special.repo.call_git(["update-server-info"])

    ds_a.repo.fetch(DEFAULT_REMOTE)
    ds_a.repo.merge(f"{DEFAULT_REMOTE}/{DEFAULT_BRANCH}")

    ds_b = clone(ds_a.path, path / "other")
    ds_b.get("f1")
    ok_(ds_b.repo.file_has_content("f1"))


@skip_if_adjusted_branch
@skip_if_no_network
@with_tempfile(mkdir=True)
def test_nonuniform_adjusted_subdataset(path=None):
    # https://github.com/datalad/datalad/issues/5107
    topds = Dataset(Path(path) / "top").create()
    subds_url = 'https://github.com/datalad/testrepo--basic--r1'
    topds.clone(
        source='https://github.com/datalad/testrepo--basic--r1',
        path='subds')
    eq_(topds.subdatasets(return_type='item-or-list')['gitmodule_url'],
        subds_url)


@with_tempfile
def test_clone_recorded_subds_reset(path=None):
    path = Path(path)
    ds_a = create(path / "ds_a")
    ds_a_sub = ds_a.create("sub")
    (ds_a_sub.pathobj / "foo").write_text("foo")
    ds_a.save(recursive=True)
    (ds_a_sub.pathobj / "bar").write_text("bar")
    ds_a_sub.save()

    ds_b = clone(ds_a.path, path / "ds_b")
    ds_b.get("sub")
    assert_repo_status(ds_b.path)
    sub_repo = Dataset(path / "ds_b" / "sub").repo
    branch = sub_repo.get_active_branch()
    eq_(ds_b.subdatasets()[0]["gitshasum"],
        sub_repo.get_hexsha(
            sub_repo.get_corresponding_branch(branch) or branch))


@with_tempfile
def test_clone_git_clone_opts(path=None):
    path = Path(path)
    ds_a = create(path / "ds_a", annex=False)

    repo_a = ds_a.repo
    repo_a.commit(msg="c1", options=["--allow-empty"])
    repo_a.checkout(DEFAULT_BRANCH + "-other", ["-b"])
    repo_a.commit(msg="c2", options=["--allow-empty"])
    repo_a.tag("atag")

    ds_b = clone(ds_a.path, path / "ds_b",
                 git_clone_opts=[f"--branch={DEFAULT_BRANCH}",
                                 "--single-branch", "--no-tags"])
    repo_b = ds_b.repo
    eq_(repo_b.get_active_branch(), DEFAULT_BRANCH)
    eq_(set(x["refname"] for x in repo_b.for_each_ref_(fields="refname")),
        {f"refs/heads/{DEFAULT_BRANCH}",
         f"refs/remotes/{DEFAULT_REMOTE}/{DEFAULT_BRANCH}"})


@with_tempfile
@with_tempfile
def test_clone_url_mapping(src_path=None, dest_path=None):
    src = create(src_path)
    dest = Dataset(dest_path)
    # check that the impossible doesn't work
    assert_raises(IncompleteResultsError, clone, 'rambo', dest_path)
    # rather than adding test URL mapping here, consider
    # test_url_mapping_specs(), it is cheaper there

    # anticipate windows test paths and escape them
    escaped_subst = (r',rambo,%s' % src_path).replace('\\', '\\\\')
    for specs in (
            # we can clone with a simple substitution
            {'datalad.clone.url-substitute.mike': escaped_subst},
            # a prior match to a dysfunctional URL doesn't impact success
            {
                'datalad.clone.url-substitute.no': ',rambo,picknick',
                'datalad.clone.url-substitute.mike': escaped_subst,
            }):
        try:
            with patch.dict(dest.config._merged_store, specs):
                clone('rambo', dest_path)
        finally:
            dest.drop(what='all', reckless='kill', recursive=True)

    # check submodule config impact
    dest.create()
    with patch.dict(dest.config._merged_store,
                    {'datalad.clone.url-substitute.mike': escaped_subst}):
        dest.clone('rambo', 'subds')
    submod_rec = dest.repo.get_submodules()[0]
    # we record the original-original URL
    eq_(submod_rec['gitmodule_datalad-url'], 'rambo')
    # and put the effective one as the primary URL
    eq_(submod_rec['gitmodule_url'], src_path)


_nomatch_map = {
    'datalad.clone.url-substitute.nomatch': (
        ',nomatch,NULL',
    )
}
_windows_map = {
    'datalad.clone.url-substitute.win': (
        r',C:\\Users\\datalad\\from,D:\\to',
    )
}


def test_url_mapping_specs():
    from datalad.core.distributed.clone import _map_urls
    cfg = ConfigManager()
    for m, i, o in (
            # path redirect on windows
            (_windows_map,
             r'C:\Users\datalad\from',
             r'D:\to'),
            # test standard github mapping, no pathc needed
            ({},
             'https://github.com/datalad/testrepo_gh/sub _1',
             'https://github.com/datalad/testrepo_gh-sub__1'),
            # and on deep subdataset too
            ({},
             'https://github.com/datalad/testrepo_gh/sub _1/d/sub_-  1',
             'https://github.com/datalad/testrepo_gh-sub__1-d-sub_-_1'),
            # test that the presence of another mapping spec doesn't ruin
            # the outcome
            (_nomatch_map,
             'https://github.com/datalad/testrepo_gh/sub _1',
             'https://github.com/datalad/testrepo_gh-sub__1'),
            # verify OSF mapping, but see
            # https://github.com/datalad/datalad/issues/5769 for future
            # implications
            ({},
             'https://osf.io/q8xnk/',
             'osf://q8xnk'),
            ):
        with patch.dict(cfg._merged_store, m):
            eq_(_map_urls(cfg, [i]), [o])
