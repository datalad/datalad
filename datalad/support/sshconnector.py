# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import os
import tempfile
import threading
from hashlib import md5
from socket import gethostname
from subprocess import Popen

import fasteners

from datalad.cmd import (
    NoCapture,
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.support.exceptions import (
    CapturedException,
    CommandError,
    ConnectionOpenFailedError,
)
from datalad.support.external_versions import external_versions
# importing the quote function here so it can always be imported from this
# module
# this used to be shlex.quote(), but is now a cross-platform helper
from datalad.utils import (
    Path,
    auto_repr,
    ensure_list,
    on_windows,
)
from datalad.utils import quote_cmdlinearg as sh_quote

# !!! Do not import network here -- delay import, allows to shave off 50ms or so
# on initial import datalad time
# from datalad.support.network import RI, is_ssh


lgr = logging.getLogger('datalad.support.sshconnector')


def get_connection_hash(hostname, port='', username='', identity_file='',
                        bundled=None, force_ip=False):
    """Generate a hash based on SSH connection properties

    This can be used for generating filenames that are unique
    to a connection from and to a particular machine (with
    port and login username). The hash also contains the local
    host name.

    Identity file corresponds to a file that will be passed via ssh's -i
    option.

    All parameters correspond to the respective properties of an SSH
    connection, except for `bundled`, which is unused.

    .. deprecated:: 0.16
       The ``bundled`` argument is ignored.
    """
    if bundled is not None:
        import warnings
        warnings.warn(
            "The `bundled` argument of `get_connection_hash()` is ignored. "
            "It will be removed in a future release.",
            DeprecationWarning)
    # returning only first 8 characters to minimize our chance
    # of hitting a limit on the max path length for the Unix socket.
    # Collisions would be very unlikely even if we used less than 8.
    # References:
    #  https://github.com/ansible/ansible/issues/11536#issuecomment-153030743
    #  https://github.com/datalad/datalad/pull/1377

    # The "# nosec" below skips insecure hash checks by 'codeclimate'. The hash
    # is not security critical, since it is only used as an "abbreviation" of
    # the unique connection property string.
    return md5(         # nosec
        '{lhost}{rhost}{port}{identity_file}{username}{force_ip}'.format(
            lhost=gethostname(),
            rhost=hostname,
            port=port,
            identity_file=identity_file,
            username=username,
            force_ip=force_ip or ''
        ).encode('utf-8')).hexdigest()[:8]


@auto_repr
class BaseSSHConnection(object):
    """Representation of an SSH connection.
    """
    def __init__(self, sshri, identity_file=None,
                 use_remote_annex_bundle=None, force_ip=False):
        """Create a connection handler

        The actual opening of the connection is performed on-demand.

        Parameters
        ----------
        sshri: SSHRI
          SSH resource identifier (contains all connection-relevant info),
          or another resource identifier that can be converted into an SSHRI.
        identity_file : str or None
          Value to pass to ssh's -i option.
        use_remote_annex_bundle : bool, optional
          If enabled, look for a git-annex installation on the remote and
          prefer its Git binaries in the search path (i.e. prefer a bundled
          Git over a system package). See also the configuration setting
          datalad.ssh.try-use-annex-bundled-git
        force_ip : {False, 4, 6}
           Force the use of IPv4 or IPv6 addresses with -4 or -6.

        .. versionchanged:: 0.16
           The default for `use_remote_annex_bundle` changed from `True`
           to `None`. Instead of attempting to use a potentially available
           git-annex bundle on the remote host by default, this behavior
           is now conditional on the `datalad.ssh.try-use-annex-bundled-git`
           (off by default).
        """
        self._runner = None
        self._ssh_executable = None
        self._ssh_version = None

        from datalad.support.network import (
            SSHRI,
            is_ssh,
        )
        if not is_ssh(sshri):
            raise ValueError(
                "Non-SSH resource identifiers are not supported for SSH "
                "connections: {}".format(sshri))
        self.sshri = SSHRI(**{k: v for k, v in sshri.fields.items()
                              if k in ('username', 'hostname', 'port')})
        # arguments only used for opening a connection
        self._ssh_open_args = []
        # arguments for annex ssh invocation
        self._ssh_args = []
        self._ssh_open_args.extend(
            ['-p', '{}'.format(self.sshri.port)] if self.sshri.port else [])
        if force_ip:
            self._ssh_open_args.append("-{}".format(force_ip))
        if identity_file:
            self._ssh_open_args.extend(["-i", identity_file])

        self._use_remote_annex_bundle = use_remote_annex_bundle
        # essential properties of the remote system
        self._remote_props = {}

    def __call__(self, cmd, options=None, stdin=None, log_output=True):
        """Executes a command on the remote.

        It is the callers responsibility to properly quote commands
        for remote execution (e.g. filename with spaces of other special
        characters).

        Parameters
        ----------
        cmd: str
          command to run on the remote
        options : list of str, optional
          Additional options to pass to the `-o` flag of `ssh`. Note: Many
          (probably most) of the available configuration options should not be
          set here because they can critically change the properties of the
          connection. This exists to allow options like SendEnv to be set.
        log_output: bool
          Whether to capture and return stdout+stderr.

        Returns
        -------
        tuple of str
          stdout, stderr of the command run, if `log_output` was `True`
        """
        raise NotImplementedError

    def open(self):
        """Opens the connection.

        Returns
        -------
        bool
          To return True if connection establishes a control socket successfully.
          Return False otherwise
        """

        raise NotImplementedError

    def close(self):
        """Closes the connection.
        """

        raise NotImplementedError

    @property
    def ssh_executable(self):
        """determine which ssh client executable should be used.
        """
        if not self._ssh_executable:
            from datalad import cfg
            self._ssh_executable = cfg.obtain("datalad.ssh.executable")
        return self._ssh_executable

    @property
    def runner(self):
        if self._runner is None:
            self._runner = WitlessRunner()
        return self._runner

    @property
    def ssh_version(self):
        if self._ssh_version is None:
            ssh_version = external_versions["cmd:ssh"]
            self._ssh_version = ssh_version.version if ssh_version else None
        return self._ssh_version

    def _adjust_cmd_for_bundle_execution(self, cmd):
        from datalad import cfg

        # locate annex and set the bundled vs. system Git machinery in motion
        if self._use_remote_annex_bundle \
                or cfg.obtain('datalad.ssh.try-use-annex-bundled-git'):
            remote_annex_installdir = self.get_annex_installdir()
            if remote_annex_installdir:
                # make sure to use the bundled git version if any exists
                cmd = '{}; {}'.format(
                    'export "PATH={}:$PATH"'.format(remote_annex_installdir),
                    cmd)
        return cmd

    def _exec_ssh(self, ssh_cmd, cmd, options=None, stdin=None, log_output=True):
        cmd = self._adjust_cmd_for_bundle_execution(cmd)

        for opt in options or []:
            ssh_cmd.extend(["-o", opt])

        # build SSH call, feed remote command as a single last argument
        # whatever it contains will go to the remote machine for execution
        # we cannot perform any sort of escaping, because it will limit
        # what we can do on the remote, e.g. concatenate commands with '&&'
        ssh_cmd += [self.sshri.as_str()] + [cmd]

        lgr.debug("%s is used to run %s", self, ssh_cmd)

        # TODO: pass expect parameters from above?
        # Hard to explain to toplevel users ... So for now, just set True
        out = self.runner.run(
            ssh_cmd,
            protocol=StdOutErrCapture if log_output else NoCapture,
            stdin=stdin)
        return out['stdout'], out['stderr']

    def _get_scp_command_spec(self, recursive, preserve_attrs):
        """Internal helper for SCP interface methods"""
        # Convert ssh's port flag (-p) to scp's (-P).
        scp_options = ["-P" if x == "-p" else x for x in self._ssh_args]
        # add recursive, preserve_attributes flag if recursive, preserve_attrs set and create scp command
        scp_options += ["-r"] if recursive else []
        scp_options += ["-p"] if preserve_attrs else []
        return ["scp"] + scp_options

    def _quote_filename(self, filename):
        if self.ssh_version and self.ssh_version[0] < 9:
            return _quote_filename_for_scp(filename)

        # no filename quoting for OpenSSH version 9 and above
        return filename

    def put(self, source, destination, recursive=False, preserve_attrs=False):
        """Copies source file/folder to destination on the remote.

        Note: this method performs escaping of filenames to an extent that
        moderately weird ones should work (spaces, quotes, pipes, other
        characters with special shell meaning), but more complicated cases
        might require appropriate external preprocessing of filenames.

        Parameters
        ----------
        source : str or list
          file/folder path(s) to copy from on local
        destination : str
          file/folder path to copy to on remote
        recursive : bool
          flag to enable recursive copying of given sources
        preserve_attrs : bool
          preserve modification times, access times, and modes from the
          original file

        Returns
        -------
        str
          stdout, stderr of the copy operation.
        """
        # make sure we have an open connection, will test if action is needed
        # by itself
        self.open()
        scp_cmd = self._get_scp_command_spec(recursive, preserve_attrs)
        # add source filepath(s) to scp command
        scp_cmd += ensure_list(source)
        # add destination path
        scp_cmd += ['%s:%s' % (
            self.sshri.hostname,
            self._quote_filename(destination),
        )]
        out = self.runner.run(scp_cmd, protocol=StdOutErrCapture)
        return out['stdout'], out['stderr']

    def get(self, source, destination, recursive=False, preserve_attrs=False):
        """Copies source file/folder from remote to a local destination.

        Note: this method performs escaping of filenames to an extent that
        moderately weird ones should work (spaces, quotes, pipes, other
        characters with special shell meaning), but more complicated cases
        might require appropriate external preprocessing of filenames.

        Parameters
        ----------
        source : str or list
          file/folder path(s) to copy from the remote host
        destination : str
          file/folder path to copy to on the local host
        recursive : bool
          flag to enable recursive copying of given sources
        preserve_attrs : bool
          preserve modification times, access times, and modes from the
          original file

        Returns
        -------
        str
          stdout, stderr of the copy operation.
        """
        # make sure we have an open connection, will test if action is needed
        # by itself
        self.open()
        scp_cmd = self._get_scp_command_spec(recursive, preserve_attrs)
        # add source filepath(s) to scp command, prefixed with the remote host
        scp_cmd += ["%s:%s" % (self.sshri.hostname, self._quote_filename(s))
                    for s in ensure_list(source)]
        # add destination path
        scp_cmd += [destination]
        out = self.runner.run(scp_cmd, protocol=StdOutErrCapture)
        return out['stdout'], out['stderr']

    def get_annex_installdir(self):
        key = 'installdir:annex'
        if key in self._remote_props:
            return self._remote_props[key]
        annex_install_dir = None
        # already set here to avoid any sort of recursion until we know
        # more
        self._remote_props[key] = annex_install_dir
        try:
            with tempfile.TemporaryFile() as tempf:
                # TODO does not work on windows
                annex_install_dir = self(
                    # use sh -e to be able to fail at each stage of the process
                    "sh -e -c 'dirname $(readlink -f $(which git-annex-shell))'"
                    , stdin=tempf
                )[0].strip()
        except CommandError as e:
            lgr.debug('Failed to locate remote git-annex installation: %s',
                      CapturedException(e))
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
                          CapturedException(e))
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
                      CapturedException(e))
        self._remote_props[key] = git_version
        return git_version


@auto_repr
class NoMultiplexSSHConnection(BaseSSHConnection):
    """Representation of an SSH connection.

    The connection is opened for execution of a single process, and closed
    as soon as the process end.
    """
    def __call__(self, cmd, options=None, stdin=None, log_output=True):

        # there is no dedicated "open" step, put all args together
        ssh_cmd = [self.ssh_executable] + self._ssh_open_args + self._ssh_args
        return self._exec_ssh(
            ssh_cmd,
            cmd,
            options=options,
            stdin=stdin,
            log_output=log_output)

    def is_open(self):
        return False

    def open(self):
        return False

    def close(self):
        # we perform blocking execution, we should not return from __call__ until
        # the connection is already closed
        pass


@auto_repr
class MultiplexSSHConnection(BaseSSHConnection):
    """Representation of a (shared) ssh connection.
    """
    def __init__(self, ctrl_path, sshri, **kwargs):
        """Create a connection handler

        The actual opening of the connection is performed on-demand.

        Parameters
        ----------
        ctrl_path: str
          path to SSH controlmaster
        sshri: SSHRI
          SSH resource identifier (contains all connection-relevant info),
          or another resource identifier that can be converted into an SSHRI.
        **kwargs
          Pass on to BaseSSHConnection
        """
        super().__init__(sshri, **kwargs)

        # on windows cmd args lists are always converted into a string using appropriate
        # quoting rules, on other platforms args lists are passed directly and we need
        # to take care of quoting ourselves
        ctrlpath_arg = "ControlPath={}".format(ctrl_path if on_windows else sh_quote(str(ctrl_path)))
        self._ssh_args += ["-o", ctrlpath_arg]
        self._ssh_open_args += [
            "-fN",
            "-o", "ControlMaster=auto",
            "-o", "ControlPersist=15m",
        ]
        self.ctrl_path = Path(ctrl_path)
        self._opened_by_us = False
        # used by @fasteners.locked
        self._lock = [
            threading.Lock(),
            fasteners.process_lock.InterProcessLock(self.ctrl_path.with_suffix('.lck'))
        ]

    def __call__(self, cmd, options=None, stdin=None, log_output=True):

        # XXX: check for open socket once
        #      and provide roll back if fails to run and was not explicitly
        #      checked first
        # MIH: this would mean that we would have to distinguish failure
        #      of a payload command from failure of SSH itself. SSH however,
        #      only distinguishes success and failure of the entire operation
        #      Increase in fragility from introspection makes a potential
        #      performance benefit a questionable improvement.
        # make sure we have an open connection, will test if action is needed
        # by itself
        self.open()

        ssh_cmd = [self.ssh_executable] + self._ssh_args
        return self._exec_ssh(
            ssh_cmd,
            cmd,
            options=options,
            stdin=stdin,
            log_output=log_output)

    def _assemble_multiplex_ssh_cmd(self, additional_arguments):
        return [self.ssh_executable] \
               + additional_arguments \
               + self._ssh_args \
               + [self.sshri.as_str()]

    def is_open(self):
        if not self.ctrl_path.exists():
            lgr.log(
                5,
                "Not opening %s for checking since %s does not exist",
                self, self.ctrl_path
            )
            return False
        # check whether controlmaster is still running:
        cmd = self._assemble_multiplex_ssh_cmd(["-O", "check"])

        lgr.debug("Checking %s by calling %s", self, cmd)
        try:
            # expect_stderr since ssh would announce to stderr
            # "Master is running" and that is normal, not worthy warning about
            # etc -- we are doing the check here for successful operation
            with tempfile.TemporaryFile() as tempf:
                self.runner.run(
                    cmd,
                    # do not leak output
                    protocol=StdOutErrCapture,
                    stdin=tempf)
            res = True
        except CommandError as e:
            if e.code != 255:
                # this is not a normal SSH error, whine ...
                raise e
            # SSH died and left socket behind, or server closed connection
            self.close()
            res = False
        lgr.debug(
            "Check of %s has %s",
            self,
            {True: 'succeeded', False: 'failed'}[res])
        return res

    @fasteners.locked
    def open(self):
        """Opens the connection.

        In other words: Creates the SSH ControlMaster to be used by this
        connection, if it is not there already.

        Returns
        -------
        bool
          True when SSH reports success opening the connection, False when
          a ControlMaster for an open connection already exists.

        Raises
        ------
        ConnectionOpenFailedError
          When starting the SSH ControlMaster process failed.
        """
        # the socket should vanish almost instantly when the connection closes
        # sending explicit 'check' commands to the control master is expensive
        # (needs tempfile to shield stdin, Runner overhead, etc...)
        # as we do not use any advanced features (forwarding, stop[ing the
        # master without exiting) it should be relatively safe to just perform
        # the much cheaper check of an existing control path
        if self.ctrl_path.exists():
            return False

        # create ssh control master command
        cmd = self._assemble_multiplex_ssh_cmd(self._ssh_open_args)

        # start control master:
        lgr.debug("Opening %s by calling %s", self, cmd)
        # The following call is exempt from bandit's security checks because
        # we/the user control the content of 'cmd'.
        proc = Popen(cmd)  # nosec
        stdout, stderr = proc.communicate(input="\n")  # why the f.. this is necessary?

        # wait till the command exits, connection is conclusively
        # open or not at this point
        exit_code = proc.wait()

        if exit_code != 0:
            raise ConnectionOpenFailedError(
                cmd,
                'Failed to open SSH connection (could not start ControlMaster process)',
                exit_code,
                stdout,
                stderr,
            )
        self._opened_by_us = True
        return True

    def close(self):
        if not self._opened_by_us:
            lgr.debug("Not closing %s since was not opened by itself", self)
            return
        # stop controlmaster:
        cmd = self._assemble_multiplex_ssh_cmd(["-O", "stop"])
        lgr.debug("Closing %s by calling %s", self, cmd)
        try:
            self.runner.run(cmd, protocol=StdOutErrCapture)
        except CommandError as e:
            lgr.debug("Failed to run close command")
            if self.ctrl_path.exists():
                lgr.debug("Removing existing control path %s", self.ctrl_path)
                # socket need to go in any case
                self.ctrl_path.unlink()
            if e.code != 255:
                # not a "normal" SSH error
                raise e


@auto_repr
class BaseSSHManager(object):
    """Interface for an SSHManager
    """
    def ensure_initialized(self):
        """Ensures that manager is initialized"""
        pass

    assure_initialized = ensure_initialized

    def get_connection(self, url, use_remote_annex_bundle=None, force_ip=False):
        """Get an SSH connection handler

        Parameters
        ----------
        url: str
          ssh url
        use_remote_annex_bundle : bool, optional
          If enabled, look for a git-annex installation on the remote and
          prefer its Git binaries in the search path (i.e. prefer a bundled
          Git over a system package). See also the configuration setting
          datalad.ssh.try-use-annex-bundled-git
        force_ip : {False, 4, 6}
          Force the use of IPv4 or IPv6 addresses.

        Returns
        -------
        BaseSSHConnection

        .. versionchanged:: 0.16
           The default for `use_remote_annex_bundle` changed from `True`
           to `None`. Instead of attempting to use a potentially available
           git-annex bundle on the remote host by default, this behavior
           is now conditional on the `datalad.ssh.try-use-annex-bundled-git`
           (off by default).
        """
        raise NotImplementedError

    def _prep_connection_args(self, url):
        # parse url:
        from datalad.support.network import (
            RI,
            is_ssh,
        )
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
        return sshri, identity_file

    def close(self, allow_fail=True):
        """Closes all connections, known to this instance.

        Parameters
        ----------
        allow_fail: bool, optional
          If True, swallow exceptions which might be thrown during
          connection.close, and just log them at DEBUG level
        """
        pass


@auto_repr
class NoMultiplexSSHManager(BaseSSHManager):
    """Does not "manage" and just returns a new connection
    """

    def get_connection(self, url, use_remote_annex_bundle=None, force_ip=False):
        sshri, identity_file = self._prep_connection_args(url)

        return NoMultiplexSSHConnection(
            sshri,
            identity_file=identity_file,
            use_remote_annex_bundle=use_remote_annex_bundle,
            force_ip=force_ip,
        )


@auto_repr
class MultiplexSSHManager(BaseSSHManager):
    """Keeps ssh connections to share. Serves singleton representation
    per connection.

    A custom identity file can be specified via `datalad.ssh.identityfile`.
    Callers are responsible for reloading `datalad.cfg` if they have changed
    this value since loading datalad.
    """

    def __init__(self):
        super().__init__()
        self._socket_dir = None
        self._connections = dict()
        # Initialization of prev_connections is happening during initial
        # handling of socket_dir, so we do not define them here explicitly
        # to an empty list to fail if logic is violated
        self._prev_connections = None
        # and no explicit initialization in the constructor
        # self.ensure_initialized()

    @property
    def socket_dir(self):
        """Return socket_dir, and if was not defined before,
        and also pick up all previous connections (if any)
        """
        self.ensure_initialized()
        return self._socket_dir

    def ensure_initialized(self):
        """Assures that manager is initialized - knows socket_dir, previous connections
        """
        if self._socket_dir is not None:
            return
        from datalad import cfg
        self._socket_dir = Path(cfg.obtain('datalad.locations.sockets'))
        self._socket_dir.mkdir(exist_ok=True, parents=True)
        try:
            os.chmod(str(self._socket_dir), 0o700)
        except OSError as exc:
            lgr.warning(
                "Failed to (re)set permissions on the %s. "
                "Most likely future communications would be impaired or fail. "
                "Original exception: %s",
                self._socket_dir, CapturedException(exc)
            )

        try:
            self._prev_connections = [p
                                      for p in self.socket_dir.iterdir()
                                      if not p.is_dir()]
        except OSError as exc:
            self._prev_connections = []
            lgr.warning(
                "Failed to list %s for existing sockets. "
                "Most likely future communications would be impaired or fail. "
                "Original exception: %s",
                self._socket_dir, CapturedException(exc)
            )

        lgr.log(5,
                "Found %d previous connections",
                len(self._prev_connections))
    assure_initialized = ensure_initialized

    def get_connection(self, url, use_remote_annex_bundle=None, force_ip=False):

        sshri, identity_file = self._prep_connection_args(url)

        conhash = get_connection_hash(
            sshri.hostname,
            port=sshri.port,
            identity_file=identity_file or "",
            username=sshri.username,
            force_ip=force_ip,
        )
        # determine control master:
        ctrl_path = self.socket_dir / conhash

        # do we know it already?
        if ctrl_path in self._connections:
            return self._connections[ctrl_path]
        else:
            c = MultiplexSSHConnection(
                ctrl_path, sshri, identity_file=identity_file,
                use_remote_annex_bundle=use_remote_annex_bundle,
                force_ip=force_ip)
            self._connections[ctrl_path] = c
            return c

    def close(self, allow_fail=True, ctrl_path=None):
        """Closes all connections, known to this instance.

        Parameters
        ----------
        allow_fail: bool, optional
          If True, swallow exceptions which might be thrown during
          connection.close, and just log them at DEBUG level
        ctrl_path: str, Path, or list of str or Path, optional
          If specified, only the path(s) provided would be considered
        """
        if self._connections:
            ctrl_paths = [Path(p) for p in ensure_list(ctrl_path)]
            to_close = [c for c in self._connections
                        # don't close if connection wasn't opened by SSHManager
                        if self._connections[c].ctrl_path
                        not in self._prev_connections and
                        self._connections[c].ctrl_path.exists()
                        and (not ctrl_paths
                             or self._connections[c].ctrl_path in ctrl_paths)]
            if to_close:
                lgr.debug("Closing %d SSH connections...", len(to_close))
            for cnct in to_close:
                f = self._connections[cnct].close
                if allow_fail:
                    f()
                else:
                    try:
                        f()
                    except Exception as exc:
                        ce = CapturedException(exc)
                        lgr.debug("Failed to close a connection: "
                                  "%s", ce.message)
            self._connections = dict()


# retain backward compat with 0.13.4 and earlier
# should be ok since cfg already defined by the time this one is imported
from .. import cfg

if cfg.obtain('datalad.ssh.multiplex-connections'):
    SSHManager = MultiplexSSHManager
    SSHConnection = MultiplexSSHConnection
else:
    SSHManager = NoMultiplexSSHManager
    SSHConnection = NoMultiplexSSHConnection


def _quote_filename_for_scp(name):
    """Manually escape shell goodies in a file name.

    Why manual? Because the author couldn't find a better way, and
    simply quoting the entire filename does not work with SCP's overly
    strict file matching criteria (likely a bug on their side).

    Hence this beauty:
    """
    for s, t in (
            (' ', '\\ '),
            ('"', '\\"'),
            ("'", "\\'"),
            ("&", "\\&"),
            ("|", "\\|"),
            (">", "\\>"),
            ("<", "\\<"),
            (";", "\\;")):
        name = name.replace(s, t)
    return name
