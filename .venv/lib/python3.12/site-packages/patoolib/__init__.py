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
"""Main package providing archive functions for the patoolib package.
See __all__ for all exported functions.
"""

import sys

# check for compatible Python version before importing other packages
if not hasattr(sys, "version_info") or sys.version_info < (3, 12, 0, "final", 0):
    raise SystemExit("This program requires Python 3.12 or later.")
import functools
import inspect
import os
import shutil
import importlib
import subprocess
from collections.abc import Sequence, Callable

# PEP 396: supply __version__
from .configuration import App, Version as __version__  # noqa: F401
from . import fileutil, log, util

# export API functions
__all__ = [
    'create_archive',
    'diff_archives',
    'extract_archive',
    'is_archive',
    'list_archive',
    'list_formats',
    'repack_archive',
    'search_archive',
    'supported_formats',
    'test_archive',
]


# Supported archive commands
ArchiveCommands: tuple[str, ...] = ('list', 'extract', 'test', 'create')

# Supported archive formats
ArchiveFormats: tuple[str, ...] = (
    '7z',
    'ace',
    'adf',
    'alzip',
    'ape',
    'ar',
    'arc',
    'arj',
    'bzip2',
    'bzip3',
    'cab',
    'chm',
    'compress',
    'cpio',
    'deb',
    'dms',
    'flac',
    'freearc',
    'gzip',
    'iso',
    'lrzip',
    'lz4',
    'lzh',
    'lzip',
    'lzma',
    'lzop',
    'rar',
    'rpm',
    'rzip',
    'shar',
    'shn',
    'tar',
    'udf',
    'vhd',
    'wim',
    'xz',
    'zip',
    'zoo',
    'zpaq',
    'zstd',
)

# Supported compressions (used with tar for example)
# Note that all compressions must also be archive formats
ArchiveCompressions: tuple[str, ...] = (
    'bzip2',
    'compress',
    'gzip',
    'lzip',
    'lzma',
    'xz',
    'zstd',
)

# Map MIME types to archive format
ArchiveMimetypes: dict[str, str] = {
    'application/gzip': 'gzip',
    'application/jar': 'zip',  # reported on older systems such as ubuntu 14.04
    'application/java-archive': 'zip',
    'application/vnd.android.package-archive': 'zip',
    'application/vnd.ms-cab-compressed': 'cab',
    'application/x-7z-compressed': '7z',
    'application/x-ace': 'ace',
    'application/x-adf': 'adf',
    'application/x-alzip': 'alzip',
    'application/x-archive': 'ar',
    'application/x-arc': 'arc',
    'application/x-arj': 'arj',
    'application/x-bzip2': 'bzip2',
    'application/x-bzip3': 'bzip3',
    'application/x-cab': 'cab',
    'application/x-chm': 'chm',
    'application/x-compress': 'compress',
    'application/x-cpio': 'cpio',
    'application/x-debian-package': 'deb',
    'application/x-dms': 'dms',
    'application/x-freearc': 'freearc',
    'application/x-iso9660-image': 'iso',
    'application/x-lz4': 'lz4',
    'application/x-lzop': 'lzop',
    'application/x-lzma': 'lzma',
    'application/x-lzip': 'lzip',
    'application/x-lha': 'lzh',
    'application/x-lrzip': 'lrzip',
    'application/x-lzh': 'lzh',
    'application/x-ms-wim': 'wim',
    'application/x-rpm': 'rpm',
    'application/x-rzip': 'rzip',
    'application/x-shar': 'shar',
    'application/x-tar': 'tar',
    'application/x-iso13346-image': 'udf',
    'application/x-vhd': 'vhd',
    'application/x-xz': 'xz',
    'application/x-zip-compressed': 'zip',
    'application/x-zoo': 'zoo',
    'application/vnd.rar': 'rar',
    'application/zip': 'zip',
    'application/zpaq': 'zpaq',
    "application/zstd": "zstd",
    'audio/x-ape': 'ape',
    'audio/x-shn': 'shn',
    'audio/flac': 'flac',
}

# List of programs supporting the given archive format and command.
# If command is None, the program supports all commands (list, extract, ...)
# Programs starting with "py_" are Python modules.
# {<format>: {<command>: (<program>,...)}
ArchivePrograms: dict[str, dict[str | None, tuple[str, ...]]] = {
    '7z': {
        None: ('7z', '7za', '7zr', '7zz', '7zzs'),
        'extract': ('unar',),
    },
    'ace': {
        'extract': ('unace', 'unar'),
        'test': ('unace',),
        'list': ('unace',),
    },
    'adf': {
        'extract': ('unadf',),
        'test': ('unadf',),
        'list': ('unadf',),
    },
    'alzip': {
        'extract': ('unalz',),
        'test': ('unalz',),
        'list': ('unalz',),
    },
    'ape': {
        'create': ('mac',),
        'extract': ('mac',),
        'list': ('py_echo',),
        'test': ('mac',),
    },
    'ar': {
        None: ('ar',),
    },
    # Note:
    # ".arc" files can be in ARC or FREEARC format
    # https://en.wikipedia.org/wiki/ARC_(file_format)
    # https://en.wikipedia.org/wiki/FreeArc
    'arc': {
        None: ('arc',),
        'extract': ('nomarch',),
        'test': ('nomarch',),
        'list': ('nomarch',),
    },
    'freearc': {
        None: ('arc',),
    },
    'arj': {
        None: ('arj',),
        'extract': ('7z', '7zz', '7zzs'),
        'list': ('7z', '7zz', '7zzs'),
        'test': ('7z', '7zz', '7zzs'),
    },
    'bzip2': {
        None: ('7z', '7za', '7zz', '7zzs'),
        'extract': ('pbzip2', 'lbzip2', 'bzip2', 'unar', 'py_bz2'),
        'test': ('pbzip2', 'lbzip2', 'bzip2'),
        'create': ('pbzip2', 'lbzip2', 'bzip2', 'py_bz2'),
        'list': ('py_echo',),
    },
    'bzip3': {
        'extract': ('bzip3',),
        'test': ('bzip3',),
        'create': ('bzip3',),
        'list': ('py_echo',),
    },
    'cab': {
        'extract': ('cabextract', '7z', '7zz', '7zzs', 'unar'),
        'create': ('lcab',),
        'list': ('cabextract', '7z', '7zz', '7zzs'),
        'test': ('cabextract', '7z', '7zz', '7zzs'),
    },
    'chm': {
        'extract': ('7z', '7zz', '7zzs', 'archmage', 'extract_chmLib'),
        'test': ('7z', '7zz', '7zzs', 'archmage'),
        'list': ('7z', '7zz', '7zzs'),
    },
    'compress': {
        'extract': ('gzip', '7z', '7za', '7zz', '7zzs', 'unar', 'uncompress.real'),
        'list': (
            '7z',
            '7za',
            '7zz',
            '7zzs',
            'py_echo',
        ),
        'test': ('gzip', '7z', '7za', '7zz', '7zzs'),
        'create': ('compress',),
    },
    'cpio': {
        'extract': ('cpio', 'bsdcpio', '7z', '7zz', '7zzs', 'unar'),
        'list': ('cpio', 'bsdcpio', '7z', '7zz', '7zzs'),
        'test': ('cpio', 'bsdcpio', '7z', '7zz', '7zzs'),
        'create': ('cpio', 'bsdcpio'),
    },
    'flac': {
        'extract': ('flac',),
        'test': ('flac',),
        'create': ('flac',),
        'list': ('py_echo',),
    },
    'gzip': {
        None: ('7z', '7za', '7zz', '7zzs', 'pigz', 'gzip'),
        'extract': (
            'unar',
            'py_gzip',
        ),
        'create': ('zopfli', 'py_gzip'),
    },
    'iso': {
        'extract': ('7z', '7zz', '7zzs', 'unar'),
        'list': ('7z', '7zz', '7zzs', 'isoinfo'),
        'test': (
            '7z',
            '7zz',
            '7zzs',
        ),
        'create': ('genisoimage',),
    },
    'lz4': {None: ('lz4',)},
    'lzh': {
        None: ('lha',),
        'extract': ('lhasa', 'unar'),
    },
    'lzip': {
        'extract': ('plzip', 'lzip', 'clzip', 'pdlzip'),
        'list': ('py_echo',),
        'test': ('plzip', 'lzip', 'clzip', 'pdlzip'),
        'create': ('plzip', 'lzip', 'clzip', 'pdlzip'),
    },
    'lzma': {
        'extract': ('7z', '7zz', '7zzs', 'lzma', 'xz', 'unar', 'py_lzma'),
        'list': ('7z', '7zz', '7zzs', 'py_echo'),
        'test': ('7z', '7zz', '7zzs', 'lzma', 'xz'),
        'create': ('lzma', 'xz', 'py_lzma'),
    },
    'lrzip': {
        'extract': ('lrzip',),
        'list': ('py_echo',),
        'test': ('lrzip',),
        'create': ('lrzip',),
    },
    'rar': {
        None: ('rar',),
        'extract': ('unrar', '7z', '7zz', '7zzs', 'unar'),
        'list': ('unrar', '7z', '7zz', '7zzs'),
        'test': ('unrar', '7z', '7zz', '7zzs'),
    },
    'rpm': {
        'extract': ('rpm2cpio', '7z', '7zz', '7zzs'),
        'list': ('rpm', '7z', '7za', '7zz', '7zzs'),
        'test': ('rpm', '7z', '7zz', '7zzs'),
    },
    'deb': {
        'extract': ('dpkg-deb', '7z', '7zz', '7zzs'),
        'list': ('dpkg-deb', '7z', '7zz', '7zzs'),
        'test': ('dpkg-deb', '7z', '7zz', '7zzs'),
    },
    'dms': {
        'extract': ('xdms', 'unar'),
        'list': ('xdms',),
        'test': ('xdms',),
    },
    'lzop': {
        None: ('lzop',),
    },
    'rzip': {
        'extract': ('rzip',),
        'list': ('py_echo',),
        'create': ('rzip',),
    },
    'shar': {
        'create': ('shar',),
        'extract': ('unshar',),
    },
    'shn': {
        'extract': ('shorten',),
        'list': ('py_echo',),
        'create': ('shorten',),
    },
    'tar': {
        None: ('tar', 'star', 'bsdtar', 'py_tarfile'),
        'extract': ('unar',),
    },
    'udf': {
        'extract': ('7z',),
        'list': ('7z',),
        'test': ('7z',),
    },
    'vhd': {
        'extract': (
            '7z',
            '7zz',
            '7zzs',
        ),
        'list': (
            '7z',
            '7zz',
            '7zzs',
        ),
        'test': (
            '7z',
            '7zz',
            '7zzs',
        ),
    },
    'wim': {
        None: ('7z', '7zz', '7zzs'),
    },
    'xz': {
        None: ('xz', '7z', '7zz', '7zzs'),
        'extract': (
            'unar',
            'py_lzma',
        ),
        'create': ('py_lzma',),
    },
    'zip': {
        None: ('7z', '7za', '7zz', '7zzs', 'py_zipfile'),
        'extract': ('unzip', 'unar', 'jar'),
        'list': ('unzip', 'jar'),
        'test': (
            'zip',
            'unzip',
        ),
        'create': ('zip',),
    },
    'zoo': {
        None: ('zoo',),
        'extract': ('unar',),
    },
    'zpaq': {
        None: (
            'zpaqfranz',
            'zpaq',
        ),
    },
    "zstd": {
        None: ("zstd",),
        "create": ("py_zstd",),
        "extract": ("py_zstd",),
    },
}

# List of programs by archive type, which don't support password use
NoPasswordSupportArchivePrograms: dict[str, dict[str | None, tuple[str, ...]]] = {
    'bzip2': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'cab': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'arj': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'gzip': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'iso': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'cpio': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'rpm': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'deb': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'lzma': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'udf': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'vhd': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'xz': {
        None: (
            '7z',
            '7zz',
            '7zzs',
        )
    },
    'zip': {
        'create': ('py_zipfile',),
        'extract': ('jar',),
        'list': ('jar',),
    },
}

# List those programs that have different python module names because of
# Python module naming restrictions.
ProgramModules: dict[str, str] = {
    '7z': 'p7zip',
    '7za': 'p7azip',
    '7zr': 'p7rzip',
    '7zz': 'p7zz',
    '7zzs': 'p7zzs',
    'uncompress.real': 'uncompress',
    'dpkg-deb': 'dpkg',
    'extract_chmlib': 'chmlib',
}


@functools.cache
def program_supports_compression(
    command: str, program: str, exe: str, compression: str
) -> bool:
    """Decide if the given program supports the compression natively.
    The result is memoized since this function can call the given program
    for testing if it supports certain options.

    @return: True iff the program supports the given compression format
      natively, else False.
    """
    if program in ('tar', 'star', 'bsdtar'):
        # Unfortunately, different tar implementations support different compressions,
        # even while having the same program name.
        # So a better way to determine support is by running the tar program itself.
        # Use the following features (which are hopefully true on all platforms):
        # * tar programs support the "--help" option
        # * tar programs exit with error on unsupported options
        # * tar programs allow long option --<compression> for supported compressions
        # This way running "tar --<compression> --help" determines, if the compression is supported
        cmd = [exe, f"--{compression}", "--help"]
        if util.run(cmd, stderr=subprocess.DEVNULL, verbosity=-1) != 0:
            # compression is not supported by this tar implementation
            return False
        # in addition to the commandline option, tar also needs the corresponding compression program
        if util.find_program(compression):
            # the compression program is available for tar
            if (
                program == 'tar'
                and command == 'create'
                and compression == 'xz'
                and os.name == 'nt'
            ):
                # The native tar.exe on windows does not support creating tar.xz archives,
                # even when xz.exe is available. Complicated ...
                return False
            return True
    elif program in ('py_tarfile',):
        # the python tarfile module has a fixed list of supported compression modules
        try:
            from compression import zstd  # noqa: F401, PLC0415

            # Python >= 3.14 has zstd support and can extract tar.zst files.
            return compression in ('gzip', 'bzip2', 'lzma', 'xz', 'zstd')
        except ImportError:
            return compression in ('gzip', 'bzip2', 'lzma', 'xz')
    return False


from .mime import guess_mime, Encoding2Mime  # noqa: E402


def is_archive(filename: str) -> bool:
    """Detect if the file is a known archive.

    Example: patoolib.is_archive("package.deb")

    :param filename: The filename to check. Can be relative to the current working directory or absolute.
    :type filename: str
    :return: True if given filename is an archive file.
    :rtype: bool
    """
    mime, _compression = guess_mime(filename)
    return mime in ArchiveMimetypes


def get_archive_format(filename: str, verbosity: int = 0) -> tuple[str, str | None]:
    """Detect filename archive format and optional compression."""
    mime, compression = guess_mime(filename)
    if verbosity >= 2:
        log.log_info(
            f"archive {filename} has mime {mime} and compression {compression}"
        )
    if not (mime or compression):
        raise util.PatoolError(f"unknown archive format for file `{filename}'")
    if mime in ArchiveMimetypes:
        format = ArchiveMimetypes[mime]
    else:
        raise util.PatoolError(
            f"unknown archive mime format {mime} for file `{filename}'"
        )
    if verbosity >= 1:
        log.log_info(f"detected format {format} for archive {filename}")
    if format == compression:
        # file cannot be in same format compressed
        compression = None
    return format, compression


def check_archive_format(format: str, compression: str | None) -> None:
    """Make sure format and compression is known."""
    if format not in ArchiveFormats:
        raise util.PatoolError(f"unknown archive format `{format}'")
    if compression is not None and compression not in ArchiveCompressions:
        raise util.PatoolError(f"unknown archive compression `{compression}'")


def find_archive_program(
    format: str,
    command: str,
    program: str | None = None,
    password: str | None = None,
    compression: str | None = None,
    verbosity: int = 0,
) -> str:
    """Find suitable archive program for given format and mode."""
    commands = ArchivePrograms[format]
    programs = []
    if program is not None:
        # try a specific program first
        programs.append(program)
    # first try the universal programs with key None
    for key in (None, command):
        if key in commands:
            programs.extend(commands[key])
    if password is not None:
        programs = _remove_command_without_password_support(programs, format, command)
    if not programs:
        raise util.PatoolError(f"{command} archive format `{format}' is not supported")
    # return the first existing program
    for program in programs:
        if program.startswith('py_'):
            # it's a Python module, check if it is supported
            try:
                get_patool_program_module(program)
                return program
            except ImportError:
                pass
            continue
        exe = util.find_program(program)
        if exe:
            if program in ('7z', '7zz', '7zzs', '7za'):
                if format == 'rar' and not util.p7zip_supports_rar(program):
                    continue
                if format == 'compress' and not util.p7zip_supports_compress(program):
                    continue
            elif program == 'arc':
                # arc program supports either ARC or FREEARC formats
                # find out if it's the one we need
                if util.get_arc_format(exe) != format:
                    continue
            if not check_program_compression(
                command, program, exe, compression, verbosity=verbosity
            ):
                continue
            return exe

    if compression is not None and compression in Encoding2Mime:
        # there is no program supporting the archive format with the given compression
        # try to fall back to an archive program for only the compression encoding
        if verbosity >= 0:
            msg = f"could not find an executable program to {command} format {format} and compression {compression}, trying to run {command} only for {compression}"
            log.log_info(msg)
        return find_archive_program(
            Encoding2Mime[compression],
            command,
            program=program,
            verbosity=verbosity,
        )

    # no programs found
    msg = f"could not find an executable program to {command} format {format}"
    if compression is not None:
        msg += f" and compression {compression}"
    msg += "; candidates are " + ",".join(programs)
    raise util.PatoolError(msg)


def check_program_compression(
    command: str, program: str, exe: str, compression: str | None, verbosity: int = 0
) -> bool:
    """Check if a program supports the given compression.

    @return:
      + True if compression is None or empty
      + True if given program supports the archive compression
      + False else
    """
    if not compression:
        return True
    # check if compression is supported
    if program_supports_compression(command, program, exe, compression):
        return True
    if command == 'create':
        comp_command = command
    else:
        comp_command = 'extract'
    comp_prog = find_archive_program(compression, comp_command, verbosity=verbosity)
    if comp_prog:
        return True
    return False


def _remove_command_without_password_support(
    programs: Sequence[str], format: str, command: str
) -> Sequence[str]:
    """Remove programs if they don't support passwords for current format and command."""
    if format not in NoPasswordSupportArchivePrograms:
        return programs
    no_password_support_commands = NoPasswordSupportArchivePrograms[format]
    no_password_support_programs = set()
    for key in (None, command):
        if key in no_password_support_commands:
            for program in no_password_support_commands[key]:
                no_password_support_programs.add(program)
    programs_with_support = []
    for program in programs:
        if program not in no_password_support_programs:
            programs_with_support.append(program)
    if not programs_with_support and programs:
        raise util.PatoolError(
            f"{command} archive format `{format}' with password is not supported"
        )
    return programs_with_support


def list_formats() -> None:
    """Print information about available archive formats to stdout.

    :return: None
    :rtype:  None
    """
    print("Archive programs of", App)
    print("Archive programs are searched in the following directories:")
    print(util.system_search_path())
    print()
    for format in ArchiveFormats:
        print(format, "files:")
        for command in ArchiveCommands:
            programs = ArchivePrograms[format]
            if command not in programs and None not in programs:
                print(f"   {command:>8}: - (not supported)")
                continue
            try:
                program = find_archive_program(format, command)
                print(f"   {command:>8}: {program}", end=' ')
                if format == 'tar':
                    encs = [x for x in ArchiveCompressions if util.find_program(x)]
                    if encs:
                        print(
                            "(supported compressions: {})".format(", ".join(encs)),
                            end=' ',
                        )
                elif format == '7z':
                    if util.p7zip_supports_rar(program):
                        print("(rar archives supported)", end=' ')
                    else:
                        print("(rar archives not supported)", end=' ')
                print()
            except util.PatoolError:
                # display information what programs can handle this archive format
                handlers = programs.get(None, programs.get(command))
                print(
                    f"   {command:>8}: - (no program found; install {util.strlist_with_or(handlers)})"  # ty: ignore[invalid-argument-type]
                )


def supported_formats(operations: Sequence[str] = ArchiveCommands) -> list[str]:
    """Return a list of supported archive formats for an iterable of operations.

    :param operations: The operations to check for, defaults to ArchiveCommands.
    :type operations:  List|Tuple|Set|Dict[str]
    :return:           A list of supported archive formats.
    :rtype:            List[str]
    """
    supported = list(ArchiveFormats)
    for format in ArchiveFormats:
        # NOTE: If we wish to include supported formats in the CLI
        # argparse default nargs to an empty list, so we would need some
        # check to set operations to ArchiveCommands if bool(operations) is False.
        for command in operations:
            try:
                find_archive_program(format, command)
            except util.PatoolError:
                supported.remove(format)
                break
    return supported


def move_outdir_orphan(outdir: str) -> tuple[bool, str]:
    """Move a single file or directory inside outdir a level up.
    Never overwrite files.
    Return (True, outfile) if successful, (False, reason) if not.
    """
    entries = os.listdir(outdir)
    if len(entries) == 1:
        src = os.path.join(outdir, entries[0])
        dst = os.path.join(os.path.dirname(outdir), entries[0])
        if os.path.exists(dst) or os.path.islink(dst):
            return (False, "local file exists")
        shutil.move(src, dst)
        os.rmdir(outdir)
        return (True, entries[0])
    return (False, "multiple files in root")


def run_archive_cmdlist(
    archive_cmdlist: Sequence[str] | tuple[Sequence[str], dict],
    verbosity: int = 0,
    interactive: bool = True,
) -> int:
    """Run archive command.

    @return: exit code
    """
    # archive_cmdlist is a command list with optional keyword arguments
    if isinstance(archive_cmdlist, tuple):
        cmdlist, runkwargs = archive_cmdlist
    else:
        cmdlist, runkwargs = archive_cmdlist, {}
    return util.run_checked(
        cmdlist,
        verbosity=verbosity,
        interactive=interactive,
        **runkwargs,  # ty: ignore[invalid-argument-type]
    )


def cleanup_outdir(outdir: str, archive: str) -> tuple[str, str]:
    """Cleanup outdir after extraction and return target file name and
    result string.
    """
    fileutil.make_user_readable(outdir)
    # move single directory or file in outdir
    (success, msg) = move_outdir_orphan(outdir)
    if success:
        # msg is a single directory or filename
        return msg, f"`{msg}'"
    # outdir remains unchanged
    # rename it to something more user-friendly (basically the archive
    # name without extension)
    outdir2 = fileutil.get_single_outfile("", archive)
    os.rename(outdir, outdir2)
    return outdir2, f"`{outdir2}' ({msg})"


def _extract_archive(
    archive: str,
    verbosity: int = 0,
    interactive: bool = True,
    outdir: str | None = None,
    program: str | None = None,
    format: str | None = None,
    compression: str | None = None,
    password: str | None = None,
) -> str:
    """Extract an archive.

    @return: output directory
    """
    if format is None:
        format, compression = get_archive_format(archive, verbosity=verbosity)
    check_archive_format(format, compression)
    program = find_archive_program(
        format,
        'extract',
        program=program,
        password=password,
        compression=compression,
        verbosity=verbosity,
    )
    get_archive_cmdlist = get_archive_cmdlist_func(program, 'extract', format)
    if outdir is None:
        outdir = fileutil.tmpdir(dir=".")
        do_cleanup_outdir = True
    else:
        do_cleanup_outdir = False
        if os.path.exists(outdir):
            if not os.path.isdir(outdir):
                msg = f"output path `{outdir}' exists and is not a directory"
                raise util.PatoolError(msg)
        else:
            if verbosity >= 0:
                log.log_info(f"... creating output directory `{outdir}'.")
            os.makedirs(outdir)
    try:
        cmdlist = get_archive_cmdlist(
            archive,
            compression,
            program,
            verbosity,
            interactive,
            outdir,
            password=password,
        )
        if cmdlist:
            # an empty command list means the get_archive_cmdlist() function
            # already handled the command (e.g. when it's a builtin Python
            # function)
            run_archive_cmdlist(cmdlist, verbosity=verbosity, interactive=interactive)
        if do_cleanup_outdir:
            target, msg = cleanup_outdir(outdir, archive)
        else:
            target, msg = outdir, f"`{outdir}'"
        if verbosity >= 0:
            log.log_info(f"... {archive} extracted to {msg}.")
        return target
    finally:
        # try to remove an empty temporary output directory
        if do_cleanup_outdir and os.path.isdir(outdir):
            try:
                os.rmdir(outdir)
            except OSError as err:
                if sys.exc_info()[0] is not None:
                    msg = (
                        "extraction error, could not remove temporary "
                        f"extraction directory {outdir}: {err}"
                    )
                    log.log_error(msg)


def _create_archive(
    archive: str,
    filenames: Sequence[str],
    verbosity: int = 0,
    interactive: bool = True,
    program: str | None = None,
    format: str | None = None,
    compression: str | None = None,
    password: str | None = None,
) -> None:
    """Create an archive."""
    if format is None:
        format, compression = get_archive_format(archive, verbosity=verbosity)
    check_archive_format(format, compression)
    program = find_archive_program(
        format,
        'create',
        program=program,
        password=password,
        compression=compression,
        verbosity=verbosity,
    )
    get_archive_cmdlist = get_archive_cmdlist_func(program, 'create', format)
    cmdlist = get_archive_cmdlist(
        archive,
        compression,
        program,
        verbosity,
        interactive,
        filenames,
        password=password,
    )
    if cmdlist:
        # an empty command list means the get_archive_cmdlist() function
        # already handled the command (e.g. when it's a builtin Python
        # function)
        run_archive_cmdlist(cmdlist, verbosity=verbosity, interactive=interactive)


def _handle_archive(
    archive: str,
    command: str,
    verbosity: int = 0,
    interactive: bool = True,
    program: str | None = None,
    format: str | None = None,
    compression: str | None = None,
    password: str | None = None,
) -> None:
    """Test and list archives."""
    if format is None:
        format, compression = get_archive_format(archive, verbosity=verbosity)
    check_archive_format(format, compression)
    if command not in ('list', 'test'):
        raise util.PatoolError(f"invalid archive command `{command}'")
    program = find_archive_program(
        format,
        command,
        program=program,
        password=password,
        compression=compression,
        verbosity=verbosity,
    )
    get_archive_cmdlist = get_archive_cmdlist_func(program, command, format)
    # prepare keyword arguments for command list
    cmdlist = get_archive_cmdlist(
        archive, compression, program, verbosity, interactive, password=password
    )
    if cmdlist:
        # an empty command list means the get_archive_cmdlist() function
        # already handled the command (e.g. when it's a builtin Python
        # function)
        run_archive_cmdlist(cmdlist, verbosity=verbosity, interactive=interactive)


def get_patool_program_module(program):
    """Get the patool module for given program."""
    key = fileutil.stripext(os.path.basename(program).lower())
    # modules are stored in "programs" submodule
    modulename = ".programs." + ProgramModules.get(key, key)
    # import the module
    return importlib.import_module(modulename, __name__)


def get_archive_cmdlist_func(program: str, command: str, format: str) -> Callable:
    """Get the Python function that executes the given program."""
    # get python module for given archive program
    try:
        module = get_patool_program_module(program)
    except ImportError as err:
        msg = f"cannot import program module {program} in {__name__}"
        raise util.PatoolError(msg) from err
    # get archive handler function (e.g. patoolib.programs.star.extract_tar)
    try:
        archive_cmdlist_func = getattr(module, f'{command}_{format}')
    except AttributeError as err:
        msg = f"could not find {command}_{format} in {module}"
        raise util.PatoolError(msg) from err

    def check_for_password_before_cmdlist_func_call(*args, **kwargs):
        """If password is None, or not set, run command as usual.
        If password is set, but can't be accepted raise appropriate
        message.
        """
        if 'password' in kwargs and kwargs['password'] is None:
            kwargs.pop('password')
        if 'password' not in kwargs:
            return archive_cmdlist_func(*args, **kwargs)
        if 'password' in inspect.signature(archive_cmdlist_func).parameters:
            return archive_cmdlist_func(*args, **kwargs)
        msg = f'There is no support for password in {program}'
        raise util.PatoolError(msg)

    return check_for_password_before_cmdlist_func_call


def _diff_archives(
    archive1: str, archive2: str, verbosity: int = 0, interactive: bool = True
) -> int:
    """Show differences between two archives.
    @return 0 if archives are the same, else 1
    @raises: PatoolError on errors
    """
    if fileutil.is_same_file(archive1, archive2):
        return 0
    diff = util.find_program("diff")
    if not diff:
        msg = "The diff(1) program is required for showing archive differences, please install it."
        raise util.PatoolError(msg)
    tmpdir1 = fileutil.tmpdir()
    try:
        path1 = _extract_archive(archive1, outdir=tmpdir1, verbosity=-1)
        entries1 = os.listdir(tmpdir1)
        tmpdir2 = fileutil.tmpdir()
        try:
            path2 = _extract_archive(archive2, outdir=tmpdir2, verbosity=-1)
            entries2 = os.listdir(tmpdir2)
            if len(entries1) == 1 and len(entries2) == 1:
                # when both archives only have one single entry, compare those
                diffpath1 = os.path.join(path1, entries1[0])
                diffpath2 = os.path.join(path2, entries2[0])
            else:
                diffpath1 = path1
                diffpath2 = path2
            return util.run_checked(
                [diff, "-urN", diffpath1, diffpath2], verbosity=1, ret_ok=(0, 1)
            )
        finally:
            fileutil.rmtree(tmpdir2)
    finally:
        fileutil.rmtree(tmpdir1)


def _search_archive(
    pattern: str,
    archive: str,
    verbosity: int = 0,
    interactive: bool = True,
    password: str | None = None,
) -> int:
    """Search for given pattern in an archive."""
    grep = util.find_program("grep")
    if not grep:
        msg = "The grep(1) program is required for searching archive contents, please install it."
        raise util.PatoolError(msg)
    tmpdir = fileutil.tmpdir()
    try:
        path = _extract_archive(archive, outdir=tmpdir, verbosity=-1, password=password)
        return util.run_checked(
            [grep, "-r", "-e", pattern, "."], ret_ok=(0, 1), verbosity=1, cwd=path
        )
    finally:
        fileutil.rmtree(tmpdir)


def _repack_archive(
    archive1: str,
    archive2: str,
    verbosity: int = 0,
    interactive: bool = True,
    password: str | None = None,
) -> None:
    """Repackage an archive to a different format."""
    format1, compression1 = get_archive_format(archive1, verbosity=verbosity)
    format2, compression2 = get_archive_format(archive2, verbosity=verbosity)
    if format1 == format2 and compression1 == compression2:
        # same format and compression allows to copy the file
        if verbosity >= 0:
            log.log_info(
                f"copy `{archive1}' -> `{archive2}' in same format {format1} and compression {compression1}"
            )
        fileutil.link_or_copy(archive1, archive2, verbosity=verbosity)
        return
    tmpdir = fileutil.tmpdir()
    try:
        same_format = format1 == format2 and compression1 and compression2
        if same_format:
            # only decompress since the format is the same
            format = compression1
        else:
            format = None
        path = _extract_archive(
            archive1,
            verbosity=verbosity,
            outdir=tmpdir,
            password=password,
            format=format,
        )
        archive = os.path.abspath(archive2)
        files = tuple(os.listdir(path))
        olddir = os.getcwd()
        os.chdir(path)
        try:
            if same_format:
                # only compress since the format is the same
                format = compression2
            else:
                format = None
            _create_archive(
                archive,
                files,
                verbosity=verbosity,
                interactive=interactive,
                password=password,
                format=format,
            )
        finally:
            os.chdir(olddir)
    finally:
        fileutil.rmtree(tmpdir)


# the patool library API


def extract_archive(
    archive: str,
    verbosity: int = 0,
    outdir: str | None = None,
    program: str | None = None,
    interactive: bool = True,
    password: str | None = None,
    format: str | None = None,
) -> str:
    """Extract an archive file.

    Extracting never overwrites existing files or directories. The original archive file is kept after
    extraction, even if all files were successful extracted.

    Example: patoolib.extract_archive("archive.zip", outdir="/tmp")

    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param outdir: The directory where the archive should be extracted. A value of None (the default)
         uses the current working directory.
    :type outdir: str or None
    :param program: If None (the default), a list of suitable archive programs are checked if they
         exist in the system search path (defined by the PATH environment variable).
         If a program name is given, it is added to the list of programs that is searched for.
         The program should be a relative or absolute path name to an executable.
    :type program: str or None
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :param format: If given, use this archive format instead of auto-detection.
    :type format: str or None
    :raise patoolib.PatoolError: If an archive does not exist or is not a regular file, or on errors while
         extracting.
    :return: The directory where the archive has been extracted.
    :rtype: str
    """
    fileutil.check_existing_filename(archive)
    if verbosity >= 0:
        log.log_info(f"Extracting {archive} ...")
    return _extract_archive(
        archive,
        verbosity=verbosity,
        interactive=interactive,
        outdir=outdir,
        program=program,
        password=password,
        format=format,
    )


def list_archive(
    archive: str,
    verbosity: int = 1,
    program: str | None = None,
    interactive: bool = True,
    password: str | None = None,
    format: str | None = None,
) -> None:
    """List given archive.

    Example: patoolib.list_archive("package.deb")

    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param program: If None (the default), a list of suitable archive programs are checked if they
         exist in the system search path (defined by the PATH environment variable).
         If a program name is given, it is added to the list of programs that is searched for.
         The program should be a relative or absolute path name to an executable.
    :type program: str or None
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :param format: If given, use this archive format instead of auto-detection.
    :type format: str or None
    :raise patoolib.PatoolError: If an archive does not exist or is not a regular file, or on errors while
         listing.
    :return: None
    :rtype: None
    """
    # Set default verbosity to 1 since the listing output should be visible.
    fileutil.check_existing_filename(archive)
    if verbosity >= 0:
        log.log_info(f"Listing {archive} ...")
    return _handle_archive(
        archive,
        'list',
        verbosity=verbosity,
        interactive=interactive,
        program=program,
        password=password,
        format=format,
    )


def test_archive(
    archive: str,
    verbosity: int = 0,
    program: str | None = None,
    interactive: bool = True,
    password: str | None = None,
    format: str | None = None,
) -> None:
    """Test given archive.

    Example: patoolib.test_archive("dist.tar.gz", verbosity=1)

    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param program: If None (the default), a list of suitable archive programs are checked if they
         exist in the system search path (defined by the PATH environment variable).
         If a program name is given, it is added to the list of programs that is searched for.
         The program should be a relative or absolute path name to an executable.
    :type program: str or None
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :param format: If given, use this archive format instead of auto-detection.
    :type format: str or None
    :raise patoolib.PatoolError: If an archive does not exist or is not a regular file, or on errors while
         testing.
    :return: None
    :rtype: None
    """
    fileutil.check_existing_filename(archive)
    if verbosity >= 0:
        log.log_info(f"Testing {archive} ...")
    res = _handle_archive(
        archive,
        'test',
        verbosity=verbosity,
        interactive=interactive,
        program=program,
        password=password,
        format=format,
    )
    if verbosity >= 0:
        log.log_info("... tested ok.")
    return res


def create_archive(
    archive: str,
    filenames,
    verbosity: int = 0,
    program: str | None = None,
    interactive: bool = True,
    password: str | None = None,
    format: str | None = None,
) -> None:
    """Create given archive with given files.

    Example: patoolib.create_archive("/path/to/myfiles.zip", ("file1.txt", "dir/"))

    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param filenames: A list of filenames to add to the archive. Can be relative to the current
          working directory or absolute.
    :type filenames: tuple of str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param program: If None (the default), a list of suitable archive programs are checked if they
         exist in the system search path (defined by the PATH environment variable).
         If a program name is given, it is added to the list of programs that is searched for.
         The program should be a relative or absolute path name to an executable.
    :type program: str or None
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :param format: If given, use this archive format instead of auto-detection.
    :type format: str or None
    :raise patoolib.PatoolError: on errors while creating the archive
    :return: None
    :rtype: None
    """
    fileutil.check_new_filename(archive)
    fileutil.check_archive_filelist(filenames)
    if verbosity >= 0:
        log.log_info(f"Creating {archive} ...")
    res = _create_archive(
        archive,
        filenames,
        verbosity=verbosity,
        interactive=interactive,
        program=program,
        password=password,
        format=format,
    )
    if verbosity >= 0:
        log.log_info(f"... {archive} created.")
    return res


def diff_archives(
    archive1: str, archive2: str, verbosity: int = 0, interactive: bool = True
) -> int:
    """Compare two archives and print their differences.

    Both archives will be extracted in temporary directories. Both directory contents will be compared
    recursively with the diff(1) tool.

    Example: patoolib.diff_archives("release1.0.tar.gz", "release2.0.zip")

    :param archive1: The first archive filename. Can be relative to the current working directory or absolute.
    :type archive1: str
    :param archive2: The second archive filename. Can be relative to the current working directory or absolute.
    :type archive2: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :raise patoolib.PatoolError: on errors while comparing the archives.
    :return: None
    :rtype: None
    """
    fileutil.check_existing_filename(archive1)
    fileutil.check_existing_filename(archive2)
    if verbosity >= 0:
        log.log_info(f"Comparing {archive1} with {archive2} ...")
    res = _diff_archives(
        archive1, archive2, verbosity=verbosity, interactive=interactive
    )
    if res == 0 and verbosity >= 0:
        log.log_info("... no differences found.")
    return res


def search_archive(
    pattern: str,
    archive: str,
    verbosity: int = 0,
    interactive: bool = True,
    password: str | None = None,
) -> int:
    """Search pattern in archive members.

    The archive will be extracted in a temporary directory. The directory contents will then be searched
    with the grep(1) tool.

    Example: patoolib.search_archive("def urlopen", "python3.3.tar.gz")

    :param pattern: The pattern to search for. See the grep(1) manual page for pattern syntax.
    :type pattern: str
    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :raise patoolib.PatoolError: on errors while extracting or searching the archive
    :return: exit code of the grep program
    :rtype: int
    """
    if not pattern:
        raise util.PatoolError("empty search pattern")
    fileutil.check_existing_filename(archive)
    if verbosity >= 0:
        log.log_info(f"Searching {pattern!r} in {archive} ...")
    res = _search_archive(
        pattern,
        archive,
        verbosity=verbosity,
        interactive=interactive,
        password=password,
    )
    if res == 1 and verbosity >= 0:
        log.log_info(f"... {pattern!r} not found")
    return res


def repack_archive(
    archive: str,
    archive_new: str,
    verbosity: int = 0,
    interactive: bool = True,
    password: str | None = None,
) -> None:
    """Repack archive to different file and/or format.

    The archive will be extracted and recompressed to archive_new.

    Example: patoolib.repack_archive("linux-2.6.33.tar.gz", "linux-2.6.33.tar.bz2")

    :param archive: The archive filename. Can be relative to the current working directory or absolute.
    :type archive: str
    :param archive_new: The new archive filename. Can be relative to the current working directory or absolute.
    :type archive_new: str
    :param verbosity: larger values print more information. 0 is the default, -1 or lower means no output,
         values >= 1 prints command output
    :type verbosity: int
    :param interactive: If True (the default), wait for user input if the extraction program asks for it.
         This should be set to True if you intend to type in a password interactively.
         If set to False, standard input will be set to an empty string to prevent simple hangs from
         programs requiring input.
    :type interactive: bool
    :param password: If an archive is encrypted, set the given password with command line options.
         Note that the password might be written to logs that keep track of your command line
         history. If an archive program does not support passwords this option is ignored by patool.
    :type password: str or None
    :raise patoolib.PatoolError: on errors while extracting or creating the archive
    :return: None
    :rtype: None
    """
    fileutil.check_existing_filename(archive)
    fileutil.check_new_filename(archive_new)
    if verbosity >= 0:
        log.log_info(f"Repacking {archive} to {archive_new} ...")
    res = _repack_archive(
        archive,
        archive_new,
        verbosity=verbosity,
        interactive=interactive,
        password=password,
    )
    if verbosity >= 0:
        log.log_info("... repacking successful.")
    return res
