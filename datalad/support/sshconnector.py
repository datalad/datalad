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
from socket import gethostname
from hashlib import md5
from os.path import exists
from os.path import join as opj
from subprocess import Popen
# importing the quote function here so it can always be imported from this
# module
try:
    # from Python 3.3 onwards
    from shlex import quote as sh_quote
except ImportError:
    # deprecated since Pythonn 2.7
    from pipes import quote as sh_quote

# !!! Do not import network here -- delay import, allows to shave off 50ms or so
# on initial import datalad time
# from datalad.support.network import RI, is_ssh

from datalad.support.exceptions import CommandError
from datalad.dochelpers import exc_str
from datalad.utils import not_supported_on_windows
from datalad.utils import assure_dir
from datalad.utils import auto_repr
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.ssh')


def _wrap_str(s):
    """Helper to wrap argument into '' to be passed over ssh cmdline"""
    s = s.replace("'", r'\'')
    return "'%s'" % s


def get_connection_hash(hostname, port='', username=''):
    """Generate a hash based on SSH connection properties

    This can be used for generating filenames that are unique
    to a connection from and to a particular machine (with
    port and login username). The hash also contains the local
    host name.
    """
    return md5(
        '{lhost}{rhost}{port}{username}'.format(
            lhost=gethostname(),
            rhost=hostname,
            port=port,
            username=username).encode('utf-8')).hexdigest()

@auto_repr
class SSHConnection(object):
    """Representation of a (shared) ssh connection.
    """

    def __init__(self, ctrl_path, sshri):
        """Create a connection handler

        The actual opening of the connection is performed on-demand.

        Parameters
        ----------
        ctrl_path: str
          path to SSH controlmaster
        sshri: SSHRI
          SSH resource identifier (contains all connection-relevant info),
          or another resource identifier that can be converted into an SSHRI.
        """
        self._runner = None

        from datalad.support.network import SSHRI, is_ssh
        if not is_ssh(sshri):
            raise ValueError(
                "Non-SSH resource identifiers are not supported for SSH "
                "connections: {}".format(sshri))
        self.sshri = SSHRI(**{k: v for k, v in sshri.fields.items()
                              if k in ('username', 'hostname', 'port')})
        self.ctrl_path = ctrl_path
        self.ctrl_options = ["-o", "ControlPath=" + self.ctrl_path]
        if self.sshri.port:
            self.ctrl_options += ['-p', '{}'.format(self.sshri.port)]

        # essential properties of the remote system
        self.remote_props = {}

    def __call__(self, cmd, stdin=None, log_output=True):
        """Executes a command on the remote.

        It is the callers responsibility to properly quote commands
        for remote execution (e.g. filename with spaces of other special
        characters). Use the `sh_quote()` from the module for this purpose.

        Parameters
        ----------
        cmd: str
          command to run on the remote

        Returns
        -------
        tuple of str
          stdout, stderr of the command run.
        """

        if not self.is_open():
            self.open()
            # locate annex and set the bundled vs. system Git machinery in motion
            self.get_annex_installdir()

        remote_annex_installdir = self.remote_props.get(
            'installdir:annex', None)
        if remote_annex_installdir:
            # make sure to use the bundled git version if any exists
            cmd = '{}; {}'.format(
                'export "PATH={}:$PATH"'.format(remote_annex_installdir),
                cmd)
        # build SSH call, feed remote command as a single last argument
        # whatever it contains will go to the remote machine for execution
        # we cannot perform any sort of escaping, because it will limit
        # what we can do on the remote, e.g. concatenate commands with '&&'
        ssh_cmd = ["ssh"] + self.ctrl_options
        ssh_cmd += [self.sshri.as_str()] \
            + [cmd]

        if log_output:
            kwargs = dict(log_stdout=True, log_stderr=True, log_online=False)
        else:
            kwargs = dict(log_stdout=False, log_stderr=False, log_online=True)
        # TODO: pass expect parameters from above?
        # Hard to explain to toplevel users ... So for now, just set True
        return self.runner.run(
            ssh_cmd,
            expect_fail=True,
            expect_stderr=True,
            stdin=stdin,
            **kwargs)

    @property
    def runner(self):
        if self._runner is None:
            self._runner = Runner()
        return self._runner

    def is_open(self):
        if not exists(self.ctrl_path):
            return False
        # check whether controlmaster is still running:
        cmd = ["ssh", "-O", "check"] + self.ctrl_options + [self.sshri.as_str()]
        out, err = self.runner.run(cmd)
        if "Master running" not in err:
            # master exists but isn't running
            # => clean up:
            self.close()
            return False
        return True

    def open(self):
        """Opens the connection.

        In other words: Creates the SSH controlmaster to be used by this
        connection, if it is not there already.
        """

        if self.is_open():
            return

        # set control options
        ctrl_options = ["-o", "ControlMaster=auto",
                        "-o", "ControlPersist=15m"] + self.ctrl_options
        # create ssh control master command
        cmd = ["ssh"] + ctrl_options + [self.sshri.as_str(), "exit"]

        # start control master:
        lgr.debug("Try starting control master by calling:\n%s" % cmd)
        proc = Popen(cmd)
        proc.communicate(input="\n")  # why the f.. this is necessary?

    def close(self):
        """Closes the connection.
        """

        # stop controlmaster:
        cmd = ["ssh", "-O", "stop"] + self.ctrl_options + [self.sshri.as_str()]
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
        scp_cmd += ['%s:"%s"' % (self.sshri.hostname, destination)]
        return self.runner.run(scp_cmd)

    def get_annex_installdir(self):
        key = 'installdir:annex'
        if key in self.remote_props:
            return self.remote_props[key]
        annex_install_dir = None
        try:
            annex_install_dir = self(
                # use sh -e to be able to fail at each stage of the process
                "sh -e -c 'dirname $(readlink -f $(which git-annex-shell))'")[0].strip()
        except CommandError as e:
            lgr.debug('Failed to locate remote git-annex installation: %s',
                      exc_str(e))
        self.remote_props[key] = annex_install_dir
        return annex_install_dir

    def get_annex_version(self):
        key = 'cmd:annex'
        if key in self.remote_props:
            return self.remote_props[key]
        try:
            # modern annex versions
            version = self('git annex version --raw')[0]
        except CommandError:
            # either no annex, or old version
            try:
                # fall back on method that could work with older installations
                out, err = self('git annex version')
                version = out.split('\n')[0].split(':')[1].strip()
            except CommandError as e:
                lgr.debug('Failed to determine remote git-annex version: %s',
                          exc_str(e))
                version = None
        self.remote_props[key] = version
        return version

    def get_git_version(self):
        key = 'cmd:git'
        if key in self.remote_props:
            return self.remote_props[key]
        git_version = None
        try:
            git_version = self('git version')[0].split()[2]
        except CommandError as e:
            lgr.debug('Failed to determine Git version: %s',
                      exc_str(e))
        self.remote_props[key] = git_version
        return git_version


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

        from os import listdir
        from os.path import isdir
        self._prev_connections = [opj(self.socket_dir, p)
                                  for p in listdir(self.socket_dir)
                                  if not isdir(opj(self.socket_dir, p))]

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
            raise ValueError("Unsupported SSH URL: '{0}', use "
                             "ssh://host/path or host:path syntax".format(url))

        conhash = get_connection_hash(
            sshri.hostname,
            port=sshri.port,
            username=sshri.username)
        # determine control master:
        ctrl_path = "%s/%s" % (self.socket_dir, conhash)

        # do we know it already?
        if ctrl_path in self._connections:
            return self._connections[ctrl_path]
        else:
            c = SSHConnection(ctrl_path, sshri)
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
            to_close = [c for c in self._connections
                        # don't close if connection wasn't opened by SSHManager
                        if self._connections[c].ctrl_path
                        not in self._prev_connections]
            lgr.debug("Closing %d SSH connections..." % len(to_close))
            for cnct in to_close:
                f = self._connections[cnct].close
                if allow_fail:
                    f()
                else:
                    try:
                        f()
                    except Exception as exc:
                        lgr.debug("Failed to close a connection: "
                                  "%s", exc_str(exc))
