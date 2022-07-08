# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import stat

from datalad.api import (
    Dataset,
    clone,
    create_sibling_ria,
)
from datalad.cmd import NoCapture
from datalad.customremotes.ria_utils import (
    create_ds_in_store,
    create_store,
    get_layout_locations,
)
from datalad.distributed.ora_remote import (
    LocalIO,
    SSHRemoteIO,
    _sanitize_key,
)
from datalad.distributed.tests.ria_utils import (
    common_init_opts,
    get_all_files,
    populate_dataset,
)
from datalad.support.exceptions import CommandError
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_status,
    assert_true,
    has_symlink_capability,
    known_failure_windows,
    serve_path_via_http,
    skip_if_adjusted_branch,
    skip_if_no_network,
    skip_if_root,
    skip_ssh,
    skip_wo_symlink_capability,
    slow,
    swallow_logs,
    turtle,
    with_tempfile,
)
from datalad.utils import Path

# Note, that exceptions to test for are generally CommandError since we are
# talking to the special remote via annex.


@with_tempfile
@with_tempfile
def _test_initremote_basic(url, io, store, ds_path, link):

    ds_path = Path(ds_path)
    store = Path(store)
    link = Path(link)
    ds = Dataset(ds_path).create()
    populate_dataset(ds)

    init_opts = common_init_opts + ['url={}'.format(url)]

    # fails on non-existing storage location
    assert_raises(CommandError,
                  ds.repo.init_remote, 'ria-remote', options=init_opts)
    # Doesn't actually create a remote if it fails
    assert_not_in('ria-remote',
                  [cfg['name']
                   for uuid, cfg in ds.repo.get_special_remotes().items()]
                  )

    # fails on non-RIA URL
    assert_raises(CommandError, ds.repo.init_remote, 'ria-remote',
                  options=common_init_opts + ['url={}'.format(store.as_uri())]
                  )
    # Doesn't actually create a remote if it fails
    assert_not_in('ria-remote',
                  [cfg['name']
                   for uuid, cfg in ds.repo.get_special_remotes().items()]
                  )

    # set up store:
    create_store(io, store, '1')
    # still fails, since ds isn't setup in the store
    assert_raises(CommandError,
                  ds.repo.init_remote, 'ria-remote', options=init_opts)
    # Doesn't actually create a remote if it fails
    assert_not_in('ria-remote',
                  [cfg['name']
                   for uuid, cfg in ds.repo.get_special_remotes().items()]
                  )
    # set up the dataset as well
    create_ds_in_store(io, store, ds.id, '2', '1')
    # now should work
    ds.repo.init_remote('ria-remote', options=init_opts)
    assert_in('ria-remote',
              [cfg['name']
               for uuid, cfg in ds.repo.get_special_remotes().items()]
              )
    assert_repo_status(ds.path)
    # git-annex:remote.log should have:
    #   - url
    #   - common_init_opts
    #   - archive_id (which equals ds id)
    remote_log = ds.repo.call_git(['cat-file', 'blob', 'git-annex:remote.log'],
                                  read_only=True)
    assert_in("url={}".format(url), remote_log)
    [assert_in(c, remote_log) for c in common_init_opts]
    assert_in("archive-id={}".format(ds.id), remote_log)

    # re-configure with invalid URL should fail:
    assert_raises(
        CommandError,
        ds.repo.call_annex,
        ['enableremote', 'ria-remote'] + common_init_opts + [
            'url=ria+file:///non-existing'])
    # but re-configure with valid URL should work
    if has_symlink_capability():
        link.symlink_to(store)
        new_url = 'ria+{}'.format(link.as_uri())
        ds.repo.call_annex(
            ['enableremote', 'ria-remote'] + common_init_opts + [
                'url={}'.format(new_url)])
        # git-annex:remote.log should have:
        #   - url
        #   - common_init_opts
        #   - archive_id (which equals ds id)
        remote_log = ds.repo.call_git(['cat-file', 'blob',
                                       'git-annex:remote.log'],
                                      read_only=True)
        assert_in("url={}".format(new_url), remote_log)
        [assert_in(c, remote_log) for c in common_init_opts]
        assert_in("archive-id={}".format(ds.id), remote_log)

    # we can deal with --sameas, which leads to a special remote not having a
    # 'name' property, but only a 'sameas-name'. See gh-4259
    try:
        ds.repo.init_remote('ora2',
                            options=init_opts + ['--sameas', 'ria-remote'])
    except CommandError as e:
        if 'Invalid option `--sameas' in e.stderr:
            # annex too old - doesn't know --sameas
            pass
        else:
            raise
    # TODO: - check output of failures to verify it's failing the right way
    #       - might require to run initremote directly to get the output


# TODO: Skipped due to gh-4436
@known_failure_windows
@skip_ssh
@with_tempfile
def test_initremote_basic_sshurl(storepath=None):
    _test_initremote_basic(
        'ria+ssh://datalad-test{}'.format(Path(storepath).as_posix()), \
        SSHRemoteIO('datalad-test'), \
        storepath,
    )


# ora remote cannot handle windows file:// URLs
@known_failure_windows
@with_tempfile
def test_initremote_basic_fileurl(storepath=None):
    _test_initremote_basic(
        "ria+{}".format(Path(storepath).as_uri()),
        LocalIO(),
        storepath,
    )


# https://github.com/datalad/datalad/issues/6160
@known_failure_windows
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_initremote_basic_httpurl(storepath=None, storeurl=None):
    _test_initremote_basic(
        f"ria+{storeurl}",
        LocalIO(),
        storepath,
    )


@with_tempfile(mkdir=True)
@serve_path_via_http(use_ssl=True)
def test_initremote_basic_httpsurl(storepath=None, storeurl=None):
    _test_initremote_basic(
        f"ria+{storeurl}",
        LocalIO(),
        storepath,
    )


@skip_wo_symlink_capability
@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
def _test_initremote_alias(host, ds_path, store):

    ds_path = Path(ds_path)
    store = Path(store)
    ds = Dataset(ds_path).create()
    populate_dataset(ds)

    if host:
        url = "ria+ssh://{host}{path}".format(host=host,
                                              path=store)
    else:
        url = "ria+{}".format(store.as_uri())
    init_opts = common_init_opts + ['url={}'.format(url)]

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    create_store(io, store, '1')
    # set up the dataset with alias
    create_ds_in_store(io, store, ds.id, '2', '1', 'ali')
    ds.repo.init_remote('ria-remote', options=init_opts)
    assert_in('ria-remote',
              [cfg['name']
               for uuid, cfg in ds.repo.get_special_remotes().items()]
              )
    assert_repo_status(ds.path)
    assert_true(io.exists(store / "alias" / "ali"))


def test_initremote_alias():

    # TODO: Skipped due to gh-4436
    known_failure_windows(skip_ssh(_test_initremote_alias))('datalad-test')
    _test_initremote_alias(None)



@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
def _test_initremote_rewrite(host, ds_path, store):

    # rudimentary repetition of test_initremote_basic, but
    # with url.<base>.insteadOf config, which should not only
    # be respected, but lead to the rewritten URL stored in
    # git-annex:remote.log

    ds_path = Path(ds_path)
    store = Path(store)
    ds = Dataset(ds_path).create()
    populate_dataset(ds)
    assert_repo_status(ds.path)

    url = "mystore:"
    init_opts = common_init_opts + ['url={}'.format(url)]

    if host:
        replacement = "ria+ssh://{host}{path}".format(host=host,
                                                      path=store)
    else:
        replacement = "ria+{}".format(store.as_uri())

    ds.config.set("url.{}.insteadOf".format(replacement), url, scope='local')

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    create_store(io, store, '1')
    create_ds_in_store(io, store, ds.id, '2', '1')

    # run initremote and check what's stored:
    ds.repo.init_remote('ria-remote', options=init_opts)
    assert_in('ria-remote',
              [cfg['name']
               for uuid, cfg in ds.repo.get_special_remotes().items()]
              )
    # git-annex:remote.log should have:
    #   - rewritten url
    #   - common_init_opts
    #   - archive_id (which equals ds id)
    remote_log = ds.repo.call_git(['cat-file', 'blob', 'git-annex:remote.log'],
                                  read_only=True)
    assert_in("url={}".format(replacement), remote_log)
    [assert_in(c, remote_log) for c in common_init_opts]
    assert_in("archive-id={}".format(ds.id), remote_log)


def test_initremote_rewrite():
    # TODO: Skipped due to gh-4436
    known_failure_windows(skip_ssh(_test_initremote_rewrite))('datalad-test')
    _test_initremote_rewrite(None)


@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
@with_tempfile
def _test_remote_layout(host, dspath, store, archiv_store):

    dspath = Path(dspath)
    store = Path(store)
    archiv_store = Path(archiv_store)
    ds = Dataset(dspath).create()
    populate_dataset(ds)
    assert_repo_status(ds.path)

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    if host:
        store_url = "ria+ssh://{host}{path}".format(host=host,
                                                    path=store)
        arch_url = "ria+ssh://{host}{path}".format(host=host,
                                                   path=archiv_store)
    else:
        store_url = "ria+{}".format(store.as_uri())
        arch_url = "ria+{}".format(archiv_store.as_uri())

    create_store(io, store, '1')

    # TODO: Re-establish test for version 1
    # version 2: dirhash
    create_ds_in_store(io, store, ds.id, '2', '1')

    # add special remote
    init_opts = common_init_opts + ['url={}'.format(store_url)]
    ds.repo.init_remote('store', options=init_opts)

    # copy files into the RIA store
    ds.push('.', to='store')

    # we should see the exact same annex object tree
    dsgit_dir, archive_dir, dsobj_dir = \
        get_layout_locations(1, store, ds.id)
    store_objects = get_all_files(dsobj_dir)
    local_objects = get_all_files(ds.pathobj / '.git' / 'annex' / 'objects')
    assert_equal(len(store_objects), 4)

    if not ds.repo.is_managed_branch():
        # with managed branches the local repo uses hashdirlower instead
        # TODO: However, with dataset layout version 1 this should therefore
        #       work on adjusted branch the same way
        # TODO: Wonder whether export-archive-ora should account for that and
        #       rehash according to target layout.
        assert_equal(sorted([p for p in store_objects]),
                     sorted([p for p in local_objects])
                     )

        if not io.get_7z():
            raise SkipTest("No 7z available in RIA store")

        # we can simply pack up the content of the remote into a
        # 7z archive and place it in the right location to get a functional
        # archive remote

        create_store(io, archiv_store, '1')
        create_ds_in_store(io, archiv_store, ds.id, '2', '1')

        whereis = ds.repo.whereis('one.txt')
        dsgit_dir, archive_dir, dsobj_dir = \
            get_layout_locations(1, archiv_store, ds.id)
        ds.export_archive_ora(archive_dir / 'archive.7z')
        init_opts = common_init_opts + ['url={}'.format(arch_url)]
        ds.repo.init_remote('archive', options=init_opts)
        # now fsck the new remote to get the new special remote indexed
        ds.repo.fsck(remote='archive', fast=True)
        assert_equal(len(ds.repo.whereis('one.txt')), len(whereis) + 1)
        # test creating an archive with filters on files
        ds.export_archive_ora(archive_dir / 'archive2.7z', annex_wanted='(include=*.txt)')
        # test with wanted expression of a specific remote
        ds.repo.set_preferred_content("wanted", "include=subdir/*", remote="store")
        ds.export_archive_ora(archive_dir / 'archive3.7z', remote="store")
        # test with the current sha
        ds.export_archive_ora(
            archive_dir / 'archive4.7z',
            froms=ds.repo.get_revisions()[1],
            )


@slow  # 12sec + ? on travis
# TODO: Skipped due to gh-4436
@known_failure_windows
@skip_ssh
def test_remote_layout_ssh():
    _test_remote_layout('datalad-test')

def test_remote_layout():
    _test_remote_layout(None)


@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
def _test_version_check(host, dspath, store):

    dspath = Path(dspath)
    store = Path(store)

    ds = Dataset(dspath).create()
    populate_dataset(ds)
    assert_repo_status(ds.path)

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    if host:
        store_url = "ria+ssh://{host}{path}".format(host=host,
                                                    path=store)
    else:
        store_url = "ria+{}".format(store.as_uri())

    create_store(io, store, '1')

    # TODO: Re-establish test for version 1
    # version 2: dirhash
    create_ds_in_store(io, store, ds.id, '2', '1')

    # add special remote
    init_opts = common_init_opts + ['url={}'.format(store_url)]
    ds.repo.init_remote('store', options=init_opts)
    ds.push('.', to='store')

    # check version files
    remote_ds_tree_version_file = store / 'ria-layout-version'
    dsgit_dir, archive_dir, dsobj_dir = \
        get_layout_locations(1, store, ds.id)
    remote_obj_tree_version_file = dsgit_dir / 'ria-layout-version'

    assert_true(remote_ds_tree_version_file.exists())
    assert_true(remote_obj_tree_version_file.exists())

    with open(str(remote_ds_tree_version_file), 'r') as f:
        assert_equal(f.read().strip(), '1')
    with open(str(remote_obj_tree_version_file), 'r') as f:
        assert_equal(f.read().strip(), '2')

    # Accessing the remote should not yield any output regarding versioning,
    # since it's the "correct" version. Note that "fsck" is an arbitrary choice.
    # We need just something to talk to the special remote.
    with swallow_logs(new_level=logging.INFO) as cml:
        ds.repo.fsck(remote='store', fast=True)
        # TODO: For some reason didn't get cml.assert_logged to assert
        #       "nothing was logged"
        assert not cml.out

    # Now fake-change the version
    with open(str(remote_obj_tree_version_file), 'w') as f:
        f.write('X\n')

    # Now we should see a message about it
    with swallow_logs(new_level=logging.INFO) as cml:
        ds.repo.fsck(remote='store', fast=True)
        cml.assert_logged(level="INFO",
                          msg="Remote object tree reports version X",
                          regex=False)

    # reading still works:
    ds.drop('.')
    assert_status('ok', ds.get('.'))

    # but writing doesn't:
    with open(str(Path(ds.path) / 'new_file'), 'w') as f:
        f.write("arbitrary addition")
    ds.save(message="Add a new_file")

    # TODO: use self.annex.error in special remote and see whether we get an
    #       actual error result
    with assert_raises(CommandError):
        ds.push('new_file', to='store')

    # However, we can force it by configuration
    ds.config.add("annex.ora-remote.store.force-write", "true", scope='local')
    ds.push('new_file', to='store')


@slow  # 17sec + ? on travis
@skip_ssh
@known_failure_windows
def test_version_check_ssh():
    # TODO: Skipped due to gh-4436
    _test_version_check('datalad-test')

def test_version_check():
    _test_version_check(None)


# git-annex-testremote is way too slow on crippled FS.
# Use is_managed_branch() as a proxy and skip only here
# instead of in a decorator
@skip_if_adjusted_branch
@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
def _test_gitannex(host, store, dspath):
    store = Path(store)

    dspath = Path(dspath)
    store = Path(store)

    ds = Dataset(dspath).create()

    populate_dataset(ds)
    assert_repo_status(ds.path)

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    if host:
        store_url = "ria+ssh://{host}{path}".format(host=host,
                                                    path=store)
    else:
        store_url = "ria+{}".format(store.as_uri())

    create_store(io, store, '1')

    # TODO: Re-establish test for version 1
    # version 2: dirhash
    create_ds_in_store(io, store, ds.id, '2', '1')

    # add special remote
    init_opts = common_init_opts + ['url={}'.format(store_url)]
    ds.repo.init_remote('store', options=init_opts)

    from datalad.support.external_versions import external_versions
    if '8.20200330' < external_versions['cmd:annex'] < '8.20200624':
        # https://git-annex.branchable.com/bugs/testremote_breeds_way_too_many_instances_of_the_externals_remote/?updated
        raise SkipTest(
            "git-annex might lead to overwhelming number of external "
            "special remote instances")

    # run git-annex-testremote
    # note, that we don't want to capture output. If something goes wrong we
    # want to see it in test build's output log.
    ds.repo._call_annex(['testremote', 'store'], protocol=NoCapture)


@turtle
@known_failure_windows # TODO: Skipped due to gh-4436
@skip_ssh
def test_gitannex_ssh():
    _test_gitannex('datalad-test')


@slow  # 41sec on travis
def test_gitannex_local():
    _test_gitannex(None)


@known_failure_windows  # see gh-4469
@with_tempfile
@with_tempfile
def _test_binary_data(host, store, dspath):
    # make sure, special remote deals with binary data and doesn't
    # accidentally involve any decode/encode etc.

    dspath = Path(dspath)
    store = Path(store)

    url = "https://github.com/datalad/example-dicom-functional/blob/master/dicoms/MR.1.3.46.670589.11.38317.5.0.4476.2014042516042547586"
    file = "dicomfile"
    ds = Dataset(dspath).create()
    ds.download_url(url, path=file, message="Add DICOM file from github")
    assert_repo_status(ds.path)

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    if host:
        store_url = "ria+ssh://{host}{path}".format(host=host,
                                                    path=store)
    else:
        store_url = "ria+{}".format(store.as_uri())

    create_store(io, store, '1')
    create_ds_in_store(io, store, ds.id, '2', '1')

    # add special remote
    init_opts = common_init_opts + ['url={}'.format(store_url)]
    ds.repo.init_remote('store', options=init_opts)

    # actual data transfer (both directions)
    # Note, that we intentionally call annex commands instead of
    # datalad-publish/-get here. We are testing an annex-special-remote.

    store_uuid = ds.siblings(name='store',
                             return_type='item-or-list')['annex-uuid']
    here_uuid = ds.siblings(name='here',
                            return_type='item-or-list')['annex-uuid']

    known_sources = ds.repo.whereis(str(file))
    assert_in(here_uuid, known_sources)
    assert_not_in(store_uuid, known_sources)
    ds.repo.call_annex(['move', str(file), '--to', 'store'])
    known_sources = ds.repo.whereis(str(file))
    assert_not_in(here_uuid, known_sources)
    assert_in(store_uuid, known_sources)
    ds.repo.call_annex(['get', str(file), '--from', 'store'])
    known_sources = ds.repo.whereis(str(file))
    assert_in(here_uuid, known_sources)
    assert_in(store_uuid, known_sources)


def test_binary_data():
    # TODO: Skipped due to gh-4436
    known_failure_windows(skip_ssh(_test_binary_data))('datalad-test')
    skip_if_no_network(_test_binary_data)(None)


@known_failure_windows
@with_tempfile
@with_tempfile
@with_tempfile
def test_push_url(storepath=None, dspath=None, blockfile=None):

    dspath = Path(dspath)
    store = Path(storepath)
    blockfile = Path(blockfile)
    blockfile.touch()

    ds = Dataset(dspath).create()
    populate_dataset(ds)
    assert_repo_status(ds.path)

    # set up store:
    io = LocalIO()
    store_url = "ria+{}".format(store.as_uri())
    create_store(io, store, '1')
    create_ds_in_store(io, store, ds.id, '2', '1')

    # initremote fails with invalid url (not a ria+ URL):
    invalid_url = (store.parent / "non-existent").as_uri()
    init_opts = common_init_opts + ['url={}'.format(store_url),
                                    'push-url={}'.format(invalid_url)]
    assert_raises(CommandError, ds.repo.init_remote, 'store', options=init_opts)

    # initremote succeeds with valid but inaccessible URL (pointing to a file
    # instead of a store):
    block_url = "ria+" + blockfile.as_uri()
    init_opts = common_init_opts + ['url={}'.format(store_url),
                                    'push-url={}'.format(block_url)]
    ds.repo.init_remote('store', options=init_opts)

    # but a push will fail:
    assert_raises(CommandError, ds.repo.call_annex,
                  ['copy', 'one.txt', '--to', 'store'])

    # reconfigure with correct push-url:
    init_opts = common_init_opts + ['url={}'.format(store_url),
                                    'push-url={}'.format(store_url)]
    ds.repo.enable_remote('store', options=init_opts)

    # push works now:
    ds.repo.call_annex(['copy', 'one.txt', '--to', 'store'])

    store_uuid = ds.siblings(name='store',
                             return_type='item-or-list')['annex-uuid']
    here_uuid = ds.siblings(name='here',
                            return_type='item-or-list')['annex-uuid']

    known_sources = ds.repo.whereis('one.txt')
    assert_in(here_uuid, known_sources)
    assert_in(store_uuid, known_sources)


# create-sibling-ria cannot handle windows paths
@known_failure_windows
@with_tempfile
@with_tempfile
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_url_keys(dspath=None, storepath=None, httppath=None, httpurl=None):
    ds = Dataset(dspath).create()
    repo = ds.repo
    filename = 'url_no_size.html'
    # URL-type key without size
    repo.call_annex([
        'addurl', '--relaxed', '--raw', '--file', filename, httpurl,
    ])
    ds.save()
    # copy target
    ds.create_sibling_ria(
        name='ria',
        url='ria+file://{}'.format(storepath),
        storage_sibling='only',
        new_store_ok=True
    )
    ds.get(filename)
    repo.call_annex(['copy', '--to', 'ria', filename])
    ds.drop(filename)
    # in the store and on the web
    assert_equal(len(ds.repo.whereis(filename)), 2)
    # try download, but needs special permissions to even be attempted
    ds.config.set('annex.security.allow-unverified-downloads', 'ACKTHPPT', scope='local')
    repo.call_annex(['copy', '--from', 'ria', filename])
    assert_equal(len(ds.repo.whereis(filename)), 3)
    # smoke tests that execute the remaining pieces with the URL key
    repo.call_annex(['fsck', '-f', 'ria'])
    assert_equal(len(ds.repo.whereis(filename)), 3)
    # mapped key in whereis output
    assert_in('127.0.0.1', repo.call_annex(['whereis', filename]))

    repo.call_annex(['move', '-f', 'ria', filename])
    # check that it does not magically reappear, because it actually
    # did not drop the file
    repo.call_annex(['fsck', '-f', 'ria'])
    assert_equal(len(ds.repo.whereis(filename)), 2)


def test_sanitize_key():
    for i, o in (
                ('http://example.com/', 'http&c%%example.com%'),
                ('/%&:', '%&s&a&c'),
            ):
        assert_equal(_sanitize_key(i), o)


# Skipping on adjusted branch as a proxy for crippledFS. Write permissions of
# the owner on a directory can't be revoked on VFAT. "adjusted branch" is a
# bit broad but covers the CI cases. And everything RIA/ORA doesn't currently
# properly run on crippled/windows anyway. Needs to be more precise when
# RF'ing will hopefully lead to support on windows in principle.
@skip_if_adjusted_branch
@known_failure_windows
@with_tempfile
@with_tempfile
def _test_permission(host, storepath, dspath):

    # Test whether ORA correctly revokes and obtains write permissions within
    # the annex object tree. That is: Revoke after ORA pushed a key to store
    # in order to allow the object tree to safely be used with an ephemeral
    # clone. And on removal obtain write permissions, like annex would
    # internally on a drop (but be sure to restore if something went wrong).

    dspath = Path(dspath)
    storepath = Path(storepath)
    ds = Dataset(dspath).create()
    populate_dataset(ds)
    ds.save()
    assert_repo_status(ds.path)
    testfile = 'one.txt'

    # set up store:
    io = SSHRemoteIO(host) if host else LocalIO()
    if host:
        store_url = "ria+ssh://{host}{path}".format(host=host,
                                                    path=storepath)
    else:
        store_url = "ria+{}".format(storepath.as_uri())

    create_store(io, storepath, '1')
    create_ds_in_store(io, storepath, ds.id, '2', '1')
    _, _, obj_tree = get_layout_locations(1, storepath, ds.id)
    assert_true(obj_tree.is_dir())
    file_key_in_store = obj_tree / 'X9' / '6J' / 'MD5E-s8--7e55db001d319a94b0b713529a756623.txt' / 'MD5E-s8--7e55db001d319a94b0b713529a756623.txt'

    init_opts = common_init_opts + ['url={}'.format(store_url)]
    ds.repo.init_remote('store', options=init_opts)

    store_uuid = ds.siblings(name='store',
                             return_type='item-or-list')['annex-uuid']
    here_uuid = ds.siblings(name='here',
                            return_type='item-or-list')['annex-uuid']

    known_sources = ds.repo.whereis(testfile)
    assert_in(here_uuid, known_sources)
    assert_not_in(store_uuid, known_sources)
    assert_false(file_key_in_store.exists())

    ds.repo.call_annex(['copy', testfile, '--to', 'store'])
    known_sources = ds.repo.whereis(testfile)
    assert_in(here_uuid, known_sources)
    assert_in(store_uuid, known_sources)
    assert_true(file_key_in_store.exists())

    # Revoke write permissions from parent dir in-store to test whether we
    # still can drop (if we can obtain the permissions). Note, that this has
    # no effect on VFAT.
    file_key_in_store.parent.chmod(file_key_in_store.parent.stat().st_mode &
                                   ~stat.S_IWUSR)
    # we can't directly delete; key in store should be protected
    assert_raises(PermissionError, file_key_in_store.unlink)

    # ORA can still drop, since it obtains permission to:
    ds.repo.call_annex(['drop', testfile, '--from', 'store'])
    known_sources = ds.repo.whereis(testfile)
    assert_in(here_uuid, known_sources)
    assert_not_in(store_uuid, known_sources)
    assert_false(file_key_in_store.exists())


@skip_ssh
def test_obtain_permission_ssh():
    _test_permission('datalad-test')

@skip_if_root
def test_obtain_permission_root():
    _test_permission(None)
