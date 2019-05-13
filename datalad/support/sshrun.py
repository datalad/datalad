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
import tempfile

from datalad.support.param import Parameter
from datalad.interface.base import Interface
from datalad.interface.base import build_doc

from datalad import ssh_manager

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
    # prevent common args from being added to the docstring
    _no_eval_results = True

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
        no_stdin=Parameter(
            args=("-n",),
            action="store_true",
            dest="no_stdin",
            doc="Do not connect stdin to the process"),
    )

    @staticmethod
    def __call__(login, cmd, port=None, no_stdin=False):
        lgr.debug("sshrun invoked: %r %r %r %r", login, cmd, port, no_stdin)
        # Perspective workarounds for git-annex invocation, see
        # https://github.com/datalad/datalad/issues/1456#issuecomment-292641319
        
        if cmd.startswith("'") and cmd.endswith("'"):
            lgr.debug(
                "Detected additional level of quotations in %r so performing "
                "shlex split", cmd
            )
            # there is an additional layer of quotes
            # Let's strip them off using shlex
            import shlex
            cmd_ = shlex.split(cmd)
            if len(cmd_) != 1:
                raise RuntimeError(
                    "Obtained more or less than a single argument upon shlex "
                    "split: %s" % repr(cmd_))
            cmd = cmd_[0]
        sshurl = 'ssh://{}{}'.format(
            login,
            ':{}'.format(port) if port else '')
        ssh = ssh_manager.get_connection(sshurl)
        # use an empty temp file as stdin if none shall be connected
        stdin_ = tempfile.TemporaryFile() if no_stdin else sys.stdin
        try:
            out, err = ssh(cmd, stdin=stdin_, log_output=False)
        finally:
            if no_stdin:
                stdin_.close()
        os.write(1, out.encode('UTF-8'))
        os.write(2, err.encode('UTF-8'))
