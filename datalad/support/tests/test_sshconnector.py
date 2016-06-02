# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test classes SSHConnection and SSHManager

"""

import os
from os.path import exists, join as opj

from nose.tools import ok_, assert_is_instance

from datalad.support.sshconnector import SSHConnection, SSHManager
from datalad.tests.utils import assert_raises, eq_
from datalad.tests.utils import skip_ssh


@skip_ssh
def test_ssh_get_connection():

    manager = SSHManager()
    c1 = manager.get_connection('ssh://localhost')
    assert_is_instance(c1, SSHConnection)

    # subsequent call returns the very same instance:
    ok_(manager.get_connection('ssh://localhost') is c1)

    # fail on malformed URls (meaning: urlparse can't correctly deal with them):
    assert_raises(ValueError, manager.get_connection, 'localhost')
    assert_raises(ValueError, manager.get_connection, 'someone@localhost')
    assert_raises(ValueError, manager.get_connection, 'ssh:/localhost')


@skip_ssh
def test_ssh_open_close():

    manager = SSHManager()
    c1 = manager.get_connection('ssh://localhost')
    path = opj(manager.socket_dir, 'localhost')
    c1.open()
    # control master exists:
    ok_(exists(path))

    # use connection to execute remote command:
    out, err = c1(['ls', '-a'])
    remote_ls = [entry for entry in out.splitlines() if entry != '.' and entry != '..']
    local_ls = os.listdir(os.path.expanduser('~'))
    eq_(set(remote_ls), set(local_ls))

    c1.close()
    # control master doesn't exist anymore:
    ok_(not exists(path))


@skip_ssh
def test_ssh_manager_close():

    manager = SSHManager()
    manager.get_connection('ssh://localhost').open()
    manager.get_connection('ssh://datalad-test').open()
    ok_(exists(opj(manager.socket_dir, 'localhost')))
    ok_(exists(opj(manager.socket_dir, 'datalad-test')))

    manager.close()

    ok_(not exists(opj(manager.socket_dir, 'localhost')))
    ok_(not exists(opj(manager.socket_dir, 'datalad-test')))



