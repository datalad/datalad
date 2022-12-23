# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##


import subprocess

from datalad.api import (
    Dataset,
    clone,
)
from datalad.customremotes.ria_utils import (
    create_ds_in_store,
    create_store,
    get_layout_locations,
)
from datalad.distributed.ora_remote import (
    LocalIO,
    SSHRemoteIO,
)
from datalad.distributed.tests.ria_utils import (
    common_init_opts,
    populate_dataset,
)
from datalad.interface.results import annexjson2result
from datalad.tests.utils_pytest import (
    assert_result_count,
    assert_status,
    eq_,
    known_failure_windows,
    skip_ssh,
    slow,
    with_tempfile,
)
from datalad.utils import (
    Path,
    quote_cmdlinearg,
)


@known_failure_windows  # see gh-4469
@with_tempfile()
@with_tempfile(mkdir=True)
def _test_bare_git_version_1(host, dspath, store):
    # This test should take a dataset and create a bare repository at the remote
    # end from it.
    # Given, that it is placed correctly within a tree of dataset, that remote
    # thing should then be usable as an ora-remote as well as as a git-type
    # remote.
    # Note: Usability of git remote by annex depends on dataset layout version
    #       (dirhashlower vs. -mixed).
    #       For version 1 (lower) upload and consumption should be
    #       interchangeable. It doesn't matter which remote is used for what
    #       direction.
    ds_path = Path(dspath)
    store = Path(store)
    ds = Dataset(ds_path).create()
    populate_dataset(ds)

    bare_repo_path, _, objdir = get_layout_locations(1, store, ds.id)
    # Use git to make sure the remote end is what git thinks a bare clone of it
    # should look like
    subprocess.run(['git', 'clone', '--bare',
                    quote_cmdlinearg(str(dspath)),
                    quote_cmdlinearg(str(bare_repo_path))
                    ])

    if host:
        url = "ria+ssh://{host}{path}".format(host=host,
                                              path=store)
    else:
        url = "ria+{}".format(store.as_uri())
    init_opts = common_init_opts + ['url={}'.format(url)]
    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    create_store(io, store, '1')
    # set up the dataset location, too.
    # Note: Dataset layout version 1 (dirhash lower):
    create_ds_in_store(io, store, ds.id, '1', '1', init_obj_tree=False)

    # Now, let's have the bare repo as a git remote and use it with annex
    git_url = "ssh://{host}{path}".format(host=host, path=bare_repo_path) \
        if host else bare_repo_path.as_uri()
    ds.repo.add_remote('bare-git', git_url)
    ds.repo.enable_remote('bare-git')

    # copy files to the remote
    ds.push('.', to='bare-git')
    eq_(len(ds.repo.whereis('one.txt')), 2)

    # now we can drop all content locally, reobtain it, and survive an
    # fsck
    ds.drop('.')
    ds.get('.')
    assert_status('ok', [annexjson2result(r, ds) for r in ds.repo.fsck()])

    # Now, add the ora remote:
    ds.repo.init_remote('ora-remote', options=init_opts)
    # fsck to make availability known
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='ora-remote', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 3)

    # Now move content from git-remote to local and see it not being available
    # via bare-git anymore.
    ds.repo.call_annex(['move', '--all', '--from=bare-git'])
    # ora-remote doesn't know yet:
    eq_(len(ds.repo.whereis('one.txt')), 2)

    # But after fsck it does:
    fsck_res = [annexjson2result(r, ds)
                for r in ds.repo.fsck(remote='ora-remote', fast=True)]
    assert_result_count(fsck_res,
                        1,
                        status='error',
                        error_message='** Based on the location log, one.txt\n'
                                      '** was expected to be present, '
                                      'but its content is missing.')
    assert_result_count(fsck_res,
                        1,
                        status='error',
                        error_message='** Based on the location log, subdir/two\n'
                                      '** was expected to be present, '
                                      'but its content is missing.')
    eq_(len(ds.repo.whereis('one.txt')), 1)
    # and the other way around: upload via ora-remote and have it available via
    # git-remote:
    ds.push('.', to='ora-remote')
    # fsck to make availability known
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='bare-git', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 3)


@slow  # 12sec + ? on travis
def test_bare_git_version_1():
    # TODO: Skipped due to gh-4436
    known_failure_windows(skip_ssh(_test_bare_git_version_1))('datalad-test')
    _test_bare_git_version_1(None)


@known_failure_windows  # see gh-4469
@with_tempfile()
@with_tempfile(mkdir=True)
def _test_bare_git_version_2(host, dspath, store):
    # Similarly to test_bare_git_version_1, this should ensure a bare git repo
    # at the store location for a dataset doesn't conflict with the ORA remote.
    # Note: Usability of git remote by annex depends on dataset layout version
    #       (dirhashlower vs. -mixed).
    #       For version 2 (mixed) upload via ORA and consumption via git should
    #       work. But not the other way around, since git-annex uses
    #       dirhashlower with bare repos.

    ds_path = Path(dspath)
    store = Path(store)
    ds = Dataset(ds_path).create()
    populate_dataset(ds)

    bare_repo_path, _, objdir = get_layout_locations(1, store, ds.id)
    # Use git to make sure the remote end is what git thinks a bare clone of it
    # should look like
    subprocess.run(['git', 'clone', '--bare',
                    quote_cmdlinearg(str(dspath)),
                    quote_cmdlinearg(str(bare_repo_path))
                    ])

    if host:
        url = "ria+ssh://{host}{path}".format(host=host,
                                              path=store)
    else:
        url = "ria+{}".format(store.as_uri())
    init_opts = common_init_opts + ['url={}'.format(url)]
    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    create_store(io, store, '1')
    # set up the dataset location, too.
    # Note: Dataset layout version 2 (dirhash mixed):
    create_ds_in_store(io, store, ds.id, '2', '1')
    # Avoid triggering a git-annex safety check. See gh-5253.
    assert objdir.is_absolute()
    io.remove_dir(objdir)

    # Now, let's have the bare repo as a git remote
    git_url = "ssh://{host}{path}".format(host=host, path=bare_repo_path) \
        if host else bare_repo_path.as_uri()
    ds.repo.add_remote('bare-git', git_url)
    ds.repo.enable_remote('bare-git')
    # and the ORA remote in addition:
    ds.repo.init_remote('ora-remote', options=init_opts)
    # upload keys via ORA:
    ds.push('.', to='ora-remote')
    # bare-git doesn't know yet:
    eq_(len(ds.repo.whereis('one.txt')), 2)
    # fsck to make availability known
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='bare-git', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 3)
    ds.drop('.')
    eq_(len(ds.repo.whereis('one.txt')), 2)
    # actually consumable via git remote:
    ds.repo.call_annex(['move', 'one.txt', '--from', 'bare-git'])
    eq_(len(ds.repo.whereis('one.txt')), 2)
    # now, move back via git - shouldn't be consumable via ORA
    ds.repo.call_annex(['move', 'one.txt', '--to', 'bare-git'])
    # fsck to make availability known, but there's nothing from POV of ORA:
    fsck_res = [annexjson2result(r, ds)
                for r in ds.repo.fsck(remote='ora-remote', fast=True)]
    assert_result_count(fsck_res,
                        1,
                        status='error',
                        error_message='** Based on the location log, one.txt\n'
                                      '** was expected to be present, '
                                      'but its content is missing.')
    assert_result_count(fsck_res, 3, status='ok')
    eq_(len(fsck_res), 4)
    eq_(len(ds.repo.whereis('one.txt')), 1)


@slow  # 13sec + ? on travis
def test_bare_git_version_2():
    # TODO: Skipped due to gh-4436
    known_failure_windows(skip_ssh(_test_bare_git_version_2))('datalad-test')
    _test_bare_git_version_2(None)

# TODO: Outcommented "old" test from git-annex-ria-remote. This one needs to be
#       revisited after RF'ing to base ORA on proper command abstractions for
#       remote execution

# @skip_if_on_windows
# @with_tempfile
# @with_tempfile(mkdir=True)
# @serve_path_via_http
# @with_tempfile
# @with_tempfile
# @with_tempfile(mkdir=True)
# def test_create_as_bare(origin=None, remote_base_path=None, remote_base_url=None, public=None,
#                         consumer=None, tmp_location=None):
#
#     # Note/TODO: Do we need things like:
#     #    git config receive.denyCurrentBranch updateInstead
#     #    mv .hooks/post-update.sample hooks/post-update
#     #    git update-server-info
#
#     # Test how we build a riaremote from an existing dataset, that is a bare git repo and can be accessed as a git type
#     # remote as well. This should basically outline how to publish to that kind of structure as a data store, that is
#     # autoenabled, so we can publish to github/gitlab and make that storage known.
#
#     remote_base_path = Path(remote_base_path)
#
#     ds = create(origin)
#     populate_dataset(ds)
#     assert_repo_status(ds.path)
#
#     # add the ria remote:
#     # Note: For serve_path_via_http to work (which we need later), the directory needs to already exist.
#     #       But by default ORARemote will reject to create the remote structure in an already existing directory,
#     #       that wasn't created by itself (lacks as ria-layout-version file).
#     #       So, we can either configure force-write here or put a version file in it beforehand.
#     #       However, this is specific to the test environment!
#     with open(str(remote_base_path / 'ria-layout-version'), 'w') as f:
#         f.write('1')
#     initexternalremote(ds.repo, 'riaremote', 'ora', config={'base-path': str(remote_base_path)})
#     # pretty much any annex command that talks to that remote should now trigger the actual creation on the remote end:
#     assert_status(
#         'ok',
#         [annexjson2result(r, ds)
#          for r in ds.repo.fsck(remote='riaremote', fast=True)])
#
#     remote_dataset_path = remote_base_path / ds.id[:3] / ds.id[3:]
#
#     assert remote_base_path.exists()
#     assert remote_dataset_path.exists()
#     ds.push('.', to='riaremote')
#
#     # Now, let's make the remote end a valid, bare git repository
#     eq_(subprocess.run(['git', 'init', '--bare'], cwd=str(remote_dataset_path)).returncode,
#         0)
#
#     #subprocess.run(['mv', 'hooks/post-update.sample', 'hooks/post-update'], cwd=remote_dataset_path)
#     #subprocess.run(['git', 'update-server-info'], cwd=remote_dataset_path)
#
#     # TODO: we might need "mv .hooks/post-update.sample hooks/post-update", "git update-server-info" as well
#     # add as git remote and push everything
#     eq_(subprocess.run(['git', 'remote', 'add', 'bare-git', str(remote_dataset_path)], cwd=origin).returncode,
#         0)
#     # Note: "--mirror" does the job for this test, while it might not be a good default some kind of
#     # datalad-create-sibling. However those things need to be configurable for actual publish/creation routine anyway
#     eq_(subprocess.run(['git', 'push', '--mirror', 'bare-git'], cwd=origin).returncode,
#         0)
#
#     # annex doesn't know the bare-git remote yet:
#     eq_(len(ds.repo.whereis('one.txt')), 2)
#     # But after enableremote and a fsck it does:
#     eq_(subprocess.run(['git', 'annex', 'enableremote', 'bare-git'], cwd=origin).returncode,
#         0)
#     assert_status(
#         'ok',
#         [annexjson2result(r, ds)
#          for r in ds.repo.fsck(remote='bare-git', fast=True)])
#     eq_(len(ds.repo.whereis('one.txt')), 3)
#
#     # we can drop and get again via 'bare-git' remote:
#     ds.drop('.')
#     eq_(len(ds.repo.whereis('one.txt')), 2)
#     eq_(subprocess.run(['git', 'annex', 'get', 'one.txt', '--from', 'bare-git'], cwd=origin).returncode,
#         0)
#     eq_(len(ds.repo.whereis('one.txt')), 3)
#     # let's get the other one from riaremote
#     eq_(len(ds.repo.whereis(op.join('subdir', 'two'))), 2)
#     eq_(subprocess.run(['git', 'annex', 'get', op.join('subdir', 'two'), '--from', 'riaremote'], cwd=origin).returncode,
#         0)
#     eq_(len(ds.repo.whereis(op.join('subdir', 'two'))), 3)
#
#     raise SkipTest("NOT YET DONE")
#     # TODO: Part below still doesn't work. "'storage' is not available" when trying to copy to it. May be the HTTP
#     # Server is not available from within the context of the git-type special remote? Either way, still smells like an
#     # issue with the f****** test setup.
#
#
#
#     # Now, let's try make it a data store for datasets available from elsewhere (like github or gitlab):
#     # For this test, we need a second git remote pointing to remote_dataset_path, but via HTTP.
#     # This is because annex-initremote for a git-type special remote requires a git remote pointing to the same location
#     # and it fails to match local paths. Also doesn't work with file:// scheme.
#     #
#     # TODO: Figure it out in detail. That issue is either a bug or not "real".
#     #
#     # ds.repo._allow_local_urls()
#     # dataset_url = remote_base_url + ds.id[:3] + '/' + ds.id[3:] + '/'
#     # eq_(subprocess.run(['git', 'remote', 'add', 'datasrc', dataset_url],
#     #                    cwd=origin).returncode,
#     #     0)
#     # eq_(subprocess.run(['git', 'annex', 'initremote', 'storage',  'type=git',
#     #                     'location={}'.format(dataset_url), 'autoenable=true'],
#     #                    cwd=origin).returncode,
#     #     0)
#     # assert_status(
#     #     'ok',
#     #     [annexjson2result(r, ds)
#     #      for r in fsck(ds.repo, remote='storage', fast=True)])
