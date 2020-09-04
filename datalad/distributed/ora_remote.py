from annexremote import SpecialRemote
from annexremote import RemoteError
from annexremote import ProtocolError

from pathlib import (
    Path,
    PurePosixPath
)
import requests
import shutil
from shlex import quote as sh_quote
import subprocess
import logging
from functools import wraps
from datalad.customremotes.ria_utils import (
    get_layout_locations,
    UnknownLayoutVersion,
    verify_ria_url,
)


lgr = logging.getLogger('datalad.customremotes.ria_remote')

DEFAULT_BUFFER_SIZE = 65536

# TODO
# - make archive check optional


def _get_gitcfg(gitdir, key, cfgargs=None, regex=False):
    cmd = [
        'git',
        '--git-dir', gitdir,
        'config',
    ]
    if cfgargs:
        cmd += cfgargs

    cmd += ['--get-regexp'] if regex else ['--get']
    cmd += [key]
    try:
        return subprocess.check_output(
            cmd,
            # yield text
            universal_newlines=True).strip()
    except Exception:
        lgr.debug(
            "Failed to obtain config '%s' at %s",
            key, gitdir,
        )
        return None


def _get_datalad_id(gitdir):
    """Attempt to determine a DataLad dataset ID for a given repo

    Returns
    -------
    str or None
      None in case no ID was found
    """
    dsid = _get_gitcfg(
        gitdir, 'datalad.dataset.id', ['--blob', ':.datalad/config']
    )
    if dsid is None:
        lgr.debug(
            "Cannot determine a DataLad ID for repository: %s",
            gitdir,
        )
    else:
        dsid = dsid.strip()
    return dsid


class RemoteCommandFailedError(Exception):
    pass


class RIARemoteError(RemoteError):

    def __init__(self, msg):
        super().__init__(msg.replace('\n', '\\n'))


class IOBase(object):
    """Abstract class with the desired API for local/remote operations"""
    def mkdir(self, path):
        raise NotImplementedError

    def put(self, src, dst, progress_cb):
        raise NotImplementedError

    def get(self, src, dst, progress_cb):
        raise NotImplementedError

    def rename(self, src, dst):
        raise NotImplementedError

    def remove(self, path):
        raise NotImplementedError

    def exists(self, path):
        raise NotImplementedError

    def get_from_archive(self, archive, src, dst, progress_cb):
        """Get a file from an archive

        Parameters
        ----------
        archive_path : Path or str
          Must be an absolute path and point to an existing supported archive
        file_path : Path or str
          Must be a relative Path (relative to the root
          of the archive)
        """
        raise NotImplementedError

    def in_archive(self, archive_path, file_path):
        """Test whether a file is in an archive

        Parameters
        ----------
        archive_path : Path or str
          Must be an absolute path and point to an existing supported archive
        file_path : Path or str
          Must be a relative Path (relative to the root
          of the archive)
        """
        raise NotImplementedError

    def read_file(self, file_path):
        """Read a remote file's content

        Parameters
        ----------
        file_path : Path or str
          Must be an absolute path

        Returns
        -------
        string
        """

        raise NotImplementedError

    def write_file(self, file_path, content, mode='w'):
        """Write a remote file

        Parameters
        ----------
        file_path : Path or str
          Must be an absolute path
        content : str
        """

        raise NotImplementedError


class LocalIO(IOBase):
    """IO operation if the object tree is local (e.g. NFS-mounted)"""
    def mkdir(self, path):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def put(self, src, dst, progress_cb):
        shutil.copy(
            str(src),
            str(dst),
        )

    def get(self, src, dst, progress_cb):
        shutil.copy(
            str(src),
            str(dst),
        )

    def get_from_archive(self, archive, src, dst, progress_cb):
        # this requires python 3.5
        with open(dst, 'wb') as target_file:
            subprocess.run([
                '7z', 'x', '-so',
                str(archive), str(src)],
                stdout=target_file,
            )
        # Note for progress reporting:
        # man 7z:
        #
        # -bs{o|e|p}{0|1|2}
        #         Set output stream for output/error/progress line

    def rename(self, src, dst):
        src.rename(dst)

    def remove(self, path):
        path.unlink()

    def remove_dir(self, path):
        path.rmdir()

    def exists(self, path):
        return path.exists()

    def in_archive(self, archive_path, file_path):
        if not archive_path.exists():
            # no archive, not file
            return False
        loc = str(file_path)
        from datalad.cmd import Runner
        runner = Runner()
        # query 7z for the specific object location, keeps the output
        # lean, even for big archives
        out, err = runner(
            ['7z', 'l', str(archive_path),
             loc],
            log_stdout=True,
        )
        return loc in out

    def read_file(self, file_path):

        with open(str(file_path), 'r') as f:
            content = f.read()
        return content

    def write_file(self, file_path, content, mode='w'):
        if not content.endswith('\n'):
            content += '\n'
        with open(str(file_path), mode) as f:
            f.write(content)


class SSHRemoteIO(IOBase):
    """IO operation if the object tree is SSH-accessible

    It doesn't even think about a windows server.
    """

    # output markers to detect possible command failure as well as end of output from a particular command:
    REMOTE_CMD_FAIL = "ora-remote: end - fail"
    REMOTE_CMD_OK = "ora-remote: end - ok"

    def __init__(self, host, buffer_size=DEFAULT_BUFFER_SIZE):
        """
        Parameters
        ----------
        host : str
          SSH-accessible host(name) to perform remote IO operations
          on.
        """

        from datalad.support.sshconnector import SSHManager
        # connection manager -- we don't have to keep it around, I think
        self.sshmanager = SSHManager()
        # the connection to the remote
        # we don't open it yet, not yet clear if needed
        self.ssh = self.sshmanager.get_connection(
            host,
            use_remote_annex_bundle=False,
        )
        self.ssh.open()
        # open a remote shell
        cmd = ['ssh'] + self.ssh._ssh_args + [self.ssh.sshri.as_str()]
        self.shell = subprocess.Popen(cmd, stderr=subprocess.DEVNULL, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
        # swallow login message(s):
        self.shell.stdin.write(b"echo RIA-REMOTE-LOGIN-END\n")
        self.shell.stdin.flush()
        while True:
            line = self.shell.stdout.readline()
            if line == b"RIA-REMOTE-LOGIN-END\n":
                break
        # TODO: Same for stderr?

        # make sure default is used when None was passed, too.
        self.buffer_size = buffer_size if buffer_size else DEFAULT_BUFFER_SIZE

    def close(self):
        # try exiting shell clean first
        self.shell.stdin.write(b"exit\n")
        self.shell.stdin.flush()
        exitcode = self.shell.wait(timeout=0.5)
        # be more brutal if it doesn't work
        if exitcode is None:  # timed out
            # TODO: Theoretically terminate() can raise if not successful. How to deal with that?
            self.shell.terminate()
        self.sshmanager.close()

    def _append_end_markers(self, cmd):
        """Append end markers to remote command"""

        return cmd + " && printf '%s\\n' {} || printf '%s\\n' {}\n".format(
            sh_quote(self.REMOTE_CMD_OK),
            sh_quote(self.REMOTE_CMD_FAIL))

    def _get_download_size_from_key(self, key):
        """Get the size of an annex object file from it's key

        Note, that this is not necessarily the size of the annexed file, but possibly only a chunk of it.

        Parameter
        ---------
        key: str
          annex key of the file

        Returns
        -------
        int
          size in bytes
        """
        # TODO: datalad's AnnexRepo.get_size_from_key() is not correct/not fitting. Incorporate the wisdom there, too.
        #       We prob. don't want to actually move this method there, since AnnexRepo would be quite an expensive
        #       import. Startup time for special remote matters.
        # TODO: this method can be more compact. we don't need particularly elaborated error distinction

        # see: https://git-annex.branchable.com/internals/key_format/
        key_parts = key.split('--')
        key_fields = key_parts[0].split('-')

        s = S = C = None

        for field in key_fields[1:]:  # note: first one has to be backend -> ignore
            if field.startswith('s'):
                # size of the annexed file content:
                s = int(field[1:]) if field[1:].isdigit() else None
            elif field.startswith('S'):
                # we have a chunk and that's the chunksize:
                S = int(field[1:]) if field[1:].isdigit() else None
            elif field.startswith('C'):
                # we have a chunk, this is it's number:
                C = int(field[1:]) if field[1:].isdigit() else None

        if s is None:
            return None
        elif S is None and C is None:
            return s
        elif S and C:
            if C <= int(s / S):
                return S
            else:
                return s % S
        else:
            raise RIARemoteError("invalid key: {}".format(key))

    def _run(self, cmd, no_output=True, check=False):

        # TODO: we might want to redirect stderr to stdout here (or have additional end marker in stderr)
        #       otherwise we can't empty stderr to be ready for next command. We also can't read stderr for better error
        #       messages (RemoteError) without making sure there's something to read in any case (it's blocking!)
        #       However, if we are sure stderr can only ever happen if we would raise RemoteError anyway, it might be
        #       okay
        call = self._append_end_markers(cmd)
        self.shell.stdin.write(call.encode())
        self.shell.stdin.flush()

        lines = []
        while True:
            line = self.shell.stdout.readline().decode()
            lines.append(line)
            if line == self.REMOTE_CMD_OK + '\n':
                # end reading
                break
            elif line == self.REMOTE_CMD_FAIL + '\n':
                if check:
                    raise RemoteCommandFailedError("{cmd} failed: {msg}".format(cmd=cmd,
                                                                                msg="".join(lines[:-1]))
                                                   )
                else:
                    break
        if no_output and len(lines) > 1:
            raise RIARemoteError("{}: {}".format(call, "".join(lines)))
        return "".join(lines[:-1])

    def mkdir(self, path):
        self._run('mkdir -p {}'.format(sh_quote(str(path))))

    def put(self, src, dst, progress_cb):
        self.ssh.put(str(src), str(dst))

    def get(self, src, dst, progress_cb):

        # Note, that as we are in blocking mode, we can't easily fail on the
        # actual get (that is 'cat').
        # Therefore check beforehand.
        if not self.exists(src):
            raise RIARemoteError("annex object {src} does not exist.".format(src=src))

        # TODO: see get_from_archive()

        # TODO: Currently we will hang forever if the file isn't readable and it's supposed size is bigger than whatever
        #       cat spits out on stdout. This is because we don't notice that cat has exited non-zero.
        #       We could have end marker on stderr instead, but then we need to empty stderr beforehand to not act upon
        #       output from earlier calls. This is a problem with blocking reading, since we need to make sure there's
        #       actually something to read in any case.
        cmd = 'cat {}'.format(sh_quote(str(src)))
        self.shell.stdin.write(cmd.encode())
        self.shell.stdin.write(b"\n")
        self.shell.stdin.flush()

        from os.path import basename
        key = basename(str(src))
        try:
            size = self._get_download_size_from_key(key)
        except RemoteError as e:
            raise RemoteError("src: {}".format(str(src)) + str(e))

        if size is None:
            # rely on SCP for now
            self.ssh.get(str(src), str(dst))
            return

        with open(dst, 'wb') as target_file:
            bytes_received = 0
            while bytes_received < size:  # TODO: some additional abortion criteria? check stderr in addition?
                c = self.shell.stdout.read1(self.buffer_size)
                # no idea yet, whether or not there's sth to gain by a sophisticated determination of how many bytes to
                # read at once (like size - bytes_received)
                if c:
                    bytes_received += len(c)
                    target_file.write(c)
                    progress_cb(bytes_received)

    def rename(self, src, dst):
        self._run('mv {} {}'.format(sh_quote(str(src)), sh_quote(str(dst))))

    def remove(self, path):
        self._run('rm {}'.format(sh_quote(str(path))))

    def remove_dir(self, path):
        self._run('rmdir {}'.format(sh_quote(str(path))))

    def exists(self, path):
        try:
            self._run('test -e {}'.format(sh_quote(str(path))), check=True)
            return True
        except RemoteCommandFailedError:
            return False

    def in_archive(self, archive_path, file_path):

        if not self.exists(archive_path):
            return False

        loc = str(file_path)
        # query 7z for the specific object location, keeps the output
        # lean, even for big archives
        cmd = '7z l {} {}'.format(
            sh_quote(str(archive_path)),
            sh_quote(loc))

        # Note: Currently relies on file_path not showing up in case of failure
        # including non-existent archive. If need be could be more sophisticated
        # and called with check=True + catch RemoteCommandFailedError
        out = self._run(cmd, no_output=False, check=False)

        return loc in out

    def get_from_archive(self, archive, src, dst, progress_cb):

        # Note, that as we are in blocking mode, we can't easily fail on the actual get (that is 'cat').
        # Therefore check beforehand.
        if not self.exists(archive):
            raise RIARemoteError("archive {arc} does not exist.".format(arc=archive))

        # TODO: We probably need to check exitcode on stderr (via marker). If archive or content is missing we will
        #       otherwise hang forever waiting for stdout to fill `size`

        cmd = '7z x -so {} {}\n'.format(
            sh_quote(str(archive)),
            sh_quote(str(src)))
        self.shell.stdin.write(cmd.encode())
        self.shell.stdin.flush()

        # TODO: - size needs double-check and some robustness
        #       - can we assume src to be a posixpath?
        #       - RF: Apart from the executed command this should be pretty much identical to self.get(), so move that
        #         code into a common function

        from os.path import basename
        size = self._get_download_size_from_key(basename(str(src)))

        with open(dst, 'wb') as target_file:
            bytes_received = 0
            while bytes_received < size:
                c = self.shell.stdout.read1(self.buffer_size)
                if c:
                    bytes_received += len(c)
                    target_file.write(c)
                    progress_cb(bytes_received)

    def read_file(self, file_path):

        cmd = "cat  {}".format(sh_quote(str(file_path)))
        try:
            out = self._run(cmd, no_output=False, check=True)
        except RemoteCommandFailedError:
            raise RIARemoteError("Could not read {}".format(str(file_path)))

        return out

    def write_file(self, file_path, content, mode='w'):

        if mode == 'w':
            mode = ">"
        elif mode == 'a':
            mode = ">>"
        else:
            raise ValueError("Unknown mode '{}'".format(mode))
        if not content.endswith('\n'):
            content += '\n'

        cmd = "printf '%s' {} {} {}".format(
            sh_quote(content),
            mode,
            sh_quote(str(file_path)))
        try:
            self._run(cmd, check=True)
        except RemoteCommandFailedError:
            raise RIARemoteError("Could not write to {}".format(str(file_path)))


class HTTPRemoteIO(object):
    # !!!!
    # This is not actually an IO class like SSHRemoteIO and LocalIO and needs
    # respective RF'ing of special remote implementation eventually.
    # We want ORA over HTTP, but with a server side CGI to talk to in order to
    # reduce the number of requests. Implementing this as such an IO class would
    # mean to have separate requests for all server side executions, which is
    # what we do not want. As a consequence RIARemote class implementation needs
    # to treat HTTP as a special case until refactoring to a design that fits
    # both approaches.

    # NOTE: For now read-only. Not sure yet whether an IO class is the right
    # approach.

    def __init__(self, ria_url, dsid, buffer_size=DEFAULT_BUFFER_SIZE):
        assert ria_url.startswith("ria+http")
        self.base_url = ria_url[4:]
        if self.base_url[-1] == '/':
            self.base_url = self.base_url[:-1]

        self.base_url += "/" + dsid[:3] + '/' + dsid[3:]
        # make sure default is used when None was passed, too.
        self.buffer_size = buffer_size if buffer_size else DEFAULT_BUFFER_SIZE

    def checkpresent(self, key_path):
        # Note, that we need the path with hash dirs, since we don't have access
        # to annexremote.dirhash from within IO classes

        url = self.base_url + "/annex/objects/" + str(key_path)
        response = requests.head(url)
        return response.status_code == 200

    def get(self, key_path, filename, progress_cb):
        # Note, that we need the path with hash dirs, since we don't have access
        # to annexremote.dirhash from within IO classes

        url = self.base_url + "/annex/objects/" + str(key_path)
        response = requests.get(url, stream=True)

        with open(filename, 'wb') as dst_file:
            bytes_received = 0
            for chunk in response.iter_content(chunk_size=self.buffer_size,
                                               decode_unicode=False):
                dst_file.write(chunk)
                bytes_received += len(chunk)
                progress_cb(bytes_received)


def handle_errors(func):
    """Decorator to convert and log errors

    Intended to use with every method of RiaRemote class, facing the outside
    world. In particular, that is about everything, that may be called via
    annex' special remote protocol, since a non-RemoteError will simply result
    in a broken pipe by default handling.
    """

    # TODO: configurable on remote end (flag within layout_version!)

    @wraps(func)
    def  _wrap_handle_errors(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            if self.remote_log_enabled:
                from datetime import datetime
                from traceback import format_exc
                exc_str = format_exc()
                entry = "{time}: Error:\n{exc_str}\n" \
                        "".format(time=datetime.now(),
                                  exc_str=exc_str)
                log_target = self.store_base_path / 'error_logs' / \
                             "{dsid}.{uuid}.log".format(dsid=self.archive_id,
                                                        uuid=self.uuid)
                self.io.write_file(log_target, entry, mode='a')
            if not isinstance(e, RIARemoteError):
                raise RIARemoteError(str(e))
            else:
                raise e

    return  _wrap_handle_errors


class NoLayoutVersion(Exception):
    pass


class RIARemote(SpecialRemote):
    """This is the class of RIA remotes.
    """

    dataset_tree_version = '1'
    object_tree_version = '2'
    # TODO: Move known versions. Needed by creation routines as well.
    known_versions_objt = ['1', '2']
    known_versions_dst = ['1']

    @handle_errors
    def __init__(self, annex):
        super(RIARemote, self).__init__(annex)
        if hasattr(self, 'configs'):
            # introduced in annexremote 1.4.2 to support LISTCONFIGS
            self.configs['url'] = "RIA store to use"
        # machine to SSH-log-in to access/store the data
        # subclass must set this
        self.storage_host = None
        # must be absolute, and POSIX
        # subclass must set this
        self.store_base_path = None
        # by default we can read and write
        self.read_only = False
        self.force_write = None
        self.uuid = None
        self.ignore_remote_config = None
        self.remote_log_enabled = None
        self.remote_dataset_tree_version = None
        self.remote_object_tree_version = None

        # for caching the remote's layout locations:
        self.remote_git_dir = None
        self.remote_archive_dir = None
        self.remote_obj_dir = None
        self._io = None  # lazy

        # cache obj_locations:
        self._last_archive_path = None
        self._last_keypath = (None, None)

    def verify_store(self):
        """Check whether the store exists and reports a layout version we
        know

        The layout of the store is recorded in base_path/ria-layout-version.
        If the version found on the remote end isn't supported and `force-write`
        isn't configured, sets the remote to read-only operation.
        """

        dataset_tree_version_file = \
            self.store_base_path / 'ria-layout-version'

        # check dataset tree version
        try:
            self.remote_dataset_tree_version = \
                self._get_version_config(dataset_tree_version_file)
            if self.remote_dataset_tree_version not in self.known_versions_dst:
                # Note: In later versions, condition might change in order to
                # deal with older versions.
                raise UnknownLayoutVersion(
                    "RIA store layout version unknown: %s" %
                    self.remote_dataset_tree_version)

        except (RemoteError, FileNotFoundError):
            # Exception class depends on whether self.io is local or SSH.
            # assume file doesn't exist
            # TODO: Is there a possibility RemoteError has a different reason
            #       and should be handled differently?
            #       Don't think so ATM. -> Reconsider with new execution layer.

            # Note: Error message needs entire URL not just the missing
            #       path, since it could be due to invalid URL. Path isn't
            #       telling if it's not clear what system we are looking at.
            # Note: Case switch due to still supported configs as an
            #       alternative to ria+ URLs. To be deprecated.
            if self.ria_store_url:
                target = self.ria_store_url
            elif self.storage_host:
                target = "ria+ssh://{}{}".format(
                    self.storage_host,
                    dataset_tree_version_file.parent)
            else:
                target = "ria+" + dataset_tree_version_file.parent.as_uri()

            if not self.io.exists(dataset_tree_version_file.parent):
                # unify exception to FileNotFoundError

                raise FileNotFoundError(
                    "Configured RIA store not found at %s " % target
                )
            else:
                # Directory is there, but no version file. We don't know what
                # that is. Treat the same way as if there was an unknown version
                # on record.
                raise NoLayoutVersion(
                    "Configured RIA store lacks a 'ria-layout-version' file at"
                    " %s" % target
                )

    def verify_ds_in_store(self):
        """Check whether the dataset exists in store and reports a layout
        version we know

        The layout is recorded in
        'dataset_somewhere_beneath_base_path/ria-layout-version.'
        If the version found on the remote end isn't supported and `force-write`
        isn't configured, sets the remote to read-only operation.
        """

        object_tree_version_file = self.remote_git_dir / 'ria-layout-version'

        # check (annex) object tree version
        try:
            self.remote_object_tree_version =\
                self._get_version_config(object_tree_version_file)
            if self.remote_object_tree_version not in self.known_versions_objt:
                raise UnknownLayoutVersion
        except (RemoteError, FileNotFoundError):
            # Exception class depends on whether self.io is local or SSH.
            # assume file doesn't exist
            # TODO: Is there a possibility RemoteError has a different reason
            #       and should be handled differently?
            #       Don't think so ATM. -> Reconsider with new execution layer.
            if not self.io.exists(object_tree_version_file.parent):
                # unify exception
                raise FileNotFoundError
            else:
                raise NoLayoutVersion

    def _load_cfg(self, gitdir, name):
        # for now still accept the configs, if no ria-URL is known:
        if not self.ria_store_url:
            self.storage_host = _get_gitcfg(
                gitdir, 'annex.ora-remote.{}.ssh-host'.format(name))

            store_base_path = _get_gitcfg(
                gitdir, 'annex.ora-remote.{}.base-path'.format(name))
            self.store_base_path = store_base_path.strip() \
                if store_base_path else None
        # Whether or not to force writing to the remote. Currently used to overrule write protection due to layout
        # version mismatch.
        self.force_write = _get_gitcfg(
            gitdir, 'annex.ora-remote.{}.force-write'.format(name))

        # whether to ignore config flags set at the remote end
        self.ignore_remote_config = _get_gitcfg(gitdir, 'annex.ora-remote.{}.ignore-remote-config'.format(name))

        # buffer size for reading files over HTTP and SSH
        self.buffer_size = _get_gitcfg(gitdir,
                                       "remote.{}.ora-buffer-size"
                                       "".format(name))
        if self.buffer_size:
            self.buffer_size = int(self.buffer_size)

    def _verify_config(self, gitdir, fail_noid=True):
        # try loading all needed info from (git) config
        name = self.annex.getconfig('name')
        if not name:
            raise RIARemoteError(
                "Cannot determine special remote name, got: {}".format(
                    repr(name)))
        # get store url:
        self.ria_store_url = self.annex.getconfig('url')
        if self.ria_store_url:
            # support URL rewrite without talking to a DataLad ConfigManager
            # Q is why? Why not use the config manager?
            url_cfgs = dict()
            url_cfgs_raw = _get_gitcfg(gitdir, "^url.*", regex=True)
            if url_cfgs_raw:
                for line in url_cfgs_raw.splitlines():
                    k, v = line.split()
                    url_cfgs[k] = v
            self.storage_host, self.store_base_path, self.ria_store_url = \
                verify_ria_url(self.ria_store_url, url_cfgs)

        # TODO duplicates call to `git-config` after RIA url rewrite
        self._load_cfg(gitdir, name)

        # for now still accept the configs, if no ria-URL is known:
        if not self.ria_store_url:
            if not self.store_base_path:
                self.store_base_path = self.annex.getconfig('base-path')
            if not self.store_base_path:
                raise RIARemoteError(
                    "No remote base path configured. "
                    "Specify `base-path` setting.")

        self.store_base_path = Path(self.store_base_path)
        if not self.store_base_path.is_absolute():
            raise RIARemoteError(
                'Non-absolute object tree base path configuration: %s'
                '' % str(self.store_base_path))

        # for now still accept the configs, if no ria-URL is known:
        if not self.ria_store_url:
            # Note: Special value '0' is replaced by None only after checking the repository's annex config.
            # This is to uniformly handle '0' and None later on, but let a user's config '0' overrule what's
            # stored by git-annex.
            if not self.storage_host:
                self.storage_host = self.annex.getconfig('ssh-host')
            elif self.storage_host == '0':
                self.storage_host = None

        # go look for an ID
        self.archive_id = self.annex.getconfig('archive-id')
        if fail_noid and not self.archive_id:
            raise RIARemoteError(
                "No archive ID configured. This should not happen.")

        # TODO: This should prob. not be done! Would only have an effect if force-write was committed
        #       annex-special-remote-config and this is likely a bad idea.
        if not self.force_write:
            self.force_write = self.annex.getconfig('force-write')

    def _get_version_config(self, path):
        """ Get version and config flags from remote file
        """

        file_content = self.io.read_file(path).strip().split('|')
        if not (1 <= len(file_content) <= 2):
            self.message("invalid version file {}".format(path))
            return None

        remote_version = file_content[0]
        remote_config_flags = file_content[1] if len(file_content) == 2 else None
        if not self.ignore_remote_config and remote_config_flags:
            # Note: 'or', since config flags can come from toplevel (dataset-tree-root) as well as
            #       from dataset-level. toplevel is supposed flag the entire tree.
            self.remote_log_enabled = self.remote_log_enabled or 'l' in remote_config_flags

        return remote_version

    def get_store(self):
        """checks the remote end for an existing store and dataset

        Furthermore reads and stores version and config flags, layout
        locations, etc.
        If this doesn't raise, the remote end should be fine to work with.
        """

        # cache remote layout directories
        self.remote_git_dir, self.remote_archive_dir, self.remote_obj_dir = \
            self.get_layout_locations(self.store_base_path, self.archive_id)

        read_only_msg = "Treating remote as read-only in order to" \
                        "prevent damage by putting things into an unknown " \
                        "version of the target layout. You can overrule this " \
                        "by setting 'annex.ora-remote.<name>.force-write=true'."
        try:
            self.verify_store()
        except UnknownLayoutVersion:
            reason = "Remote dataset tree reports version {}. Supported " \
                     "versions are: {}. Consider upgrading datalad or " \
                     "fix the 'ria-layout-version' file at the RIA store's " \
                     "root. ".format(self.remote_dataset_tree_version,
                                     self.known_versions_dst)
            self._set_read_only(reason + read_only_msg)
        except NoLayoutVersion:
            reason = "Remote doesn't report any dataset tree version. " \
                     "Consider upgrading datalad or add a fitting " \
                     "'ria-layout-version' file at the RIA store's " \
                     "root."
            self._set_read_only(reason + read_only_msg)

        try:
            self.verify_ds_in_store()
        except UnknownLayoutVersion:
            reason = "Remote object tree reports version {}. Supported" \
                     "versions are {}. Consider upgrading datalad or " \
                     "fix the 'ria-layout-version' file at the remote " \
                     "dataset root. " \
                     "".format(self.remote_object_tree_version,
                               self.known_versions_objt)
            self._set_read_only(reason + read_only_msg)
        except NoLayoutVersion:
            reason = "Remote doesn't report any object tree version. " \
                     "Consider upgrading datalad or add a fitting " \
                     "'ria-layout-version' file at the remote " \
                     "dataset root. "
            self._set_read_only(reason + read_only_msg)

    @handle_errors
    def initremote(self):
        # which repo are we talking about
        gitdir = self.annex.getgitdir()
        self._verify_config(gitdir, fail_noid=False)
        if not self.archive_id:
            self.archive_id = _get_datalad_id(gitdir)
            if not self.archive_id:
                # fall back on the UUID for the annex remote
                self.archive_id = self.annex.getuuid()

        if not isinstance(self.io, HTTPRemoteIO):
            self.get_store()

        # else:
        # TODO: consistency with SSH and FILE behavior? In those cases we make
        #       sure the store exists from within initremote

        self.annex.setconfig('archive-id', self.archive_id)
        # make sure, we store the potentially rewritten URL
        self.annex.setconfig('url', self.ria_store_url)

    def _local_io(self):
        """Are we doing local operations?"""
        # let's not make this decision dependent on the existence
        # of a directory the matches the name of the configured
        # store tree base dir. Such a match could be pure
        # coincidence. Instead, let's do remote whenever there
        # is a remote host configured
        #return self.store_base_path.is_dir()
        return not self.storage_host

    def debug(self, msg):
        # Annex prints just the message, so prepend with
        # a "DEBUG" on our own.
        self.annex.debug("ORA-DEBUG: " + msg)

    def message(self, msg):
        try:
            self.annex.info(msg)
        except ProtocolError:
            # INFO not supported by annex version.
            # If we can't have an actual info message, at least have a
            # debug message.
            self.debug(msg)

    def _set_read_only(self, msg):

        if not self.force_write:
            self.read_only = True
            self.message(msg)
        else:
            self.message("Was instructed to force write")

    def _ensure_writeable(self):
        if self.read_only:
            raise RIARemoteError("Remote is treated as read-only. "
                                 "Set 'ora-remote.<name>.force-write=true' to "
                                 "overrule this.")
        if isinstance(self.io, HTTPRemoteIO):
            raise RIARemoteError("Write access via HTTP not implemented")

    @property
    def io(self):
        if not self._io:
            if self._local_io():
                self._io = LocalIO()
            elif self.ria_store_url.startswith("ria+http"):
                self._io = HTTPRemoteIO(self.ria_store_url,
                                        self.archive_id,
                                        self.buffer_size)
            elif self.storage_host:
                self._io = SSHRemoteIO(self.storage_host, self.buffer_size)
                from atexit import register
                register(self._io.close)
            else:
                raise RIARemoteError(
                    "Local object tree base path does not exist, and no SSH"
                    "host configuration found.")
        return self._io

    @handle_errors
    def prepare(self):

        gitdir = self.annex.getgitdir()
        self.uuid = self.annex.getuuid()
        self._verify_config(gitdir)

        if not isinstance(self.io, HTTPRemoteIO):
            self.get_store()

        # report active special remote configuration
        self.info = {
            'store_base_path': str(self.store_base_path),
            'storage_host': 'local'
            if self._local_io() else self.storage_host,
        }

    @handle_errors
    def transfer_store(self, key, filename):
        self._ensure_writeable()

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        key_path = dsobj_dir / key_path

        if self.io.exists(key_path):
            # if the key is here, we trust that the content is in sync
            # with the key
            return

        self.io.mkdir(key_path.parent)

        # we need to copy to a temp location to let
        # checkpresent fail while the transfer is still in progress
        # and furthermore not interfere with administrative tasks in annex/objects
        # In addition include uuid, to not interfere with parallel uploads from different remotes
        transfer_dir = self.remote_git_dir / "ora-remote-{}".format(self.uuid) / "transfer"
        self.io.mkdir(transfer_dir)
        tmp_path = transfer_dir / key

        if tmp_path.exists():
            # Just in case - some parallel job could already be writing to it
            # at least tell the conclusion, not just some obscure permission error
            raise RIARemoteError('{}: upload already in progress'.format(filename))
        try:
            self.io.put(filename, tmp_path, self.annex.progress)
            # copy done, atomic rename to actual target
            self.io.rename(tmp_path, key_path)
        except Exception as e:
            # whatever went wrong, we don't want to leave the transfer location blocked
            self.io.remove(tmp_path)
            raise e

    @handle_errors
    def transfer_retrieve(self, key, filename):

        if isinstance(self.io, HTTPRemoteIO):
            self.io.get(PurePosixPath(self.annex.dirhash(key)) / key / key,
                        filename,
                        self.annex.progress)
            return

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        abs_key_path = dsobj_dir / key_path
        # sadly we have no idea what type of source gave checkpresent->true
        # we can either repeat the checks, or just make two opportunistic
        # attempts (at most)
        try:
            self.io.get(abs_key_path, filename, self.annex.progress)
        except Exception as e1:
            # catch anything and keep it around for a potential re-raise
            try:
                self.io.get_from_archive(archive_path, key_path, filename,
                                         self.annex.progress)
            except Exception as e2:
                raise RIARemoteError('Failed to key: {}'.format([str(e1), str(e2)]))

    @handle_errors
    def checkpresent(self, key):

        if isinstance(self.io, HTTPRemoteIO):
            return self.io.checkpresent(
                PurePosixPath(self.annex.dirhash(key)) / key / key)

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        abs_key_path = dsobj_dir / key_path
        if self.io.exists(abs_key_path):
            # we have an actual file for this key
            return True
        # do not make a careful check whether an archive exists, because at
        # present this requires an additional SSH call for remote operations
        # which may be rather slow. Instead just try to run 7z on it and let
        # it fail if no archive is around
        # TODO honor future 'archive-mode' flag
        return self.io.in_archive(archive_path, key_path)

    @handle_errors
    def remove(self, key):
        self._ensure_writeable()

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        key_path = dsobj_dir / key_path
        if self.io.exists(key_path):
            self.io.remove(key_path)
        key_dir = key_path
        # remove at most two levels of empty directories
        for level in range(2):
            key_dir = key_dir.parent
            try:
                self.io.remove_dir(key_dir)
            except Exception:
                break

    @handle_errors
    def getcost(self):
        # 100 is cheap, 200 is expensive (all relative to Config/Cost.hs)
        # 100/200 are the defaults for local and remote operations in
        # git-annex
        # if we have the object tree locally, operations are cheap (100)
        # otherwise expensive (200)
        return '100' if self._local_io() else '200'

    @handle_errors
    def whereis(self, key):

        if isinstance(self.io, HTTPRemoteIO):
            # display the URL for a request
            # TODO: method of HTTPRemoteIO
            return self.ria_store_url[4:] + "/annex/objects" + \
                   self.annex.dirhash(key) + "/" + key + "/" + key

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        return str(key_path) if self._local_io() \
            else '{}: {}:{}'.format(
                self.storage_host,
                self.remote_git_dir,
                sh_quote(str(key_path)),
        )

    @staticmethod
    def get_layout_locations(base_path, dsid):
        return get_layout_locations(1, base_path, dsid)

    def _get_obj_location(self, key):
        # Notes: - Changes to this method may require an update of
        #          RIARemote._layout_version
        #        - archive_path is always the same ATM. However, it might depend
        #          on `key` in the future. Therefore build the actual filename
        #          for the archive herein as opposed to `get_layout_locations`.

        if not self._last_archive_path:
            self._last_archive_path = self.remote_archive_dir / 'archive.7z'
        if self._last_keypath[0] != key:
            if self.remote_object_tree_version == '1':
                key_dir = self.annex.dirhash_lower(key)

            # If we didn't recognize the remote layout version, we set to
            # read-only and promised to at least try and read according to our
            # current version. So, treat that case as if remote version was our
            # (client's) version.
            else:
                key_dir = self.annex.dirhash(key)
            # double 'key' is not a mistake, but needed to achieve the exact
            # same layout as the annex/objects tree
            self._last_keypath = (key, Path(key_dir) / key / key)

        return self.remote_obj_dir, self._last_archive_path, \
            self._last_keypath[1]


def main():
    """cmdline entry point"""
    from annexremote import Master
    master = Master()
    remote = RIARemote(master)
    master.LinkRemote(remote)
    master.Listen()
