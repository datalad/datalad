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
from subprocess import Popen
from shlex import split as sh_split

from six.moves.urllib.parse import urlparse

# TODO: centralize AppDirs (=> datalad.config?)
from appdirs import AppDirs
from datalad.support.exceptions import CommandError
from datalad.utils import not_supported_on_windows
from datalad.utils import on_windows
from datalad.utils import assure_dir
from datalad.utils import auto_repr
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.ssh')


@auto_repr
class SSHConnection(object):
    """Representation of a (shared) ssh connection.
    """

    def __init__(self, ctrl_path, host):
        """Create the connection.

        This does not actually open the connection.
        It's just its representation.

        Parameters
        ----------
        ctrl_path: str
          path to SSH controlmaster

        host: str
          host to connect to. This may include the user ( [user@]host )
        """
        self._runner = None

        # TODO: This may actually also contain "user@host".
        #       So, better name instead of 'host'?
        self.host = host
        self.ctrl_path = ctrl_path
        self.cmd_prefix = ["ssh", "-S", self.ctrl_path, self.host]

    def __call__(self, cmd):
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

        ssh_cmd = self.cmd_prefix + cmd if isinstance(cmd, list) \
            else sh_split(cmd, posix=not on_windows)
            # windows check currently not needed, but keep it as a reminder

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

        # start control master:
        cmd = "ssh -o ControlMaster=auto -o \"ControlPath=%s\" " \
              "-o ControlPersist=yes %s exit" % (self.ctrl_path, self.host)
        lgr.debug("Try starting control master by calling:\n%s" % cmd)
        proc = Popen(cmd, shell=True)
        proc.communicate(input="\n")  # why the f.. this is necessary?

    def close(self):
        """Closes the connection.
        """

        # stop controlmaster:
        cmd = ["ssh", "-O", "stop", "-S", self.ctrl_path, self.host]
        try:
            self.runner.run(cmd, expect_stderr=True, expect_fail=True)
        except CommandError as e:
            if "No such file or directory" in e.stderr:
                # nothing to clean up
                pass
            else:
                raise


@auto_repr
class SSHManager(object):
    """Keeps ssh connections to share. Serves singleton representation
    per connection.
    """

    def __init__(self):
        not_supported_on_windows("TODO: Make this an abstraction to "
                                 "interface platform dependent SSH")

        self._connections = dict()

        self.socket_dir = AppDirs('datalad', 'datalad.org').user_config_dir
        assure_dir(self.socket_dir)

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
        parsed_target = urlparse(url)

        # Note: The following is due to urlparse, not ssh itself!
        # We probably should find a nice way to deal with anything,
        # ssh can handle.
        if parsed_target.scheme != 'ssh':
            raise ValueError("Not an SSH URL: %s" % url)

        if not parsed_target.netloc:
            raise ValueError("Malformed URL (missing host): %s" % url)

        # determine control master:
        ctrl_path = "%s/%s" % (self.socket_dir, parsed_target.netloc)
        if parsed_target.port:
            ctrl_path += ":%s" % parsed_target.port

        # do we know it already?
        if ctrl_path in self._connections:
            return self._connections[ctrl_path]
        else:
            c = SSHConnection(ctrl_path, parsed_target.netloc)
            self._connections[ctrl_path] = c
            return c

    def close(self):
        """Closes all connections, known to this instance.
        """
        if self._connections:
            lgr.debug("Closing %d SSH connections..." % len(self._connections))
            for cnct in self._connections:
                self._connections[cnct].close()

