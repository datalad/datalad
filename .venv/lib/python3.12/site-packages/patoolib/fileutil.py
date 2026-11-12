# Copyright (C) 2010-2023 Bastian Kleineidam
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""File and directory utility functions."""

import os
import shutil
import stat
import tempfile
from collections.abc import Sequence, Callable
from .log import log_info, log_warning, log_error
from .util import PatoolError


def check_existing_filename(filename: str, onlyfiles: bool = True) -> None:
    """Ensure that given filename is a valid, existing file."""
    if not os.path.exists(filename):
        raise PatoolError(f"file `{filename}' was not found")
    if not os.access(filename, os.R_OK):
        raise PatoolError(f"file `{filename}' is not readable")
    if onlyfiles and not os.path.isfile(filename):
        raise PatoolError(f"`{filename}' is not a file")


def check_writable_filename(filename: str) -> None:
    """Ensure that the given filename is writable."""
    if not os.access(filename, os.W_OK):
        raise PatoolError(f"file `{filename}' is not writable")


def check_new_filename(filename: str) -> None:
    """Check that filename does not already exist."""
    if os.path.exists(filename):
        raise PatoolError(f"cannot overwrite existing file `{filename}'")


def check_archive_filelist(filenames: Sequence[str]) -> None:
    """Check that file list is not empty and contains only existing files."""
    if not filenames:
        raise PatoolError("cannot create archive with empty filelist")
    for filename in filenames:
        check_existing_filename(filename, onlyfiles=False)


def set_mode(filename: str, flags: int) -> None:
    """Set mode flags for given filename if not already set."""
    try:
        mode = os.lstat(filename).st_mode
    except OSError as err:
        log_warning(f"could not stat `{filename}': {err}")
        # ignore
        return
    if not (mode & flags):
        try:
            os.chmod(filename, flags | mode)
        except OSError as err:
            log_warning(f"could not set mode flags for `{filename}': {err}")


def get_filesize(filename: str) -> int:
    """Return file size in Bytes, or -1 on error."""
    return os.path.getsize(filename)


def tmpdir(dir: str | None = None, prefix: str = "Unpack_") -> str:
    """Return a temporary directory for extraction."""
    return tempfile.mkdtemp(suffix="", prefix=prefix, dir=dir)


def stripext(filename: str) -> str:
    """Return the basename without extension of given filename
    For compressed TAR archives, the filename without the .tar
    extension is returned, ie. output of 'a.tar.xz' will be
    'a'.
    """
    basename, _ = os.path.splitext(os.path.basename(filename))
    if basename.endswith(".tar") and basename != ".tar":
        basename, _ = os.path.splitext(basename)
    return basename


def get_single_outfile(directory: str, archive: str, extension: str = "") -> str:
    """Get output filename if archive is in a single file format like gzip."""
    outfile = os.path.join(directory, stripext(archive))
    if os.path.exists(outfile + extension):
        # prevent overwriting existing files
        i = 1
        newfile = f"{outfile}{i}"
        while os.path.exists(newfile + extension):
            i += 1
            newfile = f"{outfile}{i}"
        outfile = newfile
    return outfile + extension


def is_same_file(filename1: str, filename2: str) -> bool:
    """Check if filename1 and filename2 point to the same file object.
    There can be false negatives, i.e. the result is False, but it is
    the same file anyway. Reason is that network filesystems can create
    different paths to the same physical file.
    """
    if filename1 == filename2:
        return True
    if os.name == 'posix':
        return os.path.samefile(filename1, filename2)
    return is_same_filename(filename1, filename2)


def is_same_filename(filename1: str, filename2: str) -> bool:
    """Check if filename1 and filename2 are the same filename."""
    return os.path.realpath(filename1) == os.path.realpath(filename2)


def link_or_copy(src: str, dst: str, verbosity: int = 0) -> None:
    """Try to make a hard link from src to dst and if that fails
    copy the file. Hard links save some disk space and linking
    should fail fast since no copying is involved.
    """
    if verbosity > 0:
        log_info(f"Copying {src} -> {dst}")
    try:
        os.link(src, dst)
    except (AttributeError, OSError):
        try:
            shutil.copy(src, dst)
        except OSError as err:
            raise PatoolError(f"error copying {src} -> {dst}") from err


def chdir(directory: str) -> str | None:
    """Remember and return current directory before calling os.chdir().
    If the current directory could not be determined, return None.
    """
    try:
        olddir = os.getcwd()
    except OSError as err:
        log_warning(f"could not get current working directory: {err}")
        olddir = None
    os.chdir(directory)
    return olddir


def funcname(func: Callable) -> str:
    """Get function name."""
    return getattr(func, '__name__', repr(func))


def rmtree_log_exc(func: Callable, path: str, excinfo) -> None:
    """Error log function for shutil.rmtree()."""
    log_error(f"Error in {funcname(func)}({path}): {excinfo}")


def rmtree(path: str) -> None:
    """Remove given path recursively with shutil.rmtree().
    Errors will be logged.
    """
    make_user_readable(path)
    shutil.rmtree(path, onexc=rmtree_log_exc)


def make_file_readable(filename: str) -> None:
    """Make file user readable if it is not a link."""
    if not os.path.islink(filename):
        set_mode(filename, stat.S_IRUSR)


def make_dir_readable(filename: str) -> None:
    """Make directory user readable and executable."""
    set_mode(filename, stat.S_IRUSR | stat.S_IXUSR)


def make_user_readable(directory: str) -> None:
    """Make all files in given directory user readable. Also recurse into
    subdirectories.
    """
    for root, dirs, files in os.walk(directory, onerror=log_error):
        for filename in files:
            make_file_readable(os.path.join(root, filename))
        for dirname in dirs:
            make_dir_readable(os.path.join(root, dirname))


def is_within_directory(directory, target):
    """Check that given target path is a subdirectory inside the directory."""
    abs_directory = os.path.realpath(os.path.abspath(directory))
    abs_target = os.path.realpath(os.path.abspath(target))
    try:
        return os.path.commonpath([abs_directory, abs_target]) == abs_directory
    except ValueError:
        return False
