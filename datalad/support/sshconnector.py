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
from os import remove
from os.path import exists
from os.path import join as opj
from subprocess import Popen
# importing the quote function here so it can always be imported from this
# module
from six.moves import shlex_quote as sh_quote

# !!! Do not import network here -- delay import, allows to shave off 50ms or so
# on initial import datalad time
# from datalad.support.network import RI, is_ssh

from datalad.support.exceptions import CommandError
from datalad.dochelpers import exc_str
from datalad.utils import assure_dir
from datalad.utils import auto_repr
from datalad.cmd import Runner

lgr = logging.getLogger('datalad.support.sshconnector')


def get_connection_hash(hostname, port='', username='', identity_file=''):
    """Generate a hash based on SSH connection properties

    This can be used for generating filenames that are unique
    to a connection from and to a particular machine (with
    port and login username). The hash also contains the local
    host name.

    Identity file corresponds to a file that will be passed via ssh's -i
    option.
    """
    # returning only first 8 characters to minimize our chance
    # of hitting a limit on the max path length for the Unix socket.
    # Collisions would be very unlikely even if we used less than 8.
    # References:
    #  https://github.com/ansible/ansible/issues/11536#issuecomment-153030743
    #  https://github.com/datalad/datalad/pull/1377
    return md5(
        '{lhost}{rhost}{port}{identity_file}{username}'.format(
            lhost=gethostname(),
            rhost=hostname,
            port=port,
            identity_file=identity_file,
            username=username).encode('utf-8')).hexdigest()[:8]


@auto_repr
class SSHConnection(object):
    """Representation of a (shared) ssh connection.
    """

    def __init__(self, ctrl_path, sshri, identity_file=None):
        """Create a connection handler

        The actual opening of the connection is performed on-demand.

        Parameters
        ----------
        ctrl_path: str
          path to SSH controlmaster
        sshri: SSHRI
          SSH resource identifier (contains all connection-relevant info),
          or another resource identifier that can be converted into an SSHRI.
        identity_file : str or None
          Value to pass to ssh's -i option.
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
        self._ctrl_options = ["-o", "ControlPath=\"%s\"" % self.ctrl_path]
        if self.sshri.port:
            self._ctrl_options += ['-p', '{}'.format(self.sshri.port)]

        self._identity_file = identity_file

        # essential properties of the remote system
        self._remote_props = {}
        self._opened_by_us = False

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

        # TODO:  do not do all those checks for every invocation!!
        # TODO: check for annex location once, check for open socket once
        #       and provide roll back if fails to run and was not explicitly
        #       checked first
        if not self.is_open():
            if not self.open():
                raise RuntimeError(
                    'Cannot open SSH connection to {}'.format(
                        self.sshri))

        # locate annex and set the bundled vs. system Git machinery in motion
        remote_annex_installdir = self.get_annex_installdir()
        if remote_annex_installdir:
            # make sure to use the bundled git version if any exists
            cmd = '{}; {}'.format(
                'export "PATH={}:$PATH"'.format(remote_annex_installdir),
                cmd)

        # build SSH call, feed remote command as a single last argument
        # whatever it contains will go to the remote machine for execution
        # we cannot perform any sort of escaping, because it will limit
        # what we can do on the remote, e.g. concatenate commands with '&&'
        ssh_cmd = ["ssh"] + self._ctrl_options
        ssh_cmd += [self.sshri.as_str()] \
            + [cmd]

        kwargs = dict(
            log_stdout=log_output, log_stderr=log_output,
            log_online=not log_output
        )

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
            lgr.log(
                5,
                "Not opening %s for checking since %s does not exist",
                self, self.ctrl_path
            )
            return False
        # check whether controlmaster is still running:
        cmd = ["ssh", "-O", "check"] + self._ctrl_options + [self.sshri.as_str()]
        lgr.debug("Checking %s by calling %s" % (self, cmd))
        null = open('/dev/null')
        try:
            # expect_stderr since ssh would announce to stderr
            # "Master is running" and that is normal, not worthy warning about
            # etc -- we are doing the check here for successful operation
            out, err = self.runner.run(cmd, stdin=null, expect_stderr=True)
            res = True
        except CommandError as e:
            if e.code != 255:
                # this is not a normal SSH error, whine ...
                raise e
            # SSH died and left socket behind, or server closed connection
            self.close()
            res = False
        finally:
            null.close()
        lgr.debug("Check of %s has %s", self, {True: 'succeeded', False: 'failed'}[res])
        return res

    def open(self):
        """Opens the connection.

        In other words: Creates the SSH controlmaster to be used by this
        connection, if it is not there already.

        Returns
        -------
        bool
          Whether SSH reports success opening the connection
        """
        if self.is_open():
            return

        # set control options
        ctrl_options = ["-fN",
                        "-o", "ControlMaster=auto",
                        "-o", "ControlPersist=15m"] + self._ctrl_options
        if self._identity_file:
            ctrl_options.extend(["-i", self._identity_file])
        # create ssh control master command
        cmd = ["ssh"] + ctrl_options + [self.sshri.as_str()]

        # start control master:
        lgr.debug("Opening %s by calling %s" % (self, cmd))
        proc = Popen(cmd)
        stdout, stderr = proc.communicate(input="\n")  # why the f.. this is necessary?

        # wait till the command exits, connection is conclusively
        # open or not at this point
        exit_code = proc.wait()
        ret = exit_code == 0

        if not ret:
            lgr.warning(
                "Failed to run cmd %s. Exit code=%s\nstdout: %s\nstderr: %s",
                cmd, exit_code, stdout, stderr
            )
        else:
            self._opened_by_us = True
        return ret

    def close(self):
        """Closes the connection.
        """
        if not self._opened_by_us:
            lgr.debug("Not closing %s since was not opened by itself", self)
            return
        # stop controlmaster:
        cmd = ["ssh", "-O", "stop"] + self._ctrl_options + [self.sshri.as_str()]
        lgr.debug("Closing %s by calling %s", self, cmd)
        try:
            self.runner.run(cmd, expect_stderr=True, expect_fail=True)
        except CommandError as e:
            lgr.debug("Failed to run close command")
            if exists(self.ctrl_path):
                lgr.debug("Removing existing control path %s", self.ctrl_path)
                # socket need to go in any case
                remove(self.ctrl_path)
            if e.code != 255:
                # not a "normal" SSH error
                raise e

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
        # Convert ssh's port flag (-p) to scp's (-P).
        scp_options = ["-P" if x == "-p" else x for x in self._ctrl_options]
        # add recursive, preserve_attributes flag if recursive, preserve_attrs set and create scp command
        scp_options += ["-r"] if recursive else []
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
        if key in self._remote_props:
            return self._remote_props[key]
        annex_install_dir = None
        # already set here to avoid any sort of recursion until we know
        # more
        self._remote_props[key] = annex_install_dir
        try:
            with open('/dev/null') as null:
                annex_install_dir = self(
                    # use sh -e to be able to fail at each stage of the process
                    "sh -e -c 'dirname $(readlink -f $(which git-annex-shell))'"
                    , stdin=null
                )[0].strip()
        except CommandError as e:
            lgr.debug('Failed to locate remote git-annex installation: %s',
                      exc_str(e))
        self._remote_props[key] = annex_install_dir
        return annex_install_dir

    def get_annex_version(self):
        key = 'cmd:annex'
        if key in self._remote_props:
            return self._remote_props[key]
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
        self._remote_props[key] = version
        return version

    def get_git_version(self):
        key = 'cmd:git'
        if key in self._remote_props:
            return self._remote_props[key]
        git_version = None
        try:
            git_version = self('git version')[0].split()[2]
        except CommandError as e:
            lgr.debug('Failed to determine Git version: %s',
                      exc_str(e))
        self._remote_props[key] = git_version
        return git_version


@auto_repr
class SSHManager(object):
    """Keeps ssh connections to share. Serves singleton representation
    per connection.

    A custom identity file can be specified via `datalad.ssh.identityfile`.
    Callers are responsible for reloading `datalad.cfg` if they have changed
    this value since loading datalad.
    """

    def __init__(self):
        self._socket_dir = None
        self._connections = dict()
        # Initialization of prev_connections is happening during initial
        # handling of socket_dir, so we do not define them here explicitly
        # to an empty list to fail if logic is violated
        self._prev_connections = None
        # and no explicit initialization in the constructor
        # self.assure_initialized()

    @property
    def socket_dir(self):
        """Return socket_dir, and if was not defined before,
        and also pick up all previous connections (if any)
        """
        self.assure_initialized()
        return self._socket_dir

    def assure_initialized(self):
        """Assures that manager is initialized - knows socket_dir, previous connections
        """
        if self._socket_dir is not None:
            return
        from ..config import ConfigManager
        from os import chmod
        cfg = ConfigManager()
        self._socket_dir = opj(cfg.obtain('datalad.locations.cache'),
                               'sockets')
        assure_dir(self._socket_dir)
        try:
            chmod(self._socket_dir, 0o700)
        except OSError as exc:
            lgr.warning(
                "Failed to (re)set permissions on the %s. "
                "Most likely future communications would be impaired or fail. "
                "Original exception: %s",
                self._socket_dir, exc_str(exc)
            )

        from os import listdir
        from os.path import isdir
        try:
            self._prev_connections = [opj(self.socket_dir, p)
                                      for p in listdir(self.socket_dir)
                                      if not isdir(opj(self.socket_dir, p))]
        except OSError as exc:
            self._prev_connections = []
            lgr.warning(
                "Failed to list %s for existing sockets. "
                "Most likely future communications would be impaired or fail. "
                "Original exception: %s",
                self._socket_dir, exc_str(exc)
            )

        lgr.log(5,
                "Found %d previous connections",
                len(self._prev_connections))

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
        if isinstance(url, RI):
            sshri = url
        else:
            if ':' not in url and '/' not in url:
                # it is just a hostname
                lgr.debug("Assuming %r is just a hostname for ssh connection",
                          url)
                url += ':'
            sshri = RI(url)

        if not is_ssh(sshri):
            raise ValueError("Unsupported SSH URL: '{0}', use "
                             "ssh://host/path or host:path syntax".format(url))

        from datalad import cfg
        identity_file = cfg.get("datalad.ssh.identityfile")

        conhash = get_connection_hash(
            sshri.hostname,
            port=sshri.port,
            identity_file=identity_file or "",
            username=sshri.username)
        # determine control master:
        ctrl_path = "%s/%s" % (self.socket_dir, conhash)

        # do we know it already?
        if ctrl_path in self._connections:
            return self._connections[ctrl_path]
        else:
            c = SSHConnection(ctrl_path, sshri, identity_file=identity_file)
            self._connections[ctrl_path] = c
            return c

    def close(self, allow_fail=True, ctrl_path=None):
        """Closes all connections, known to this instance.

        Parameters
        ----------
        allow_fail: bool, optional
          If True, swallow exceptions which might be thrown during
          connection.close, and just log them at DEBUG level
        ctrl_path: str or list of str, optional
          If specified, only the path(s) provided would be considered
        """
        if self._connections:
            from datalad.utils import assure_list
            ctrl_paths = assure_list(ctrl_path)
            to_close = [c for c in self._connections
                        # don't close if connection wasn't opened by SSHManager
                        if self._connections[c].ctrl_path
                        not in self._prev_connections and
                        exists(self._connections[c].ctrl_path)
                        and (not ctrl_paths
                             or self._connections[c].ctrl_path in ctrl_paths)]
            if to_close:
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
            self._connections = dict()
