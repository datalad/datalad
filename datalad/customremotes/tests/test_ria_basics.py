from pathlib import Path
import shutil
import subprocess
import logging
from datalad.interface.results import annexjson2result
from datalad.api import (
    create,
)

from datalad.utils import (
    swallow_logs
)
from datalad.tests.utils import (
    assert_raises,
    assert_repo_status,
    assert_status,
    eq_,
    with_tempfile,
)

from datalad.support.exceptions import (
    IncompleteResultsError
)

from datalad.customremotes.tests.ria_utils import (
    get_all_files,
    initremote,
    initexternalremote,
    populate_dataset,
    setup_archive_remote,
)


@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
def test_archive_layout(path, objtree, archivremote):
    ds = create(path)
    setup_archive_remote(ds.repo, objtree)
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)

    # copy files into the RIA archive
    ds.repo.copy_to('.', 'archive')

    # we should see the exact same annex object tree
    arxiv_files = get_all_files(objtree)
    # anything went there at all?
    assert len(arxiv_files) > 1
    # minus the two layers for the archive path the content is identically
    # structured, except for the two additional version files at the root of the entire tree and at the dataset level
    assert len([p for p in arxiv_files if p.name == 'ria-layout-version']) == 2

    eq_(
        sorted([p.parts[-4:] for p in arxiv_files if p.name != 'ria-layout-version']),
        # Note: datalad-master has ds.repo.dot_git Path object. Not in 0.12.0rc6 though. This would
        # also resolve .git-files, which pathlib obv. can't. If we test more sophisticated structures, we'd need to
        # account for that
        sorted([p.parts for p in get_all_files(ds.pathobj / '.git' / 'annex' / 'objects')])
    )

    # we can simply pack up the content of the directory remote into a
    # 7z archive and place it in the right location to get a functional
    # special remote
    whereis = ds.repo.whereis('one.txt')
    targetpath = Path(archivremote) / ds.id[:3] / ds.id[3:] / 'archives'
    ds.ria_export_archive(targetpath / 'archive.7z')
    initexternalremote(ds.repo, '7z', 'ria', config={'base-path': archivremote})
    # now fsck the new remote to get the new special remote indexed
    ds.repo.fsck(remote='7z', fast=True)
    eq_(len(ds.repo.whereis('one.txt')), len(whereis) + 1)


@with_tempfile(mkdir=True)
@with_tempfile()
@with_tempfile()
def test_backup_archive(path, objtree, archivremote):
    """Similar to test_archive_layout(), but not focused on
    compatibility with the directory-type special remote. Instead,
    it tests build a second RIA remote from an existing one, e.g.
    for backup purposes.
    """
    ds = create(path)
    setup_archive_remote(ds.repo, objtree)
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)

    # copy files into the RIA archive
    ds.repo.copy_to('.', 'archive')

    targetpath = Path(archivremote) / ds.id[:3] / ds.id[3:] / 'archives'
    targetpath.mkdir(parents=True)
    subprocess.run(
        ['7z', 'u', str(targetpath / 'archive.7z'), '.'],
        cwd=str(Path(objtree) / ds.id[:3] / ds.id[3:] / 'annex' / 'objects'),
    )
    initexternalremote(ds.repo, '7z', 'ria', config={'base-path': archivremote})
    # wipe out the initial RIA remote (just for testing if the upcoming
    # one can fully take over)
    shutil.rmtree(objtree)
    # fsck to make git-annex aware of the loss
    assert_status(
        'error',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='archive', fast=True)])
    # now only available "here"
    eq_(len(ds.repo.whereis('one.txt')), 1)

    # make the backup archive known
    initexternalremote(
        ds.repo, 'backup', 'ria', config={'base-path': archivremote})
    # now fsck the new remote to get the new special remote indexed
    assert_status(
        'ok',
        [annexjson2result(r, ds)
         for r in ds.repo.fsck(remote='backup', fast=True)])
    eq_(len(ds.repo.whereis('one.txt')), 2)

    # now we can drop all content locally, reobtain it, and survive an
    # fsck
    ds.drop('.')
    ds.get('.')
    assert_status('ok', [annexjson2result(r, ds) for r in ds.repo.fsck()])


@with_tempfile(mkdir=True)
@with_tempfile()
def test_version_check(path, objtree):

    ds = create(path)
    setup_archive_remote(ds.repo, objtree)
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)

    remote_ds_tree_version_file = Path(objtree) / 'ria-layout-version'
    remote_obj_tree_version_file = Path(objtree) / ds.id[:3] / ds.id[3:] / 'ria-layout-version'

    # Those files are not yet there
    assert not remote_ds_tree_version_file.exists()
    assert not remote_obj_tree_version_file.exists()

    # Now copy everything to remote. This should create the structure including those version files
    ds.repo.copy_to('.', 'archive')
    assert remote_ds_tree_version_file.exists()
    assert remote_obj_tree_version_file.exists()

    # Currently the content of booth should be "2"
    with open(str(remote_ds_tree_version_file), 'r') as f:
        eq_(f.read().strip(), '1')
    with open(str(remote_obj_tree_version_file), 'r') as f:
        eq_(f.read().strip(), '2')

    # Accessing the remote should not yield any output regarding versioning, since it's the "correct" version
    # Note that "fsck" is an arbitrary choice. We need just something to talk to the special remote
    with swallow_logs(new_level=logging.INFO) as cml:
        ds.repo.fsck(remote='archive', fast=True)
        assert not cml.out  # TODO: For some reason didn't get cml.assert_logged to assert "nothing was logged"

    # Now fake-change the version
    with open(str(remote_obj_tree_version_file), 'w') as f:
        f.write('X\n')

    # Now we should see a message about it
    with swallow_logs(new_level=logging.INFO) as cml:
        ds.repo.fsck(remote='archive', fast=True)
        cml.assert_logged(level="INFO", msg="Remote object tree reports version X", regex=False)
        cml.assert_logged(level="INFO", msg="Setting remote to read-only usage", regex=False)

    # reading still works:
    ds.drop('.')
    assert_status('ok', ds.get('.'))

    # but writing doesn't:
    with open(str(Path(ds.path) / 'new_file'), 'w') as f:
        f.write("arbitrary addition")
    ds.save(message="Add a new_file")

    # TODO: use self.annex.error and see whether we get an actual error result
    assert_raises(IncompleteResultsError, ds.repo.copy_to, 'new_file', 'archive')

    # However, we can force it by configuration
    ds.config.add("annex.ria-remote.archive.force-write", "true", where='local')
    ds.repo.copy_to('new_file', 'archive')
