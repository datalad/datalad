# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import tempfile

from datalad import ssh_manager
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.support.param import Parameter
from datalad.utils import split_cmdline

lgr = logging.getLogger('datalad.sshrun')


@build_doc
class SSHRun(Interface):
    """Run command on remote machines via SSH.

    This is a replacement for a small part of the functionality of SSH.
    In addition to SSH alone, this command can make use of datalad's SSH
    connection management. Its primary use case is to be used with Git
    as 'core.sshCommand' or via "GIT_SSH_COMMAND".

    Configure `datalad.ssh.identityfile` to pass a file to the ssh's -i option.
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
        ipv4=Parameter(
            args=("-4",),
            dest="ipv4",
            doc="use IPv4 addresses only",
            action="store_true"),
        ipv6=Parameter(
            args=("-6",),
            dest="ipv6",
            doc="use IPv6 addresses only",
            action="store_true"),
        options=Parameter(
            args=("-o",),
            metavar="OPTION",
            dest="options",
            doc="configuration option passed to SSH",
            action="append"),
        no_stdin=Parameter(
            args=("-n",),
            action="store_true",
            dest="no_stdin",
            doc="Do not connect stdin to the process"),
    )

    @staticmethod
    def __call__(login, cmd,
                 *,
                 port=None, ipv4=False, ipv6=False, options=None,
                 no_stdin=False):
        lgr.debug("sshrun invoked: login=%r, cmd=%r, port=%r, options=%r, "
                  "ipv4=%r, ipv6=%r, no_stdin=%r",
                  login, cmd, port, options, ipv4, ipv6, no_stdin)
        # Perspective workarounds for git-annex invocation, see
        # https://github.com/datalad/datalad/issues/1456#issuecomment-292641319

        if cmd.startswith("'") and cmd.endswith("'"):
            lgr.debug(
                "Detected additional level of quotations in %r so performing "
                "command line splitting", cmd
            )
            # there is an additional layer of quotes
            # Let's strip them off by splitting the command
            cmd_ = split_cmdline(cmd)
            if len(cmd_) != 1:
                raise RuntimeError(
                    "Obtained more or less than a single argument after "
                    "command line splitting: %s" % repr(cmd_))
            cmd = cmd_[0]
        sshurl = 'ssh://{}{}'.format(
            login,
            ':{}'.format(port) if port else '')

        if ipv4 and ipv6:
            raise ValueError("Cannot force both IPv4 and IPv6")
        elif ipv4:
            force_ip = 4
        elif ipv6:
            force_ip = 6
        else:
            force_ip = None

        ssh = ssh_manager.get_connection(sshurl, force_ip=force_ip)
        # use an empty temp file as stdin if none shall be connected
        stdin_ = tempfile.TemporaryFile() if no_stdin else sys.stdin
        try:
            # We pipe the SSH process' stdout/stderr by means of
            # `log_output=False`. That's necessary to let callers - for example
            # git-clone - communicate with the SSH process. Hence, we expect no
            # output being returned from this call:
            out, err = ssh(cmd, stdin=stdin_, log_output=False, options=options)
            assert not out
            assert not err
        finally:
            if no_stdin:
                stdin_.close()
