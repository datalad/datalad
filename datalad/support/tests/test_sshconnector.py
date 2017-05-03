# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test classes SSHConnection and SSHManager

"""

import logging
import os
from os.path import exists, isdir, getmtime, join as opj

from datalad.support.external_versions import external_versions

from datalad.tests.utils import assert_raises
from datalad.tests.utils import eq_
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import get_most_obscure_supported_name
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import assert_in
from datalad.tests.utils import ok_
from datalad.tests.utils import assert_is_instance

from ..sshconnector import SSHConnection, SSHManager, sh_quote
from ..sshconnector import get_connection_hash


@skip_ssh
def test_ssh_get_connection():

    manager = SSHManager()
    c1 = manager.get_connection('ssh://localhost')
    assert_is_instance(c1, SSHConnection)

    # subsequent call returns the very same instance:
    ok_(manager.get_connection('ssh://localhost') is c1)

    # fail on malformed URls (meaning: our fancy URL parser can't correctly
    # deal with them):
    assert_raises(ValueError, manager.get_connection, 'localhost')
    # we can do what urlparse cannot
    # assert_raises(ValueError, manager.get_connection, 'someone@localhost')
    # next one is considered a proper url by urlparse (netloc:'',
    # path='/localhost), but eventually gets turned into SSHRI(hostname='ssh',
    # path='/localhost') -- which is fair IMHO -> invalid test
    # assert_raises(ValueError, manager.get_connection, 'ssh:/localhost')

    manager.close()


@skip_ssh
@with_tempfile(suffix=' "`suffix:;& ',  # get_most_obscure_supported_name(),
               content="1")
def test_ssh_open_close(tfile1):

    manager = SSHManager()

    path = opj(manager.socket_dir, get_connection_hash('localhost'))
    # TODO: facilitate the test when it didn't exist
    existed_before = exists(path)
    print("%s existed: %s" % (path, existed_before))

    c1 = manager.get_connection('ssh://localhost')
    c1.open()
    # control master exists for sure now
    ok_(exists(path))

    # use connection to execute remote command:
    out, err = c1('ls -a')
    remote_ls = [entry for entry in out.splitlines()
                 if entry != '.' and entry != '..']
    local_ls = os.listdir(os.path.expanduser('~'))
    eq_(set(remote_ls), set(local_ls))

    # now test for arguments containing spaces and other pleasant symbols
    out, err = c1('ls -l {}'.format(sh_quote(tfile1)))
    assert_in(tfile1, out)
    eq_(err, '')

    c1.close()
    # control master doesn't exist anymore:
    ok_(exists(path) == existed_before)


@skip_ssh
def test_ssh_manager_close():

    manager = SSHManager()

    # check for previously existing sockets:
    existed_before_1 = exists(opj(manager.socket_dir, 'localhost'))
    existed_before_2 = exists(opj(manager.socket_dir, 'datalad-test'))

    manager.get_connection('ssh://localhost').open()
    manager.get_connection('ssh://datalad-test').open()

    if existed_before_1 and existed_before_2:
        # we need one connection to be closed and therefore being opened
        # by `manager`
        manager.get_connection('ssh://localhost').close()
        manager.get_connection('ssh://localhost').open()

    ok_(exists(opj(manager.socket_dir, get_connection_hash('localhost'))))
    ok_(exists(opj(manager.socket_dir, get_connection_hash('datalad-test'))))

    manager.close()

    still_exists_1 = exists(opj(manager.socket_dir, 'localhost'))
    still_exists_2 = exists(opj(manager.socket_dir, 'datalad-test'))

    eq_(existed_before_1, still_exists_1)
    eq_(existed_before_2, still_exists_2)


@with_tempfile
def test_ssh_manager_close_no_throw(bogus_socket):
    manager = SSHManager()

    class bogus:
        def close(self):
            raise Exception("oh I am so bad")

        @property
        def ctrl_path(self):
            with open(bogus_socket, "w") as f:
                f.write("whatever")
            return bogus_socket

    manager._connections['bogus'] = bogus()
    assert_raises(Exception, manager.close)
    assert_raises(Exception, manager.close)

    # but should proceed just fine if allow_fail=False
    with swallow_logs(new_level=logging.DEBUG) as cml:
        manager.close(allow_fail=False)
        assert_in('Failed to close a connection: oh I am so bad', cml.out)


@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(content="one")
@with_tempfile(content="two")
def test_ssh_copy(sourcedir, sourcefile1, sourcefile2):

    remote_url = 'ssh://localhost'
    manager = SSHManager()
    ssh = manager.get_connection(remote_url)
    ssh.open()

    # write to obscurely named file in sourcedir
    obscure_file = opj(sourcedir, get_most_obscure_supported_name())
    with open(obscure_file, 'w') as f:
        f.write("three")

    # copy tempfile list to remote_url:sourcedir
    sourcefiles = [sourcefile1, sourcefile2, obscure_file]
    ssh.copy(sourcefiles, opj(remote_url, sourcedir))

    # recursive copy tempdir to remote_url:targetdir
    targetdir = sourcedir + '.c opy'
    ssh.copy(sourcedir, opj(remote_url, targetdir),
             recursive=True, preserve_attrs=True)

    # check if sourcedir copied to remote_url:targetdir
    ok_(isdir(targetdir))
    # check if scp preserved source directory attributes
    # if source_mtime=1.12s, scp -p sets target_mtime = 1.0s, test that
    eq_(getmtime(targetdir), int(getmtime(sourcedir)) + 0.0)

    # check if targetfiles(and its content) exist in remote_url:targetdir,
    # this implies file(s) and recursive directory copying pass
    for targetfile, content in zip(sourcefiles, ["one", "two", "three"]):
        targetpath = opj(targetdir, targetfile)
        ok_(exists(targetpath))
        with open(targetpath, 'r') as fp:
            eq_(content, fp.read())

    ssh.close()


@skip_ssh
def test_ssh_compound_cmds():
    ssh = SSHManager().get_connection('ssh://localhost')
    out, err = ssh('[ 1 = 2 ] && echo no || echo success')
    eq_(out.strip(), 'success')
    ssh.close()  # so we get rid of the possibly lingering connections


@skip_ssh
def test_ssh_git_props():
    remote_url = 'ssh://localhost'
    manager = SSHManager()
    ssh = manager.get_connection(remote_url)
    eq_(ssh.get_annex_version(),
        external_versions['cmd:annex'])
    # cannot compare to locally detected, might differ depending on
    # how annex was installed
    ok_(ssh.get_git_version())
    manager.close()  # close possibly still present connections
