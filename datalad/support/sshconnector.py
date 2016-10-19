# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to an ssh connection.

Allows for connecting via ssh and keeping the connection open
(by using a controlmaster), in order to perform several ssh commands or
git calls to a ssh remote without the need to reauthenticate.
"""

import logging
from os.path import exists
from os.path import join as opj
from subprocess import Popen
from shlex import split as sh_split

# !!! Do not import network here -- delay import, allows to shave off 50ms or so
# on initial import datalad time
# from datalad.support.network import RI, is_ssh

from datalad.support.exceptions import CommandError
from datalad.dochelpers import exc_str
from datalad.utils import not_supported_on_windows
from datalad.utils import on_windows
from datalad.utils import assure_dir
from datalad.utils import auto_repr
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.ssh')


def _wrap_str(s):
    """Helper to wrap argument into '' to be passed over ssh cmdline"""
    s = s.replace("'", r'\'')
    return "'%s'" % s


@auto_repr
class SSHConnection(object):
    """Representation of a (shared) ssh connection.
    """

    def __init__(self, ctrl_path, host, port=None):
        """Create the connection.

        This does not actually open the connection.
        It's just its representation.

        Parameters
        ----------
        ctrl_path: str
          path to SSH controlmaster
        host: str
          host to connect to. This may include the user ( [user@]host )
        port: str
          port to connect over
        """
        self._runner = None

        # TODO: This may actually also contain "user@host".
        #       So, better name instead of 'host'?
        self.host = host
        self.ctrl_path = ctrl_path + ":" + port if port else ctrl_path
        self.port = port
        self.ctrl_options = ["-o", "ControlPath=" + self.ctrl_path]

    def __call__(self, cmd, wrap_args=True):
        """Executes a command on the remote.

        Parameters
        ----------
        cmd: list or str
          command to run on the remote

        Returns
        -------
        tuple of str
          stdout, stderr of the command run.
        """

        # TODO: Do we need to check for the connection to be open or just rely
        # on possible ssh failing?
        cmd_list = cmd if isinstance(cmd, list) \
            else sh_split(cmd, posix=not on_windows)
            # windows check currently not needed, but keep it as a reminder
        # The safest best while dealing with any special characters is to wrap
        # entire argument into "" while escaping possibly present " inside.
        # I guess for the ` & and other symbols used in the shell -- yet to figure out
        # how to escape it reliably.
        if wrap_args:
            cmd_list = list(map(_wrap_str, cmd_list))
        ssh_cmd = ["ssh"] + self.ctrl_options + [self.host] + cmd_list

        # TODO: pass expect parameters from above?
        # Hard to explain to toplevel users ... So for now, just set True
        return self.runner.run(ssh_cmd, expect_fail=True, expect_stderr=True)

    @property
    def runner(self):
        if self._runner is None:
            self._runner = Runner()
        return self._runner

    def open(self):
        """Opens the connection.

        In other words: Creates the SSH controlmaster to be used by this
        connection, if it is not there already.
        """

        if exists(self.ctrl_path):
            # check whether controlmaster is still running:
            cmd = ["ssh", "-O", "check"] + self.ctrl_options + [self.host]
            out, err = self.runner.run(cmd)
            if "Master running" not in out:
                # master exists but isn't running
                # => clean up:
                self.close()

        if not exists(self.ctrl_path):
            # set control options
            ctrl_options = ["-o", "ControlMaster=auto",
                            "-o", "ControlPersist=15m"] + self.ctrl_options
            # create ssh control master command
            cmd = ["ssh"] + ctrl_options + [self.host, "exit"]

            # start control master:
            lgr.debug("Try starting control master by calling:\n%s" % cmd)
            proc = Popen(cmd)
            proc.communicate(input="\n")  # why the f.. this is necessary?

    def close(self):
        """Closes the connection.
        """

        # stop controlmaster:
        cmd = ["ssh", "-O", "stop"] + self.ctrl_options + [self.host]
        try:
            self.runner.run(cmd, expect_stderr=True, expect_fail=True)
        except CommandError as e:
            if "No such file or directory" in e.stderr:
                # nothing to clean up
                pass
            else:
                raise

    def copy(self, source, destination, recursive=False, preserve_attrs=False):
        """Copies source file/folder to destination on the remote.

        Parameters
        ----------
        source: str or list
          file/folder path(s) to copy from on local
        destination: str
          file/folder path to copy to on remote

        Returns
        -------
        str
          stdout, stderr of the copy operation.
        """

        # add recursive, preserve_attributes flag if recursive, preserve_attrs set and create scp command
        scp_options = self.ctrl_options + ["-r"] if recursive else self.ctrl_options
        scp_options += ["-p"] if preserve_attrs else []
        scp_cmd = ["scp"] + scp_options

        # add source filepath(s) to scp command
        scp_cmd += source if isinstance(source, list) \
            else [source]

        # add destination path
        scp_cmd += ['%s:"%s"' % (self.host, destination)]
        return self.runner.run(scp_cmd)


@auto_repr
class SSHManager(object):
    """Keeps ssh connections to share. Serves singleton representation
    per connection.
    """

    def __init__(self):
        not_supported_on_windows("TODO: Make this an abstraction to "
                                 "interface platform dependent SSH")

        self._connections = dict()

        self._socket_dir = None

    @property
    def socket_dir(self):
        if self._socket_dir is None:
            from ..config import ConfigManager
            from os import chmod
            cfg = ConfigManager()
            self._socket_dir = opj(cfg.obtain('datalad.locations.cache'),
                                   'sockets')
            assure_dir(self._socket_dir)
            chmod(self._socket_dir, 0o700)

        return self._socket_dir

    def get_connection(self, url):
        """Get a singleton, representing a shared ssh connection to `url`

        Parameters
        ----------
        url: str
          ssh url

        Returns
        -------
        SSHConnection
        """
        # parse url:
        from datalad.support.network import RI, is_ssh
        sshri = RI(url)

        if not is_ssh(sshri):
            raise ValueError("Unsupported SSH URL: '{0}', use ssh://host/path or host:path syntax".format(url))

        # determine control master:
        ctrl_path = "%s/%s" % (self.socket_dir, sshri.hostname)
        if sshri.port:
            ctrl_path += ":%s" % sshri.port

        # do we know it already?
        if ctrl_path in self._connections:
            return self._connections[ctrl_path]
        else:
            c = SSHConnection(ctrl_path, sshri.hostname)
            self._connections[ctrl_path] = c
            return c

    def close(self, allow_fail=True):
        """Closes all connections, known to this instance.

        Parameters
        ----------
        allow_fail: bool, optional
          If True, swallow exceptions which might be thrown during
          connection.close, and just log them at DEBUG level
        """
        if self._connections:
            lgr.debug("Closing %d SSH connections..." % len(self._connections))
            for cnct in self._connections:
                f = self._connections[cnct].close
                if allow_fail:
                    f()
                else:
                    try:
                        f()
                    except Exception as exc:
                        lgr.debug("Failed to close a connection: %s", exc_str(exc))
