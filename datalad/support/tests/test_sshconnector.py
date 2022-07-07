# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test classes SSHConnection and SSHManager

"""

import logging
import os.path as op
from os.path import (
    exists,
    getmtime,
    isdir,
)
from os.path import join as opj

from datalad.tests.utils_pytest import (
    SkipTest,
    assert_false,
    assert_in,
    assert_is_instance,
    assert_raises,
    eq_,
    get_most_obscure_supported_name,
    get_ssh_port,
    ok_,
    patch_config,
    skip_if_on_windows,
    skip_nomultiplex_ssh,
    skip_ssh,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path

from ..sshconnector import (
    MultiplexSSHConnection,
    MultiplexSSHManager,
    NoMultiplexSSHConnection,
    SSHConnection,
    SSHManager,
    get_connection_hash,
    sh_quote,
)

# Some tests test the internals and assumptions of multiplex connections
_ssh_manager_is_multiplex = SSHManager is MultiplexSSHManager


@skip_ssh
def test_ssh_get_connection():

    manager = SSHManager()
    if _ssh_manager_is_multiplex:
        assert manager._socket_dir is None, \
            "Should be unset upon initialization. Got %s" % str(manager._socket_dir)
    c1 = manager.get_connection('ssh://datalad-test')

    if _ssh_manager_is_multiplex:
        assert manager._socket_dir, "Should be set after interactions with the manager"
        assert_is_instance(c1, MultiplexSSHConnection)
        # subsequent call returns the very same instance:
        ok_(manager.get_connection('ssh://datalad-test') is c1)
    else:
        assert_is_instance(c1, NoMultiplexSSHConnection)

    # fail on malformed URls (meaning: our fancy URL parser can't correctly
    # deal with them):
    #assert_raises(ValueError, manager.get_connection, 'localhost')
    # we now allow those simple specifications of host to get_connection
    c2 = manager.get_connection('datalad-test')
    assert_is_instance(c2, SSHConnection)

    # but should fail if it looks like something else
    assert_raises(ValueError, manager.get_connection, 'datalad-test/')
    assert_raises(ValueError, manager.get_connection, ':datalad-test')

    # we can do what urlparse cannot
    # assert_raises(ValueError, manager.get_connection, 'someone@localhost')
    # next one is considered a proper url by urlparse (netloc:'',
    # path='/localhost), but eventually gets turned into SSHRI(hostname='ssh',
    # path='/localhost') -- which is fair IMHO -> invalid test
    # assert_raises(ValueError, manager.get_connection, 'ssh:/localhost')

    manager.close()


@skip_if_on_windows
@skip_ssh
@with_tree(tree={'f0': 'f0', 'f1': 'f1'})
@with_tempfile(suffix=get_most_obscure_supported_name(),
               content="1")
def test_ssh_open_close(tmp_path=None, tfile1=None):

    manager = SSHManager()

    socket_path = None
    if _ssh_manager_is_multiplex:
        socket_path = opj(str(manager.socket_dir),
                   get_connection_hash('datalad-test'))
        # TODO: facilitate the test when it didn't exist
        existed_before = exists(socket_path)

    c1 = manager.get_connection('ssh://datalad-test')
    c1.open()
    if socket_path:
        # control master exists for sure now
        ok_(exists(socket_path))

    # use connection to execute remote command:
    # we list explicitly local HOME since we override it in module_setup
    #
    # Note: Use realpath() below because we know that the resolved temporary
    # test directory exists on the target (many tests rely on that), but it
    # doesn't necessarily have the unresolved variant.
    out, err = c1('ls -a {}'.format(sh_quote(op.realpath(tmp_path))))
    remote_ls = [entry for entry in out.splitlines()
                 if entry != '.' and entry != '..']
    eq_(set(remote_ls), {"f0", "f1"})
    if socket_path:
        ok_(exists(socket_path))

    # now test for arguments containing spaces and other pleasant symbols
    out, err = c1('ls -l {}'.format(sh_quote(tfile1)))
    assert_in(tfile1, out)
    # on a crippled FS it will actually say something like
    # Control socket connect(...6258b3a7): Connection refused\r\n'
    # but still work.
    #eq_(err, '')

    c1.close()
    if socket_path:
        # control master doesn't exist anymore:
        ok_(exists(socket_path) == existed_before)


@skip_nomultiplex_ssh
def test_ssh_manager_close():

    manager = SSHManager()

    # check for previously existing sockets:
    existed_before_1 = exists(opj(str(manager.socket_dir),
                                  get_connection_hash('datalad-test')))
    existed_before_2 = exists(opj(str(manager.socket_dir),
                                  get_connection_hash('datalad-test2')))

    manager.get_connection('ssh://datalad-test').open()
    manager.get_connection('ssh://datalad-test2').open()

    if existed_before_1 and existed_before_2:
        # we need one connection to be closed and therefore being opened
        # by `manager`
        manager.get_connection('ssh://datalad-test').close()
        manager.get_connection('ssh://datalad-test').open()

    ok_(exists(opj(str(manager.socket_dir),
                   get_connection_hash('datalad-test'))))
    ok_(exists(opj(str(manager.socket_dir),
                   get_connection_hash('datalad-test2'))))

    manager.close()

    still_exists_1 = exists(opj(str(manager.socket_dir),
                                get_connection_hash('datalad-test')))
    still_exists_2 = exists(opj(str(manager.socket_dir),
                                get_connection_hash('datalad-test2')))

    eq_(existed_before_1, still_exists_1)
    eq_(existed_before_2, still_exists_2)


@with_tempfile
def test_ssh_manager_close_no_throw(bogus_socket=None):
    manager = MultiplexSSHManager()

    class bogus:
        def close(self):
            raise Exception("oh I am so bad")

        @property
        def ctrl_path(self):
            with open(bogus_socket, "w") as f:
                f.write("whatever")
            return Path(bogus_socket)

    # since we are digging into protected area - should also set _prev_connections
    manager._prev_connections = {}
    manager._connections['bogus'] = bogus()
    assert_raises(Exception, manager.close)
    assert_raises(Exception, manager.close)

    # but should proceed just fine if allow_fail=False
    with swallow_logs(new_level=logging.DEBUG) as cml:
        manager.close(allow_fail=False)
        assert_in('Failed to close a connection: oh I am so bad', cml.out)


@skip_if_on_windows
@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(content='one')
@with_tempfile(content='two')
def test_ssh_copy(sourcedir=None, sourcefile1=None, sourcefile2=None):
    port = get_ssh_port('datalad-test')
    remote_url = 'ssh://datalad-test:{}'.format(port)
    manager = SSHManager()
    ssh = manager.get_connection(remote_url)

    # copy content of sourcefile3 to an obscurely named file in sourcedir
    obscure_file = get_most_obscure_supported_name()
    obscure_path = opj(sourcedir, obscure_file)
    with open(obscure_path, 'w') as f:
        f.write('three')

    # copy first two temp files to remote_url:sourcedir
    sourcefiles = [sourcefile1, sourcefile2]
    ssh.put(sourcefiles, opj(remote_url, sourcedir))
    # copy obscure file to remote_url:sourcedir/'<obscure_file_name>.c opy'
    # we copy to a different name because the test setup maps local dir and
    # remote dir to the same directory on the test machine. That means the file
    # is copied onto itself. With ssh version 9 this leads to an empty file.
    # We perform copy instead of just writing the content to the destination
    # file,  because ww want to ensure that the source file is picked up by
    # 'ssh.put()'.
    ssh.put([obscure_path], opj(remote_url, sourcedir, obscure_file + '.c opy'))

    # docs promise that connection is auto-opened in case of multiplex
    if _ssh_manager_is_multiplex:
        ok_(ssh.is_open())

    # recursive copy tempdir to remote_url:targetdir
    targetdir = sourcedir + '.c opy'
    ssh.put(sourcedir, opj(remote_url, targetdir),
            recursive=True, preserve_attrs=True)

    # check if sourcedir copied to remote_url:targetdir
    ok_(isdir(targetdir))
    # check if scp preserved source directory attributes
    # if source_mtime=1.12s, scp -p sets target_mtime = 1.0s, test that
    eq_(getmtime(targetdir), int(getmtime(sourcedir)) + 0.0)

    # check if targetfiles(and its content) exist in remote_url:targetdir,
    # this implies file(s) and recursive directory copying pass
    for targetfile, content in zip(sourcefiles + [obscure_file + '.c opy'],
                                   ['one', 'two', 'three']):
        targetpath = opj(targetdir, targetfile)
        ok_(exists(targetpath))
        with open(targetpath, 'r') as fp:
            eq_(content, fp.read())

    # and now a quick smoke test for get
    # but simplify the most obscure filename slightly to not trip `scp` itself
    togetfile = Path(targetdir) / (obscure_file.replace('`', '') + '2')
    togetfile.write_text(str('something'))
    ssh.get(opj(remote_url, str(togetfile)), sourcedir)
    ok_((Path(sourcedir) / togetfile.name).exists())

    ssh.close()


@skip_if_on_windows
@skip_ssh
def test_ssh_compound_cmds():
    ssh = SSHManager().get_connection('ssh://datalad-test')
    out, err = ssh('[ 1 = 2 ] && echo no || echo success')
    eq_(out.strip(), 'success')
    ssh.close()  # so we get rid of the possibly lingering connections


@skip_if_on_windows
@skip_ssh
def test_ssh_custom_identity_file():
    ifile = "/tmp/dl-test-ssh-id"  # Travis
    if not op.exists(ifile):
        raise SkipTest("Travis-specific '{}' identity file does not exist"
                       .format(ifile))

    with patch_config({"datalad.ssh.identityfile": ifile}):
        with swallow_logs(new_level=logging.DEBUG) as cml:
            manager = SSHManager()
            ssh = manager.get_connection('ssh://datalad-test')
            cmd_out, _ = ssh("echo blah")
            if _ssh_manager_is_multiplex:
                expected_socket = op.join(
                    str(manager.socket_dir),
                    get_connection_hash("datalad-test", identity_file=ifile))
                ok_(exists(expected_socket))
            manager.close()
            assert_in("-i", cml.out)
            assert_in(ifile, cml.out)


@skip_if_on_windows
@skip_ssh
def test_ssh_git_props():
    remote_url = 'ssh://datalad-test'
    manager = SSHManager()
    ssh = manager.get_connection(remote_url)
    # Note: Avoid comparing these versions directly to the versions in
    # external_versions because the ssh://localhost versions detected might
    # differ depending on how git-annex is installed.
    ok_(ssh.get_annex_version())
    ok_(ssh.get_git_version())
    manager.close()  # close possibly still present connections


# situation on our test windows boxes is complicated
# login shell is a POSIX one, path handling and equivalence between
# local and "remote" needs more research
@skip_if_on_windows
@skip_ssh
@with_tempfile(mkdir=True)
def test_bundle_invariance(path=None):
    remote_url = 'ssh://datalad-test'
    manager = SSHManager()
    testfile = Path(path) / 'dummy'
    for flag in (True, False):
        assert_false(testfile.exists())
        ssh = manager.get_connection(remote_url, use_remote_annex_bundle=flag)
        ssh('cd .>{}'.format(str(testfile)))
        ok_(testfile.exists())
        testfile.unlink()
