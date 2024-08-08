import functools
import logging
import os
import shutil
import stat
import subprocess
import sys
from contextlib import contextmanager
from functools import wraps
from pathlib import (
    Path,
    PurePosixPath,
)
from shlex import quote as sh_quote

import requests

from datalad import ssh_manager
from datalad.config import anything2bool
from datalad.customremotes import (
    ProtocolError,
    RemoteError,
    SpecialRemote,
)
from datalad.customremotes.main import main as super_main
from datalad.customremotes.ria_utils import (
    UnknownLayoutVersion,
    get_layout_locations,
    verify_ria_url,
)
from datalad.support.annex_utils import _sanitize_key
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    AccessDeniedError,
    AccessFailedError,
    CapturedException,
    DownloadError,
)
from datalad.support.network import url_path2local_path
from datalad.utils import (
    ensure_write_permission,
    on_osx,
)

lgr = logging.getLogger('datalad.customremotes.ria_remote')

DEFAULT_BUFFER_SIZE = 65536

# TODO
# - make archive check optional


# only use by _get_datalad_id
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


# cannot be replaced until https://github.com/datalad/datalad/issues/6264
# is fixed
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
    pass


class IOBase(object):
    """Abstract class with the desired API for local/remote operations"""

    def get_7z(self):
        raise NotImplementedError

    def mkdir(self, path):
        raise NotImplementedError

    def symlink(self, target, link_name):
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

    ensure_writeable = staticmethod(ensure_write_permission)

    def mkdir(self, path):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

    def symlink(self, target, link_name):
        os.symlink(target, link_name)

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
        # Upfront check to avoid cryptic error output
        # https://github.com/datalad/datalad/issues/4336
        if not self.exists(archive):
            raise RIARemoteError("archive {arc} does not exist."
                                 "".format(arc=archive))

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
        with self.ensure_writeable(dst.parent):
            src.rename(dst)

    def remove(self, path):
        try:
            with self.ensure_writeable(path.parent):
                path.unlink()
        except PermissionError as e:
            raise RIARemoteError(f"Unable to remove {path}. Could not "
                                 "obtain write permission for containing"
                                 "directory.") from e

    def remove_dir(self, path):
        with self.ensure_writeable(path.parent):
            path.rmdir()

    def exists(self, path):
        return path.exists()

    def in_archive(self, archive_path, file_path):
        if not archive_path.exists():
            # no archive, not file
            return False
        loc = str(file_path)
        from datalad.cmd import (
            StdOutErrCapture,
            WitlessRunner,
        )
        runner = WitlessRunner()
        # query 7z for the specific object location, keeps the output
        # lean, even for big archives
        out = runner.run(
            ['7z', 'l', str(archive_path),
             loc],
            protocol=StdOutErrCapture,
        )
        return loc in out['stdout']

    def read_file(self, file_path):

        with open(str(file_path), 'r') as f:
            content = f.read()
        return content

    def write_file(self, file_path, content, mode='w'):
        if not content.endswith('\n'):
            content += '\n'
        with open(str(file_path), mode) as f:
            f.write(content)

    def get_7z(self):
        from datalad.cmd import (
            CommandError,
            StdOutErrCapture,
            WitlessRunner,
        )

        # from datalad.utils import on_windows

        runner = WitlessRunner()
        # TODO: To not rely on availability in PATH we might want to use `which`
        #       (`where` on windows) and get the actual path to 7z to reuse in
        #       in_archive() and get().
        #       Note: `command -v XXX` or `type` might be cross-platform
        #       solution!
        #       However, for availability probing only, it would be sufficient
        #       to just call 7z and see whether it returns zero.

        # cmd = 'where' if on_windows else 'which'
        # try:
        #     out = runner.run([cmd, '7z'], protocol=StdOutErrCapture)
        #     return out['stdout']
        # except CommandError:
        #     return None

        try:
            runner.run('7z', protocol=StdOutErrCapture)
            return True
        except (FileNotFoundError, CommandError):
            return False


class SSHRemoteIO(IOBase):
    """IO operation if the object tree is SSH-accessible

    It doesn't even think about a windows server.
    """

    # output markers to detect possible command failure as well as end of output
    # from a particular command:
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

        # the connection to the remote
        # we don't open it yet, not yet clear if needed
        self.ssh = ssh_manager.get_connection(
            host,
            use_remote_annex_bundle=False,
        )
        self.ssh.open()
        # open a remote shell
        cmd = ['ssh'] + self.ssh._ssh_args + [self.ssh.sshri.as_str()]
        self.shell = subprocess.Popen(cmd,
                                      stderr=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE,
                                      stdin=subprocess.PIPE)
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

        # lazy property to store the remote unix name
        self._remote_uname = None

    @property
    def remote_uname(self):
        """Remote unix system name, lazy resolution

        If accessed for the first time, runs uname -s to find out

        """
        if self._remote_uname is None:
            self._remote_uname = self._run(
                "uname -s", no_output=False, check=True
            ).rstrip()
        return self._remote_uname

    def close(self):
        # try exiting shell clean first
        self.shell.stdin.write(b"exit\n")
        self.shell.stdin.flush()
        exitcode = self.shell.wait(timeout=0.5)
        # be more brutal if it doesn't work
        if exitcode is None:  # timed out
            # TODO: Theoretically terminate() can raise if not successful.
            #       How to deal with that?
            self.shell.terminate()

    def _append_end_markers(self, cmd):
        """Append end markers to remote command"""

        return cmd + " && printf '%s\\n' {} || printf '%s\\n' {}\n".format(
            sh_quote(self.REMOTE_CMD_OK),
            sh_quote(self.REMOTE_CMD_FAIL))

    def _get_download_size_from_key(self, key):
        """Get the size of an annex object file from it's key

        Note, that this is not necessarily the size of the annexed file, but
        possibly only a chunk of it.

        Parameter
        ---------
        key: str
          annex key of the file

        Returns
        -------
        int
          size in bytes
        """
        # TODO: datalad's AnnexRepo.get_size_from_key() is not correct/not
        #       fitting. Incorporate the wisdom there, too.
        #       We prob. don't want to actually move this method there, since
        #       AnnexRepo would be quite an expensive import. Startup time for
        #       special remote matters.
        # TODO: this method can be more compact. we don't need particularly
        #       elaborated error distinction

        # see: https://git-annex.branchable.com/internals/key_format/
        key_parts = key.split('--')
        key_fields = key_parts[0].split('-')

        s = S = C = None

        for field in key_fields[1:]:  # note: first has to be backend -> ignore
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

        # TODO: we might want to redirect stderr to stdout here (or have
        #       additional end marker in stderr) otherwise we can't empty stderr
        #       to be ready for next command. We also can't read stderr for
        #       better error messages (RemoteError) without making sure there's
        #       something to read in any case (it's blocking!).
        #       However, if we are sure stderr can only ever happen if we would
        #       raise RemoteError anyway, it might be okay.
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
                    raise RemoteCommandFailedError(
                        "{cmd} failed: {msg}".format(cmd=cmd,
                                                     msg="".join(lines[:-1]))
                    )
                else:
                    break
        if no_output and len(lines) > 1:
            raise RIARemoteError("{}: {}".format(call, "".join(lines)))
        return "".join(lines[:-1])

    @contextmanager
    def ensure_writeable(self, path):
        """Context manager to get write permission on `path` and restore
        original mode afterwards.

        If git-annex ever touched the key store, the keys will be in mode 444
        directories, and we need to obtain permission first.

        Parameters
        ----------
        path: Path
          path to the target file
        """

        path = sh_quote(str(path))

        # remember original mode -- better than to prescribe a fixed mode
        if self.remote_uname == "Darwin":
            format_option = "-f%Dp"
            # on macOS this would return decimal representation of mode (same
            # as python's stat().st_mode
            conversion = int
        else:  # win is currently ignored anyway
            format_option = "--format=\"%f\""
            # in opposition to the above form for macOS, on debian this would
            # yield the hexadecimal representation of the mode; hence conversion
            # needed.
            conversion = functools.partial(int, base=16)

        output = self._run(f"stat {format_option} {path}",
                           no_output=False, check=True)
        mode = conversion(output)
        if not mode & stat.S_IWRITE:
            new_mode = oct(mode | stat.S_IWRITE)[-3:]
            self._run(f"chmod {new_mode} {path}")
            changed = True
        else:
            changed = False
        try:
            yield
        finally:
            if changed:
                # restore original mode
                self._run("chmod {mode} {file}".format(mode=oct(mode)[-3:],
                                                       file=path),
                          check=False)  # don't fail if path doesn't exist
                                        # anymore

    def mkdir(self, path):
        self._run('mkdir -p {}'.format(sh_quote(str(path))))

    def symlink(self, target, link_name):
        self._run('ln -s {} {}'.format(sh_quote(str(target)), sh_quote(str(link_name))))

    def put(self, src, dst, progress_cb):
        self.ssh.put(str(src), str(dst))

    def get(self, src, dst, progress_cb):

        # Note, that as we are in blocking mode, we can't easily fail on the
        # actual get (that is 'cat').
        # Therefore check beforehand.
        if not self.exists(src):
            raise RIARemoteError("annex object {src} does not exist."
                                 "".format(src=src))

        from os.path import basename
        key = basename(str(src))
        try:
            size = self._get_download_size_from_key(key)
        except RemoteError as e:
            raise RemoteError(f"src: {src}") from e

        if size is None:
            # rely on SCP for now
            self.ssh.get(str(src), str(dst))
            return

        # TODO: see get_from_archive()

        # TODO: Currently we will hang forever if the file isn't readable and
        #       it's supposed size is bigger than whatever cat spits out on
        #       stdout. This is because we don't notice that cat has exited
        #       non-zero. We could have end marker on stderr instead, but then
        #       we need to empty stderr beforehand to not act upon output from
        #       earlier calls. This is a problem with blocking reading, since we
        #       need to make sure there's actually something to read in any
        #       case.
        cmd = 'cat {}'.format(sh_quote(str(src)))
        self.shell.stdin.write(cmd.encode())
        self.shell.stdin.write(b"\n")
        self.shell.stdin.flush()

        with open(dst, 'wb') as target_file:
            bytes_received = 0
            while bytes_received < size:
                # TODO: some additional abortion criteria? check stderr in
                #       addition?
                c = self.shell.stdout.read1(self.buffer_size)
                # no idea yet, whether or not there's sth to gain by a
                # sophisticated determination of how many bytes to read at once
                # (like size - bytes_received)
                if c:
                    bytes_received += len(c)
                    target_file.write(c)
                    progress_cb(bytes_received)

    def rename(self, src, dst):
        with self.ensure_writeable(dst.parent):
            self._run('mv {} {}'.format(sh_quote(str(src)), sh_quote(str(dst))))

    def remove(self, path):
        try:
            with self.ensure_writeable(path.parent):
                self._run('rm {}'.format(sh_quote(str(path))), check=True)
        except RemoteCommandFailedError as e:
            raise RIARemoteError(f"Unable to remove {path} "
                                 "or to obtain write permission in parent directory.") from e

    def remove_dir(self, path):
        with self.ensure_writeable(path.parent):
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

        # Note, that as we are in blocking mode, we can't easily fail on the
        # actual get (that is 'cat'). Therefore check beforehand.
        if not self.exists(archive):
            raise RIARemoteError("archive {arc} does not exist."
                                 "".format(arc=archive))

        # TODO: We probably need to check exitcode on stderr (via marker). If
        #       archive or content is missing we will otherwise hang forever
        #       waiting for stdout to fill `size`.

        cmd = '7z x -so {} {}\n'.format(
            sh_quote(str(archive)),
            sh_quote(str(src)))
        self.shell.stdin.write(cmd.encode())
        self.shell.stdin.flush()

        # TODO: - size needs double-check and some robustness
        #       - can we assume src to be a posixpath?
        #       - RF: Apart from the executed command this should be pretty much
        #         identical to self.get(), so move that code into a common
        #         function

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
        except RemoteCommandFailedError as e:
            # Currently we don't read stderr. All we know is, we couldn't read.
            # Try narrowing it down by calling a subsequent exists()
            if not self.exists(file_path):
                raise FileNotFoundError(f"{str(file_path)} not found.") from e
            else:
                raise RuntimeError(f"Could not read {file_path}") from e

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
        except RemoteCommandFailedError as e:
            raise RIARemoteError(f"Could not write to {file_path}") from e

    def get_7z(self):
        # TODO: To not rely on availability in PATH we might want to use `which`
        #       (`where` on windows) and get the actual path to 7z to reuse in
        #       in_archive() and get().
        #       Note: `command -v XXX` or `type` might be cross-platform
        #       solution!
        #       However, for availability probing only, it would be sufficient
        #       to just call 7z and see whether it returns zero.

        try:
            self._run("7z", check=True, no_output=False)
            return True
        except RemoteCommandFailedError:
            return False

        # try:
        #     out = self._run("which 7z", check=True, no_output=False)
        #     return out
        # except RemoteCommandFailedError:
        #     return None


class HTTPRemoteIO(object):
    # !!!!
    # This is not actually an IO class like SSHRemoteIO and LocalIO and needs
    # respective RF'ing of special remote implementation eventually.
    # We want ORA over HTTP, but with a server side CGI to talk to in order to
    # reduce the number of requests. Implementing this as such an IO class would
    # mean to have separate requests for all server side executions, which is
    # what we do not want. As a consequence ORARemote class implementation needs
    # to treat HTTP as a special case until refactoring to a design that fits
    # both approaches.

    # NOTE: For now read-only. Not sure yet whether an IO class is the right
    # approach.

    def __init__(self, url, buffer_size=DEFAULT_BUFFER_SIZE):
        from datalad.downloaders.providers import Providers
        if not url.startswith("http"):
            raise RIARemoteError("Expected HTTP URL, but got {}".format(url))

        self.store_url = url.rstrip('/')

        # make sure default is used when None was passed, too.
        self.buffer_size = buffer_size if buffer_size else DEFAULT_BUFFER_SIZE
        self._providers = Providers.from_config_files()

    def checkpresent(self, key_path):
        # Note, that we need the path with hash dirs, since we don't have access
        # to annexremote.dirhash from within IO classes

        return self.exists(key_path)

    def get(self, key_path, filename, progress_cb):
        # Note, that we need the path with hash dirs, since we don't have access
        # to annexremote.dirhash from within IO classes

        url = self.store_url + str(key_path)
        self._providers.download(url, path=filename, overwrite=True)

    def exists(self, path):
        # use same signature as in SSH and Local IO, although validity is
        # limited in case of HTTP.
        url = self.store_url + path.as_posix()
        try:
            response = requests.head(url, allow_redirects=True)
        except Exception as e:
            raise RIARemoteError from e

        return response.status_code == 200

    def read_file(self, file_path):

        from datalad.support.network import download_url
        url = self.store_url + file_path.as_posix()
        try:
            content = download_url(url)

            # NOTE re Exception handling:
            # We reraise here to:
            #   1. Unify exceptions across IO classes
            #   2. Get cleaner user messages. ATM what we get from the
            #   Downloaders are exceptions, that have their cause-chain baked
            #   into their string rather than being e proper exception chain.
            #   Hence, we can't generically extract the ultimate cause.
            #   RemoteError will eventually pass the entire chain string to
            #   annex. If we add our own exception here on top, this is what is
            #   displayed first to the user, rather than being buried deep into
            #   a hard to parse message.
        except AccessDeniedError as exc:
            raise PermissionError(f"Permission denied: '{url}'") from exc

        except DownloadError as exc:
            # Note: This comes from the downloader. `check_response_status`
            # in downloaders/http.py does not currently use
            # `raise_from_status`, hence we don't get a proper HTTPError to
            # check for a 404 and thereby distinguish from connection issues.
            # When this is addressed in the downloader code, we need to
            # adjust here.
            if "not found" in str(exc):
                # Raise uniform exception across IO classes:
                raise FileNotFoundError(f"{url} not found.") from exc
            else:
                # Note: There's AccessFailedError(DownloadError) as well.
                # However, we can't really tell them meaningfully apart,
                # since possible underlying HTTPErrors, etc. are baked into
                # their strings. Hence, "Failed to access" is what we can
                # tell here in either case.
                raise RuntimeError(f"Failed to access {url}") from exc
        return content


def handle_errors(func):
    """Decorator to convert and log errors

    Intended to use with every method of RiaRemote class, facing the outside
    world. In particular, that is about everything, that may be called via
    annex' special remote protocol, since a non-RemoteError will simply result
    in a broken pipe by default handling.
    """

    # TODO: configurable on remote end (flag within layout_version!)

    @wraps(func)
    def _wrap_handle_errors(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            if self.remote_log_enabled:
                try:
                    from datetime import datetime
                    from traceback import format_exc
                    exc_str = format_exc()
                    entry = "{time}: Error:\n{exc_str}\n" \
                            "".format(time=datetime.now(),
                                      exc_str=exc_str)
                    # ensure base path is platform path
                    log_target = (
                        url_path2local_path(self.store_base_path)
                        / "error_logs"
                        / "{dsid}.{uuid}.log".format(
                            dsid=self.archive_id,
                            uuid=self._repo.uuid))
                    self.io.write_file(log_target, entry, mode='a')
                except Exception:
                    # If logging of the exception does fail itself, there's
                    # nothing we can do about it. Hence, don't log and report
                    # the original issue only.
                    # TODO: With a logger that doesn't sabotage the
                    #  communication with git-annex, we should be abe to use
                    #  CapturedException here, in order to get an informative
                    #  traceback in a debug message.
                    pass

            try:
                # We're done using io, so let it perform any needed cleanup. At
                # the moment, this is only relevant for SSHRemoteIO, in which
                # case it cleans up the SSH socket and prevents a hang with
                # git-annex 8.20201103 and later.
                from atexit import unregister
                if self._io:
                    self._io.close()
                    unregister(self._io.close)
                if self._push_io:
                    self._push_io.close()
                    unregister(self._push_io.close)
            except AttributeError:
                # seems like things are already being cleaned up -> a good
                pass
            except Exception:
                # anything else: Not a problem. We are about to exit anyway
                pass

            if not isinstance(e, RIARemoteError):
                raise RIARemoteError from e
            else:
                raise e

    return _wrap_handle_errors


class NoLayoutVersion(Exception):
    pass


class ORARemote(SpecialRemote):
    """This is the class of RIA remotes.
    """

    dataset_tree_version = '1'
    object_tree_version = '2'
    # TODO: Move known versions. Needed by creation routines as well.
    known_versions_objt = ['1', '2']
    known_versions_dst = ['1']

    @handle_errors
    def __init__(self, annex):
        super(ORARemote, self).__init__(annex)
        if hasattr(self, 'configs'):
            # introduced in annexremote 1.4.2 to support LISTCONFIGS
            self.configs['url'] = "RIA store to use"
            self.configs['push-url'] = "URL for pushing to the RIA store. " \
                                       "Optional."
            self.configs['archive-id'] = "Dataset ID (fallback: annex uuid. " \
                                         "Should be set automatically by " \
                                         "datalad"
        # the local repo
        self._repo = None
        self.gitdir = None
        self.name = None  # name of the special remote
        self.gitcfg_name = None  # name in respective git remote

        self.ria_store_url = None
        self.ria_store_pushurl = None
        # machine to SSH-log-in to access/store the data
        # subclass must set this
        self.storage_host = None
        self.storage_host_push = None
        # must be absolute, and POSIX (will be instance of PurePosixPath)
        # subclass must set this
        self.store_base_path = None
        self.store_base_path_push = None
        # by default we can read and write
        self.read_only = False
        self.force_write = None
        self.ignore_remote_config = None
        self.remote_log_enabled = None
        self.remote_dataset_tree_version = None
        self.remote_object_tree_version = None

        # for caching the remote's layout locations:
        self.remote_git_dir = None
        self.remote_archive_dir = None
        self.remote_obj_dir = None
        # lazy IO:
        self._io = None
        self._push_io = None

        # cache obj_locations:
        self._last_archive_path = None
        self._last_keypath = (None, None)

        # SSH "streaming" buffer
        self.buffer_size = DEFAULT_BUFFER_SIZE

    def verify_store(self):
        """Check whether the store exists and reports a layout version we
        know

        The layout of the store is recorded in base_path/ria-layout-version.
        If the version found on the remote end isn't supported and `force-write`
        isn't configured, sets the remote to read-only operation.
        """

        # ensure base path is platform path
        dataset_tree_version_file = \
            url_path2local_path(self.store_base_path) / 'ria-layout-version'

        # check dataset tree version
        try:
            self.remote_dataset_tree_version = \
                self._get_version_config(dataset_tree_version_file)
        except Exception as exc:
            raise RIARemoteError("RIA store unavailable.") from exc
        if self.remote_dataset_tree_version not in self.known_versions_dst:
            # Note: In later versions, condition might change in order to
            # deal with older versions.
            raise UnknownLayoutVersion(f"RIA store layout version unknown: "
                                       f"{self.remote_dataset_tree_version}")

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
        except Exception as e:
            raise RIARemoteError("Dataset unavailable from RIA store.")
        if self.remote_object_tree_version not in self.known_versions_objt:
            raise UnknownLayoutVersion(f"RIA dataset layout version unknown: "
                                       f"{self.remote_object_tree_version}")

    def _load_local_cfg(self):

        # this will work, even when this is not a bare repo
        # but it is not capable of reading out dataset/branch config
        self._repo = AnnexRepo(self.gitdir)

        cfg_map = {"ora-force-write": "force_write",
                   "ora-ignore-ria-config": "ignore_remote_config",
                   "ora-buffer-size": "buffer_size",
                   "ora-url": "ria_store_url",
                   "ora-push-url": "ria_store_pushurl"
                   }

        # in initremote we may not have a reliable name of the git remote config
        # yet. Go with the default.
        gitcfg_name = self.gitcfg_name or self.name
        if gitcfg_name:
            for cfg, att in cfg_map.items():
                value = self._repo.config.get(f"remote.{gitcfg_name}.{cfg}")
                if value is not None:
                    self.__setattr__(cfg_map[cfg], value)
                    if cfg == "ora-url":
                        self.ria_store_url_source = 'local'
                    elif cfg == "ora-push-url":
                        self.ria_store_pushurl_source = 'local'
            if self.buffer_size:
                try:
                    self.buffer_size = int(self.buffer_size)
                except ValueError:
                    self.message(f"Invalid value of config "
                                 f"'remote.{gitcfg_name}."
                                 f"ora-buffer-size': {self.buffer_size}")
                    self.buffer_size = DEFAULT_BUFFER_SIZE

        if self.name:
            # Consider deprecated configs if there's no value yet
            if self.force_write is None:
                self.force_write = self._repo.config.get(
                    f'annex.ora-remote.{self.name}.force-write')
                if self.force_write:
                    self.message("WARNING: config "
                                 "'annex.ora-remote.{}.force-write' is "
                                 "deprecated. Use 'remote.{}.ora-force-write' "
                                 "instead.".format(self.name, self.gitcfg_name))
                    try:
                        self.force_write = anything2bool(self.force_write)
                    except TypeError:
                        raise RIARemoteError("Invalid value of config "
                                             "'annex.ora-remote.{}.force-write'"
                                             ": {}".format(self.name,
                                                           self.force_write))

            if self.ignore_remote_config is None:
                self.ignore_remote_config = self._repo.config.get(
                    f"annex.ora-remote.{self.name}.ignore-remote-config")
                if self.ignore_remote_config:
                    self.message("WARNING: config "
                                 "'annex.ora-remote.{}.ignore-remote-config' is"
                                 " deprecated. Use "
                                 "'remote.{}.ora-ignore-ria-config' instead."
                                 "".format(self.name, self.gitcfg_name))
                    try:
                        self.ignore_remote_config = \
                            anything2bool(self.ignore_remote_config)
                    except TypeError:
                        raise RIARemoteError(
                            "Invalid value of config "
                            "'annex.ora-remote.{}.ignore-remote-config': {}"
                            "".format(self.name, self.ignore_remote_config))

    def _load_committed_cfg(self, fail_noid=True):

        # which repo are we talking about
        self.gitdir = self.annex.getgitdir()

        # go look for an ID
        self.archive_id = self.annex.getconfig('archive-id')
        if fail_noid and not self.archive_id:
            # TODO: Message! "archive ID" is confusing. dl-id or annex-uuid
            raise RIARemoteError(
                "No archive ID configured. This should not happen.")

        # what is our uuid?
        self.uuid = self.annex.getuuid()

        # RIA store URL(s)
        self.ria_store_url = self.annex.getconfig('url')
        if self.ria_store_url:
            self.ria_store_url_source = 'annex'
        self.ria_store_pushurl = self.annex.getconfig('push-url')
        if self.ria_store_pushurl:
            self.ria_store_pushurl_source = 'annex'

        # TODO: This should prob. not be done! Would only have an effect if
        #       force-write was committed annex-special-remote-config and this
        #       is likely a bad idea.
        self.force_write = self.annex.getconfig('force-write')
        if self.force_write == "":
            self.force_write = None

        # Get the special remote name
        # TODO: Make 'name' a property of `SpecialRemote`;
        #       Same for `gitcfg_name`, `_repo`?
        self.name = self.annex.getconfig('name')
        if not self.name:
            self.name = self.annex.getconfig('sameas-name')
        if not self.name:
            # TODO: Do we need to crash? Not necessarily, I think. We could
            #       still find configs and if not - might work out.
            raise RIARemoteError(
                "Cannot determine special remote name, got: {}".format(
                    repr(self.name)))
        # Get the name of the remote entry in .git/config.
        # Note, that this by default is the same as the stored name of the
        # special remote, but can be different (for example after
        # git-remote-rename). The actual connection is the uuid of the special
        # remote, not the name.
        try:
            self.gitcfg_name = self.annex.getgitremotename()
        except (ProtocolError, AttributeError):
            # GETGITREMOTENAME not supported by annex version or by annexremote
            # version.
            # Lets try to find ourselves: Find remote with matching annex uuid
            response = _get_gitcfg(self.gitdir,
                                   r"^remote\..*\.annex-uuid",
                                   regex=True)
            response = response.splitlines() if response else []
            candidates = set()
            for line in response:
                k, v = line.split()
                if v == self.annex.getuuid():  # TODO: Where else? self.uuid?
                    candidates.add(''.join(k.split('.')[1:-1]))
            num_candidates = len(candidates)
            if num_candidates == 1:
                self.gitcfg_name = candidates.pop()
            elif num_candidates > 1:
                self.message("Found multiple used remote names in git "
                             "config: %s" % str(candidates))
                # try same name:
                if self.name in candidates:
                    self.gitcfg_name = self.name
                    self.message("Choose '%s'" % self.name)
                else:
                    self.gitcfg_name = None
                    self.message("Ignore git config")
            else:
                # No entry found.
                # Possible if we are in "initremote".
                self.gitcfg_name = None

    def _load_cfg(self, gitdir, name):
        # Whether or not to force writing to the remote. Currently used to
        # overrule write protection due to layout version mismatch.
        self.force_write = self._repo.config.get(
            f'annex.ora-remote.{name}.force-write')

        # whether to ignore config flags set at the remote end
        self.ignore_remote_config = \
            self._repo.config.get(
                f'annex.ora-remote.{name}.ignore-remote-config')

        # buffer size for reading files over HTTP and SSH
        self.buffer_size = self._repo.config.get(
            f"remote.{name}.ora-buffer-size")

        if self.buffer_size:
            self.buffer_size = int(self.buffer_size)

    def _verify_config(self, fail_noid=True):
        # try loading all needed info from (git) config

        # first load committed config
        self._load_committed_cfg(fail_noid=fail_noid)
        # now local configs (possible overwrite of committed)
        self._load_local_cfg()

        # get URL rewriting config
        url_cfgs = {k: v for k, v in self._repo.config.items()
                    if k.startswith('url.')}

        if self.ria_store_url:
            self.storage_host, self.store_base_path, self.ria_store_url = \
                verify_ria_url(self.ria_store_url, url_cfgs)

        else:
            # There's one exception to the precedence of local configs:
            # Age-old "ssh-host" + "base-path" configs are only considered,
            # if there was no RIA URL (local or committed). However, issue
            # deprecation warning, if that situation is encountered:
            host = None
            path = None

            if self.name:
                host = self._repo.config.get(
                    f'annex.ora-remote.{self.name}.ssh-host') or \
                       self.annex.getconfig('ssh-host')
                # Note: Special value '0' is replaced by None only after checking
                # the repository's annex config. This is to uniformly handle '0' and
                # None later on, but let a user's config '0' overrule what's
                # stored by git-annex.
                self.storage_host = None if host == '0' else host
                path = self._repo.config.get(
                    f'annex.ora-remote.{self.name}.base-path') or \
                       self.annex.getconfig('base-path')
                self.store_base_path = path.strip() if path else path

            if path or host:
                self.message("WARNING: base-path + ssh-host configs are "
                             "deprecated and won't be considered in the future."
                             " Use 'git annex enableremote {} "
                             "url=<RIA-URL-TO-STORE>' to store a ria+<scheme>:"
                             "//... URL in the special remote's config."
                             "".format(self.name),
                             type='info')


        if not self.store_base_path:
            raise RIARemoteError(
                "No base path configured for RIA store. Specify a proper "
                "ria+<scheme>://... URL.")

        # the base path is ultimately derived from a URL, always treat as POSIX
        self.store_base_path = PurePosixPath(self.store_base_path)
        if not self.store_base_path.is_absolute():
            raise RIARemoteError(
                'Non-absolute RIA store base path configuration: %s'
                '' % str(self.store_base_path))

        if self.ria_store_pushurl:
            if self.ria_store_pushurl.startswith("ria+http"):
                raise RIARemoteError("Invalid push-url: {}. Pushing over HTTP "
                                     "not implemented."
                                     "".format(self.ria_store_pushurl))
            self.storage_host_push, \
            self.store_base_path_push, \
            self.ria_store_pushurl = \
                verify_ria_url(self.ria_store_pushurl, url_cfgs)
            self.store_base_path_push = PurePosixPath(self.store_base_path_push)

    def _get_version_config(self, path):
        """ Get version and config flags from RIA store's layout file
        """

        if self.ria_store_url:
            # construct path to ria_layout_version file for reporting
            local_store_base_path = url_path2local_path(self.store_base_path)
            target_ri = (
                self.ria_store_url[4:]
                + "/"
                + path.relative_to(local_store_base_path).as_posix()
            )
        elif self.storage_host:
            target_ri = "ssh://{}{}".format(self.storage_host, path.as_posix())
        else:
            target_ri = path.as_uri()

        try:
            file_content = self.io.read_file(path).strip().split('|')

        # Note, that we enhance the reporting here, as the IO classes don't
        # uniformly operate on that kind of RI (which is more informative
        # as it includes the store base address including the access
        # method).
        except FileNotFoundError as exc:
            raise NoLayoutVersion(
                f"{target_ri} not found, "
                f"self.ria_store_url: {self.ria_store_url}, "
                f"self.store_base_pass: {self.store_base_path}, "
                f"self.store_base_pass_push: {self.store_base_path_push}, "
                f"path: {type(path)} {path}") from exc
        except PermissionError as exc:
            raise PermissionError(f"Permission denied: {target_ri}") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to access {target_ri}") from exc

        if not (1 <= len(file_content) <= 2):
            self.message("invalid version file {}".format(path),
                         type='info')
            return None

        remote_version = file_content[0]
        remote_config_flags = file_content[1] \
            if len(file_content) == 2 else None
        if not self.ignore_remote_config and remote_config_flags:
            # Note: 'or', since config flags can come from toplevel
            #       (dataset-tree-root) as well as from dataset-level.
            #       toplevel is supposed flag the entire tree.
            self.remote_log_enabled = self.remote_log_enabled or \
                                      'l' in remote_config_flags

        return remote_version

    def get_store(self):
        """checks the remote end for an existing store and dataset

        Furthermore reads and stores version and config flags, layout
        locations, etc.
        If this doesn't raise, the remote end should be fine to work with.
        """
        # make sure the base path is a platform path when doing local IO
        # the incoming Path object is a PurePosixPath
        # XXX this else branch is wrong: Incoming is PurePosixPath
        # but it is subsequently assumed to be a platform path, by
        # get_layout_locations() etc. Hence it must be converted
        # to match the *remote* platform, not the local client
        store_base_path = (
            url_path2local_path(self.store_base_path)
            if self._local_io
            else self.store_base_path)

        # cache remote layout directories
        self.remote_git_dir, self.remote_archive_dir, self.remote_obj_dir = \
            self.get_layout_locations(store_base_path, self.archive_id)

        read_only_msg = "Treating remote as read-only in order to " \
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
        self._verify_config(fail_noid=False)
        if not self.archive_id:
            self.archive_id = _get_datalad_id(self.gitdir)
            if not self.archive_id:
                # fall back on the UUID for the annex remote
                self.archive_id = self.annex.getuuid()

        self.get_store()

        self.annex.setconfig('archive-id', self.archive_id)
        # Make sure, we store the potentially rewritten URL. But only, if the
        # source was annex as opposed to a local config.
        if self.ria_store_url and self.ria_store_url_source == 'annex':
            self.annex.setconfig('url', self.ria_store_url)
        if self.ria_store_pushurl and self.ria_store_pushurl_source == 'annex':
            self.annex.setconfig('push-url', self.ria_store_pushurl)

    def _local_io(self):
        """Are we doing local operations?"""
        # let's not make this decision dependent on the existence
        # of a directory the matches the name of the configured
        # store tree base dir. Such a match could be pure
        # coincidence. Instead, let's do remote whenever there
        # is a remote host configured
        #return self.store_base_path.is_dir()

        # TODO: Isn't that wrong with HTTP anyway?
        #       + just isinstance(LocalIO)?
        # XXX isinstance(LocalIO) would not work, this method is used
        # before LocalIO is instantiated
        return not self.storage_host

    def _set_read_only(self, msg):

        if not self.force_write:
            self.read_only = True
            self.message(msg, type='info')
        else:
            self.message("Was instructed to force write", type='info')

    def _ensure_writeable(self):
        if self.read_only:
            raise RIARemoteError("Remote is treated as read-only. "
                                 "Set 'ora-remote.<name>.force-write=true' to "
                                 "overrule this.")
        if isinstance(self.push_io, HTTPRemoteIO):
            raise RIARemoteError("Write access via HTTP not implemented")

    @property
    def io(self):
        if not self._io:
            if self._local_io():
                self._io = LocalIO()
            elif self.ria_store_url.startswith("ria+http"):
                # TODO: That construction of "http(s)://host/" should probably
                #       be moved, so that we get that when we determine
                #       self.storage_host. In other words: Get the parsed URL
                #       instead and let HTTPRemoteIO + SSHRemoteIO deal with it
                #       uniformly. Also: Don't forget about a possible port.

                url_parts = self.ria_store_url[4:].split('/')
                # we expect parts: ("http(s):", "", host:port, path)
                self._io = HTTPRemoteIO(
                    url_parts[0] + "//" + url_parts[2],
                    self.buffer_size
                )
            elif self.storage_host:
                self._io = SSHRemoteIO(self.storage_host, self.buffer_size)
                from atexit import register
                register(self._io.close)
            else:
                raise RIARemoteError(
                    "Local object tree base path does not exist, and no SSH"
                    "host configuration found.")
        return self._io

    @property
    def push_io(self):
        # Instance of an IOBase subclass for execution based on configured
        # 'push-url' if such exists. Otherwise identical to `self.io`.
        # Note, that once we discover we need to use the push-url (that is on
        # TRANSFER_STORE and REMOVE), we should switch all operations to that IO
        # instance instead of using different connections for read and write
        # operations. Ultimately this is due to the design of annex' special
        # remote protocol - we don't know which annex command is running and
        # therefore we don't know whether to use fetch or push URL during
        # PREPARE.

        if not self._push_io:
            if self.ria_store_pushurl:
                self.message("switching ORA to push-url")
                # Not-implemented-push-HTTP is ruled out already when reading
                # push-url, so either local or SSH:
                if not self.storage_host_push:
                    # local operation
                    self._push_io = LocalIO()
                else:
                    self._push_io = SSHRemoteIO(self.storage_host_push,
                                                self.buffer_size)

                # We have a new instance. Kill the existing one and replace.
                from atexit import (
                    register,
                    unregister,
                )
                if hasattr(self.io, 'close'):
                    unregister(self.io.close)
                    self.io.close()

                # XXX now also READ IO is done with the write IO
                # this explicitly ignores the remote config
                # that distinguishes READ from WRITE with different
                # methods
                self._io = self._push_io
                if hasattr(self.io, 'close'):
                    register(self.io.close)

                self.storage_host = self.storage_host_push
                self.store_base_path = self.store_base_path_push

                # delete/update cached locations:
                self._last_archive_path = None
                self._last_keypath = (None, None)

                store_base_path = (
                    url_path2local_path(self.store_base_path)
                    if self._local_io
                    else self.store_base_path)

                self.remote_git_dir, \
                self.remote_archive_dir, \
                self.remote_obj_dir = \
                    self.get_layout_locations(store_base_path, self.archive_id)

            else:
                # no push-url: use existing IO
                self._push_io = self._io

        return self._push_io

    @handle_errors
    def prepare(self):

        gitdir = self.annex.getgitdir()
        self._repo = AnnexRepo(gitdir)
        self._verify_config()

        self.get_store()

        # report active special remote configuration/status
        self.info = {
            'store_base_path': str(self.store_base_path),
            'storage_host': 'local'
            if self._local_io() else self.storage_host,
        }

        # TODO: following prob. needs hasattr instead:
        if not isinstance(self.io, HTTPRemoteIO):
            self.info['7z'] = ("not " if not self.io.get_7z() else "") + \
                              "available"

    @handle_errors
    def transfer_store(self, key, filename):
        self._ensure_writeable()

        # we need a file-system compatible name for the key
        key = _sanitize_key(key)

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        key_path = dsobj_dir / key_path

        if self.push_io.exists(key_path):
            # if the key is here, we trust that the content is in sync
            # with the key
            return

        self.push_io.mkdir(key_path.parent)

        # We need to copy to a temp location to let checkpresent fail while the
        # transfer is still in progress and furthermore not interfere with
        # administrative tasks in annex/objects.
        # In addition include uuid, to not interfere with parallel uploads from
        # different clones.
        transfer_dir = \
            self.remote_git_dir / "ora-remote-{}".format(self._repo.uuid) / "transfer"
        self.push_io.mkdir(transfer_dir)
        tmp_path = transfer_dir / key

        try:
            self.push_io.put(filename, tmp_path, self.annex.progress)
            # copy done, atomic rename to actual target
            self.push_io.rename(tmp_path, key_path)
        except Exception as e:
            # whatever went wrong, we don't want to leave the transfer location
            # blocked
            self.push_io.remove(tmp_path)
            raise e

    @handle_errors
    def transfer_retrieve(self, key, filename):
        # we need a file-system compatible name for the key
        key = _sanitize_key(key)

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        abs_key_path = dsobj_dir / key_path
        # sadly we have no idea what type of source gave checkpresent->true
        # we can either repeat the checks, or just make two opportunistic
        # attempts (at most)
        try:
            self.io.get(abs_key_path, filename, self.annex.progress)
        except Exception as e1:
            if isinstance(self.io, HTTPRemoteIO):
                # no client-side archive access over HTTP
                # Note: This is intentional, as it would mean one additional
                # request per key. However, server response to the GET can
                # consider archives on their end.
                raise
            # catch anything and keep it around for a potential re-raise
            try:
                self.io.get_from_archive(archive_path, key_path, filename,
                                         self.annex.progress)
            except Exception as e2:
                # TODO properly report the causes
                raise RIARemoteError('Failed to obtain key: {}'
                                     ''.format([str(e1), str(e2)]))

    @handle_errors
    def checkpresent(self, key):
        # we need a file-system compatible name for the key
        key = _sanitize_key(key)

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        abs_key_path = dsobj_dir / key_path
        if self.io.exists(abs_key_path):
            # we have an actual file for this key
            return True
        if isinstance(self.io, HTTPRemoteIO):
            # no client-side archive access over HTTP
            return False
        # do not make a careful check whether an archive exists, because at
        # present this requires an additional SSH call for remote operations
        # which may be rather slow. Instead just try to run 7z on it and let
        # it fail if no archive is around
        # TODO honor future 'archive-mode' flag
        return self.io.in_archive(archive_path, key_path)

    @handle_errors
    def remove(self, key):
        # we need a file-system compatible name for the key
        key = _sanitize_key(key)

        self._ensure_writeable()

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        key_path = dsobj_dir / key_path
        if self.push_io.exists(key_path):
            self.push_io.remove(key_path)
        key_dir = key_path
        # remove at most two levels of empty directories
        for level in range(2):
            key_dir = key_dir.parent
            try:
                self.push_io.remove_dir(key_dir)
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
        # we need a file-system compatible name for the key
        key = _sanitize_key(key)

        dsobj_dir, archive_path, key_path = self._get_obj_location(key)
        if isinstance(self.io, HTTPRemoteIO):
            # display the URL for a request
            # TODO: method of HTTPRemoteIO
            # in case of a HTTP remote (unchecked for others), storage_host
            # is not just a host, but a full URL without a path
            return f'{self.storage_host}{dsobj_dir}/{key_path}'

        return str(dsobj_dir / key_path) if self._local_io() \
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
        #          ORARemote._layout_version
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

    # TODO: implement method 'error'


def main():
    """cmdline entry point"""
    super_main(
        cls=ORARemote,
        remote_name='ora',
        description=\
        "transport file content to and from datasets hosted in RIA stores",
    )
