from datalad.customremotes.ria_utils import (
    UnknownLayoutVersion,
    create_ds_in_store,
    create_store,
    verify_ria_url,
)
from datalad.distributed.ora_remote import (
    LocalIO,
    SSHRemoteIO,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_raises,
    assert_true,
    rmtree,
    skip_ssh,
    with_tempfile,
)
from datalad.utils import (
    Path,
    on_windows,
)


@with_tempfile
def _test_setup_store(io_cls, io_args, store=None):
    io = io_cls(*io_args)
    store = Path(store)
    version_file = store / 'ria-layout-version'
    error_logs = store / 'error_logs'

    # invalid version raises:
    assert_raises(UnknownLayoutVersion, create_store, io, store, '2')

    # non-existing path should work:
    create_store(io, store, '1')
    assert_true(version_file.exists())
    assert_true(error_logs.exists())
    assert_true(error_logs.is_dir())
    assert_equal([f for f in error_logs.iterdir()], [])

    # empty target directory should work as well:
    rmtree(str(store))
    store.mkdir(exist_ok=False)
    create_store(io, store, '1')
    assert_true(version_file.exists())
    assert_true(error_logs.exists())
    assert_true(error_logs.is_dir())
    assert_equal([f for f in error_logs.iterdir()], [])

    # re-execution also fine:
    create_store(io, store, '1')

    # but version conflict with existing target isn't:
    version_file.write_text("2|unknownflags\n")
    assert_raises(ValueError, create_store, io, store, '1')
    # TODO: check output reporting conflicting version "2"


def test_setup_store():

    _test_setup_store(LocalIO, [])

    if on_windows:
        raise SkipTest('ora_remote.SSHRemoteIO stalls on Windows')

    skip_ssh(_test_setup_store)(SSHRemoteIO, ['datalad-test'])


@with_tempfile
def _test_setup_ds_in_store(io_cls, io_args, store=None):
    io = io_cls(*io_args)
    store = Path(store)
    # ATM create_ds_in_store doesn't care what kind of ID is provided
    dsid = "abc123456"

    ds_path = store / dsid[:3] / dsid[3:]  # store layout version 1
    version_file = ds_path / 'ria-layout-version'
    archives = ds_path / 'archives'
    objects = ds_path / 'annex' / 'objects'
    git_config = ds_path / 'config'

    # invalid store version:
    assert_raises(UnknownLayoutVersion,
                  create_ds_in_store, io, store, dsid, '1', 'abc')

    # invalid obj version:
    assert_raises(UnknownLayoutVersion,
                  create_ds_in_store, io, store, dsid, 'abc', '1')

    # version 1
    create_store(io, store, '1')
    create_ds_in_store(io, store, dsid, '1', '1')
    for p in [ds_path, archives, objects]:
        assert_true(p.is_dir(), msg="Not a directory: %s" % str(p))
    for p in [version_file]:
        assert_true(p.is_file(), msg="Not a file: %s" % str(p))
    assert_equal(version_file.read_text(), "1\n")

    # conflicting version exists at target:
    assert_raises(ValueError, create_ds_in_store, io, store, dsid, '2', '1')

    # version 2
    # Note: The only difference between version 1 and 2 are supposed to be the
    #       key paths (dirhashlower vs mixed), which has nothing to do with
    #       setup routine.
    rmtree(str(store))
    create_store(io, store, '1')
    create_ds_in_store(io, store, dsid, '2', '1')
    for p in [ds_path, archives, objects]:
        assert_true(p.is_dir(), msg="Not a directory: %s" % str(p))
    for p in [version_file]:
        assert_true(p.is_file(), msg="Not a file: %s" % str(p))
    assert_equal(version_file.read_text(), "2\n")


def test_setup_ds_in_store():

    _test_setup_ds_in_store(LocalIO, [])

    if on_windows:
        raise SkipTest('ora_remote.SSHRemoteIO stalls on Windows')

    skip_ssh(_test_setup_ds_in_store)(SSHRemoteIO, ['datalad-test'])


def test_verify_ria_url():
    # unsupported protocol
    assert_raises(ValueError,
                  verify_ria_url, 'ria+ftp://localhost/tmp/this', {})
    # bunch of caes that should work
    cases = {
        'ria+file:///tmp/this': (None, '/tmp/this'),
        # no normalization
        'ria+file:///tmp/this/': (None, '/tmp/this/'),
        # with hosts
        'ria+ssh://localhost/tmp/this': ('ssh://localhost', '/tmp/this'),
        'ria+http://localhost/tmp/this': ('http://localhost', '/tmp/this'),
        'ria+https://localhost/tmp/this': ('https://localhost', '/tmp/this'),
        # with username
        'ria+ssh://humbug@localhost/tmp/this':
            ('ssh://humbug@localhost', '/tmp/this'),
        # with port
        'ria+ssh://humbug@localhost:2222/tmp/this':
            ('ssh://humbug@localhost:2222', '/tmp/this'),
        'ria+ssh://localhost:2200/tmp/this':
            ('ssh://localhost:2200', '/tmp/this'),
        # with password
        'ria+https://humbug:1234@localhost:8080/tmp/this':
            ('https://humbug:1234@localhost:8080', '/tmp/this'),
        # document a strange (MIH thinks undesirable), but pre-existing
        # behavior an 'ssh example.com' would end up in the user HOME,
        # not in '/'
        'ria+ssh://example.com': ('ssh://example.com', '/')
    }
    for i, o in cases.items():
        # we are not testing the URL rewriting here
        assert_equal(o, verify_ria_url(i, {})[:2])
