from pathlib import Path
import os.path as op
import subprocess
from datalad.interface.results import annexjson2result
from datalad.api import (
    create,
)
from datalad.tests.utils import (
    assert_repo_status,
    assert_result_count,
    assert_status,
    eq_,
    serve_path_via_http,
    skip_if_on_windows,
    SkipTest,
    with_tempfile,
)
from datalad.customremotes.tests.ria_utils import (
    initexternalremote,
    populate_dataset,
    skip_non_ssh
)


@skip_if_on_windows
@skip_non_ssh  # superfluous in an SSH-run and annex-testremote is slow
@with_tempfile(mkdir=True)
@with_tempfile()
def test_bare_git(origin, remote_base_path):

    remote_base_path = Path(remote_base_path)

    # This test should take a dataset and create a bare repository at the remote end from it.
    # Given, that it is placed correctly within a tree of dataset, that remote thing should then be usable as a
    # ria-remote as well as as a git-type remote

    ds = create(origin)
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)

    # Use git to make sure the remote end is what git thinks a bare clone of it should look like
    bare_repo_path = remote_base_path / ds.id[:3] / ds.id[3:]
    subprocess.run(['git', 'clone', '--bare', origin, str(bare_repo_path)])

    # Now, let's have the bare repo as a git remote and use it with annex
    eq_(subprocess.run(['git', 'remote', 'add', 'bare-git', str(bare_repo_path)], cwd=origin).returncode,
        0)
    eq_(subprocess.run(['git', 'annex', 'enableremote', 'bare-git'], cwd=origin).returncode,
        0)
    eq_(subprocess.run(['git', 'annex', 'testremote', 'bare-git'], cwd=origin).returncode,
        0)
    # copy files to the remote
    ds.repo.copy_to('.', 'bare-git')
    eq_(len(ds.repo.whereis('one.txt')), 2)

    # now we can drop all content locally, reobtain it, and survive an
    # fsck
    ds.drop('.')
    ds.get('.')
    assert_status('ok', [annexjson2result(r, ds) for r in ds.repo.fsck()])

    # Since we created the remote this particular way instead of letting ria-remote create it, we need to put
    # ria-layout-version files into it. Then we should be able to also add it as a ria-remote.
    with open(str(remote_base_path / 'ria-layout-version'), 'w') as f:
        f.write('1')
    with open(str(bare_repo_path / 'ria-layout-version'), 'w') as f:
        f.write('1')

    # Now, add the ria remote:
    initexternalremote(ds.repo, 'riaremote', 'ria', config={'base-path': str(remote_base_path)})
    # fsck to make availability known
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='riaremote', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 3)

    # Now move content from git-remote to local and see it not being available via bare-git anymore
    eq_(subprocess.run(['git', 'annex', 'move', '--all', '--from=bare-git'], cwd=origin).returncode,
        0)
    # ria-remote doesn't know yet:
    eq_(len(ds.repo.whereis('one.txt')), 2)

    # But after fsck it does:
    fsck_res = [annexjson2result(r, ds) for r in ds.repo.fsck(remote='riaremote', fast=True)]
    assert_result_count(fsck_res,
                        1,
                        status='error',
                        message='** Based on the location log, one.txt\n** was expected to be present, '
                                'but its content is missing.')
    assert_result_count(fsck_res,
                        1,
                        status='error',
                        message='** Based on the location log, subdir/two\n** was expected to be present, '
                                'but its content is missing.')

    eq_(len(ds.repo.whereis('one.txt')), 1)


@skip_if_on_windows
@with_tempfile
@with_tempfile(mkdir=True)
@serve_path_via_http
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
def test_create_as_bare(origin, remote_base_path, remote_base_url, public, consumer, tmp_location):

    # Note/TODO: Do we need things like:
    #    git config receive.denyCurrentBranch updateInstead
    #    mv .hooks/post-update.sample hooks/post-update
    #    git update-server-info

    # Test how we build a riaremote from an existing dataset, that is a bare git repo and can be accessed as a git type
    # remote as well. This should basically outline how to publish to that kind of structure as a data store, that is
    # autoenabled, so we can publish to github/gitlab and make that storage known.

    remote_base_path = Path(remote_base_path)

    ds = create(origin)
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)

    # add the ria remote:
    # Note: For serve_path_via_http to work (which we need later), the directory needs to already exist.
    #       But by default RIARemote will reject to create the remote structure in an already existing directory,
    #       that wasn't created by itself (lacks as ria-layout-version file).
    #       So, we can either configure force-write here or put a version file in it beforehand.
    #       However, this is specific to the test environment!
    with open(str(remote_base_path / 'ria-layout-version'), 'w') as f:
        f.write('1')
    initexternalremote(ds.repo, 'riaremote', 'ria', config={'base-path': str(remote_base_path)})
    # pretty much any annex command that talks to that remote should now trigger the actual creation on the remote end:
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='riaremote', fast=True)])

    remote_dataset_path = remote_base_path / ds.id[:3] / ds.id[3:]

    assert remote_base_path.exists()
    assert remote_dataset_path.exists()
    ds.repo.copy_to('.', 'riaremote')

    # Now, let's make the remote end a valid, bare git repository
    eq_(subprocess.run(['git', 'init', '--bare'], cwd=str(remote_dataset_path)).returncode,
        0)

    #subprocess.run(['mv', 'hooks/post-update.sample', 'hooks/post-update'], cwd=remote_dataset_path)
    #subprocess.run(['git', 'update-server-info'], cwd=remote_dataset_path)

    # TODO: we might need "mv .hooks/post-update.sample hooks/post-update", "git update-server-info" as well
    # add as git remote and push everything
    eq_(subprocess.run(['git', 'remote', 'add', 'bare-git', str(remote_dataset_path)], cwd=origin).returncode,
        0)
    # Note: "--mirror" does the job for this test, while it might not be a good default some kind of
    # datalad-create-sibling. However those things need to be configurable for actual publish/creation routine anyway
    eq_(subprocess.run(['git', 'push', '--mirror', 'bare-git'], cwd=origin).returncode,
        0)

    # annex doesn't know the bare-git remote yet:
    eq_(len(ds.repo.whereis('one.txt')), 2)
    # But after enableremote and a fsck it does:
    eq_(subprocess.run(['git', 'annex', 'enableremote', 'bare-git'], cwd=origin).returncode,
        0)
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='bare-git', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 3)

    # we can drop and get again via 'bare-git' remote:
    ds.drop('.')
    eq_(len(ds.repo.whereis('one.txt')), 2)
    eq_(subprocess.run(['git', 'annex', 'get', 'one.txt', '--from', 'bare-git'], cwd=origin).returncode,
        0)
    eq_(len(ds.repo.whereis('one.txt')), 3)
    # let's get the other one from riaremote
    eq_(len(ds.repo.whereis(op.join('subdir', 'two'))), 2)
    eq_(subprocess.run(['git', 'annex', 'get', op.join('subdir', 'two'), '--from', 'riaremote'], cwd=origin).returncode,
        0)
    eq_(len(ds.repo.whereis(op.join('subdir', 'two'))), 3)

    raise SkipTest("NOT YET DONE")
    # TODO: Part below still doesn't work. "'storage' is not available" when trying to copy to it. May be the HTTP
    # Server is not available from within the context of the git-type special remote? Either way, still smells like an
    # issue with the f****** test setup.



    # Now, let's try make it a data store for datasets available from elsewhere (like github or gitlab):
    # For this test, we need a second git remote pointing to remote_dataset_path, but via HTTP.
    # This is because annex-initremote for a git-type special remote requires a git remote pointing to the same location
    # and it fails to match local paths. Also doesn't work with file:// scheme.
    #
    # TODO: Figure it out in detail. That issue is either a bug or not "real".
    #
    # ds.repo._allow_local_urls()
    # dataset_url = remote_base_url + ds.id[:3] + '/' + ds.id[3:] + '/'
    # eq_(subprocess.run(['git', 'remote', 'add', 'datasrc', dataset_url],
    #                    cwd=origin).returncode,
    #     0)
    # eq_(subprocess.run(['git', 'annex', 'initremote', 'storage',  'type=git',
    #                     'location={}'.format(dataset_url), 'autoenable=true'],
    #                    cwd=origin).returncode,
    #     0)
    # assert_status(
    #     'ok',
    #     [annexjson2result(r, ds)
    #      for r in fsck(ds.repo, remote='storage', fast=True)])
