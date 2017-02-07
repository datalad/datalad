# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""SSH command to expose datalad's connection management to 3rd-party tools

Primary use case is to be used with git as core.sshCommand

"""

__docformat__ = 'restructuredtext'


import logging
import os
import sys

from datalad.support.param import Parameter
from datalad.interface.base import Interface

from datalad import ssh_manager


class SSHRun(Interface):
    """Run command on remote machines via SSH.

    This is a replacement for a small part of the functionality of SSH.
    In addition to SSH alaon, this command can make use ofdatalad's SSH
    connection management. Its primary use case is to be used with Git
    as 'core.sshCommand' or via "GIT_SSH_COMMAND".
    """

    _params_ = dict(
        login=Parameter(
            args=("login",),
            doc="[user@]hostname"),
        cmd=Parameter(
            args=("cmd",),
            doc="command for remote execution"),
        port=Parameter(
            args=("-p", '--port'),
            doc="port to connect to on the remote host"),
    )

    @staticmethod
    def __call__(login, cmd, port=None):
        sshurl = 'ssh://{}{}'.format(
            login,
            ':{}'.format(port) if port else '')
        ssh = ssh_manager.get_connection(sshurl)
        out, err = ssh(cmd, stdin=sys.stdin, log_output=False)
        os.write(1, out.encode('UTF-8'))
        os.write(2, err.encode('UTF-8'))
