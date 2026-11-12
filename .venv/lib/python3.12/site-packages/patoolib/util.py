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
"""Utility functions."""

import functools
import os
import re
import platform
import sys
import shutil
import subprocess
from collections.abc import Sequence
from .log import log_info


class PatoolError(Exception):
    """Raised when errors occur."""


def backtick(cmd: Sequence[str], encoding: str = 'utf-8', check: bool = True) -> str:
    """Return decoded output from command."""
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, check=check, encoding=encoding, errors="replace"
    ).stdout


def run_under_pythonw() -> bool:
    """Return True iff this script is run with pythonw.exe on Windows."""
    return (
        os.name == 'nt'
        and sys.executable is not None
        and sys.executable.lower().endswith('pythonw.exe')
    )


def run(
    cmd: Sequence[str], verbosity: int = 0, interactive: bool = True, **kwargs
) -> int:
    """Run command without error checking.
    @return: command return code
    """
    if verbosity >= 0:
        info = " ".join(map(repr, cmd))
        log_info(f"running {info}")
    if run_under_pythonw():
        # prevent opening of additional consoles when running with pythonw.exe
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW  # pytype: disable=module-attr
        )
    if not interactive:
        # try to prevent hangs for programs requiring input
        kwargs["input"] = ""
    if verbosity < 1:
        # hide command output on stdout
        kwargs['stdout'] = subprocess.DEVNULL
    if verbosity < -1:
        # hide command output on stdout
        kwargs['stderr'] = subprocess.DEVNULL
    if kwargs:
        if verbosity > 0:
            info = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            log_info(f"    with {info}")
        if kwargs.get("shell"):
            # for shell calls the command must be a string
            cmd = " ".join(cmd)
    res = subprocess.run(cmd, check=False, **kwargs)
    return res.returncode


def run_checked(
    cmd: Sequence[str], ret_ok: Sequence[int] = (0,), interactive: bool = True, **kwargs
) -> int:
    """Run command and raise PatoolError on error."""
    retcode = run(cmd, interactive=interactive, **kwargs)
    if retcode not in ret_ok:
        msg = f"Command `{cmd}' returned non-zero exit status {retcode}"
        raise PatoolError(msg)
    return retcode


def shell_quote(value: str) -> str:
    """Quote all shell metacharacters in given string value with strong
    (i.e. single) quotes, handling the single quote especially.
    """
    if os.name == 'nt':
        return shell_quote_nt(value)
    return shell_quote_unix(value)


def shell_quote_unix(value: str) -> str:
    """Quote argument for Unix system, suitable for filename creation."""
    value = value.replace("'", r"'\''")
    return f"'{value}'"


def shell_quote_nt(value: str) -> str:
    """Quote argument for Windows systems, suitable for filename creation."""
    illegal_chars = '"<>|?*\t\n'
    for c in illegal_chars:
        if c in value:
            raise ValueError(f"Cannot quote invalid character {c} in value {value!r}")
    if value.endswith("\\"):
        raise ValueError(f"Cannot quote invalid ending backslash in value {value!r}")
    quoted_value = value
    # quote percent with leading percent
    quoted_value = quoted_value.replace('%', '%%')
    # finally wrap in double quotes
    return f'"{quoted_value}"'


def p7zip_supports_rar(program: str) -> bool:
    """Determine if the RAR codec is installed for 7z program.
    If installed, `7z i` will print something like
    ...
    Codecs:
    1   D    40301 Rar1
    1   D    40302 Rar2
    1   D    40303 Rar3
    1   D    40305 Rar5
    ...
    """
    _7z = find_program(program)
    if _7z:
        formats = backtick([_7z, "i"])
        return bool(re.search(r" Rar\d$", formats, re.MULTILINE))
    return False


def p7zip_supports_compress(program: str) -> bool:
    """Determine if COMPRESS (.Z) archives are supported for 7z program.
    If installed, `7z i` will print something like
    ...
    Formats:
    0  ......................  Z        z taz (.tar)  1F 9D
    ...
    """
    _7z = find_program(program)
    if _7z:
        formats = backtick([_7z, "i"])
        return bool(re.search(r"Z\s+z\s+taz", formats, re.MULTILINE))
    return False


def system_search_path() -> str:
    """Get the list of directories to search for executable programs."""
    path = os.environ.get("PATH", os.defpath)
    if os.name == 'nt':
        # Add some well-known archiver programs to the search path
        path = append_to_path(path, get_nt_7z_dir())
        path = append_to_path(path, get_nt_mac_dir())
        path = append_to_path(path, get_nt_winrar_dir())
    # Add peazip add-ons
    peazip_dir = get_peazip_addon_dir()
    if os.path.isdir(peazip_dir):
        for subdir in os.listdir(peazip_dir):
            path = append_to_path(path, os.path.join(peazip_dir, subdir))
    return path


def append_to_path(path: str, directory: str) -> str:
    """Add a directory to the PATH environment variable, if it is a valid
    directory.
    """
    if not os.path.isdir(directory) or directory in path:
        return path
    if not path.endswith(os.pathsep):
        path += os.pathsep
    return path + directory


@functools.cache
def find_program(program: str) -> str | None:
    """Look for given program."""
    return shutil.which(program, path=system_search_path())


def get_nt_7z_dir() -> str:
    """Return 7-Zip directory from registry, or an empty string."""
    import winreg  # noqa: PLC0415
    import platform  # noqa: PLC0415

    python_bits = platform.architecture()[0]
    keyname = r"SOFTWARE\7-Zip"
    try:
        if python_bits == '32bit' and platform.machine().endswith('64'):
            # get 64-bit registry key from 32-bit Python
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                keyname,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            )
        else:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, keyname)
        try:
            return winreg.QueryValueEx(key, "Path")[0]
        finally:
            winreg.CloseKey(key)
    except OSError:
        return ""


def get_nt_program_dir() -> str:
    """Return the Windows program files directory."""
    progvar = "%ProgramFiles%"
    return os.path.expandvars(progvar)


def get_nt_mac_dir() -> str:
    """Return Monkey Audio Compressor (MAC) directory."""
    return os.path.join(get_nt_program_dir(), "Monkey's Audio")


def get_nt_winrar_dir() -> str:
    """Return WinRAR directory."""
    return os.path.join(get_nt_program_dir(), "WinRAR")


def get_peazip_addon_dir() -> str:
    """Get platform-dependen directory for PeaZip add-ons."""
    if platform.system() == 'Windows':
        return 'C:\\Program Files\\PeaZip\\res\\bin\\'
    if platform.system() == 'Linux':
        return '/usr/lib/peazip/res/bin/'
    if platform.system() == 'Darwin':
        return '/Applications/peazip.app/Content/MacOS/bin/'
    return ''


def get_arc_format(arc_exe: str) -> str:
    """If running arc_exe without options prints "FreeArc" in its output assume
    the given arc_exe supports the freearc format. Else assume arc format support.
    """
    helptext = backtick([arc_exe], check=False)
    return "freearc" if "FreeArc" in helptext else "arc"


def strlist_with_or(alist: Sequence[str]) -> str:
    """Return comma separated string, and last entry appended with ' or '."""
    if len(alist) > 1:
        head = ", ".join(alist[:-1])
        tail = alist[-1]
        return f"{head} or {tail}"
    return ", ".join(alist)
