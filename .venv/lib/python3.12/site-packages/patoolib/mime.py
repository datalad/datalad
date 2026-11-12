# Copyright (C) 2010-2024 Bastian Kleineidam
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
"""MIME type detection functions."""

import functools
import os
import mimetypes
import subprocess
from collections.abc import Sequence
from . import ArchiveMimetypes, ArchiveCompressions
from .log import log_error, log_warning, log_info
from .util import find_program, backtick


# internal MIME database
mimedb: mimetypes.MimeTypes | None = None


def init_mimedb() -> None:
    """Initialize the internal MIME database."""
    global mimedb  # noqa PLW0603
    try:
        mimedb = mimetypes.MimeTypes(strict=False)
    except Exception as msg:
        log_error(f"could not initialize MIME database: {msg}")
        return
    add_mimedb_data(mimedb)


def add_mimedb_data(mimedb: mimetypes.MimeTypes) -> None:
    """Add missing encodings and mimetypes to MIME database."""
    mimedb.encodings_map['.bz2'] = 'bzip2'
    mimedb.encodings_map['.lzma'] = 'lzma'
    mimedb.encodings_map['.xz'] = 'xz'
    mimedb.encodings_map['.lz'] = 'lzip'
    mimedb.encodings_map[".zst"] = "zstd"
    mimedb.suffix_map['.tbz2'] = '.tar.bz2'
    add_mimetype(mimedb, 'application/x-lzop', '.lzo')
    add_mimetype(mimedb, 'application/x-adf', '.adf')
    add_mimetype(mimedb, 'application/x-arj', '.arj')
    add_mimetype(mimedb, 'application/x-bzip3', '.bz3')
    add_mimetype(mimedb, 'application/x-lzma', '.lzma')
    add_mimetype(mimedb, 'application/x-xz', '.xz')
    add_mimetype(mimedb, 'application/java-archive', '.jar')
    add_mimetype(mimedb, 'application/vnd.rar', '.rar')
    add_mimetype(mimedb, 'application/vnd.rar', '.cbr')
    add_mimetype(mimedb, 'application/x-7z-compressed', '.7z')
    add_mimetype(mimedb, 'application/x-7z-compressed', '.cb7')
    add_mimetype(mimedb, 'application/x-cab', '.cab')
    add_mimetype(mimedb, 'application/x-rpm', '.rpm')
    add_mimetype(mimedb, 'application/x-debian-package', '.deb')
    add_mimetype(mimedb, 'application/x-ace', '.ace')
    add_mimetype(mimedb, 'application/x-ace', '.cba')
    add_mimetype(mimedb, 'application/x-archive', '.a')
    add_mimetype(mimedb, 'application/x-alzip', '.alz')
    add_mimetype(mimedb, 'application/x-arc', '.arc')
    # note: application/x-freearc is not added to mimedb since it uses the same file extension .arc as application/x-arc
    add_mimetype(mimedb, 'application/x-lrzip', '.lrz')
    add_mimetype(mimedb, 'application/x-lha', '.lha')
    add_mimetype(mimedb, 'application/x-lzh', '.lzh')
    add_mimetype(mimedb, 'application/x-lz4', '.lz4')
    add_mimetype(mimedb, 'application/x-rzip', '.rz')
    add_mimetype(mimedb, 'application/x-zoo', '.zoo')
    add_mimetype(mimedb, 'application/x-dms', '.dms')
    add_mimetype(mimedb, 'application/x-ms-wim', '.wim')
    add_mimetype(mimedb, 'application/x-zip-compressed', '.crx')
    add_mimetype(mimedb, 'application/x-shar', '.shar')
    add_mimetype(mimedb, 'application/x-tar', '.cbt')
    add_mimetype(mimedb, 'application/x-vhd', '.vhd')
    add_mimetype(mimedb, 'audio/x-ape', '.ape')
    add_mimetype(mimedb, 'audio/x-shn', '.shn')
    add_mimetype(mimedb, 'audio/flac', '.flac')
    add_mimetype(mimedb, 'application/x-chm', '.chm')
    add_mimetype(mimedb, 'application/x-iso9660-image', '.iso')
    add_mimetype(mimedb, 'application/zip', '.cbz')
    add_mimetype(mimedb, 'application/zip', '.epub')
    add_mimetype(mimedb, 'application/zip', '.apk')
    add_mimetype(mimedb, 'application/zpaq', '.zpaq')
    add_mimetype(mimedb, "application/zstd", ".zst")


def add_mimetype(mimedb: mimetypes.MimeTypes, mimetype: str, extension: str) -> None:
    """Add or replace a mimetype to be used with the given extension."""
    # If extension is already a common type, strict=True must be used.
    strict = extension in mimedb.types_map[True]
    mimedb.add_type(
        mimetype, extension, strict=strict
    )  # pytype: disable=attribute-error


@functools.cache
def guess_mime(filename: str) -> tuple[str | None, str | None]:
    """Guess the MIME type of given filename using file(1) and if that
    fails by looking at the filename extension with the Python mimetypes
    module.

    The result of this function is cached.
    """
    mime, encoding = guess_mime_file(filename)
    if mime is None:
        # fall back to guessing archive type by file extension
        mime, encoding = guess_mime_mimedb(filename)
    else:
        # check if file extension detection differs.
        mime2, _encoding2 = guess_mime_mimedb(filename)
        if mime2 != mime:
            log_info(
                f"Different MIME types detected for {filename}: "
                f"{mime} by file(1), {mime2} by extension. Preferring {mime}."
            )
    assert mime is not None or encoding is None
    return mime, encoding


Encoding2Mime: dict[str, str] = {
    'gzip': "application/gzip",
    'bzip2': "application/x-bzip2",
    'compress': "application/x-compress",
    'lzma': "application/x-lzma",
    'lzip': "application/x-lzip",
    'xz': "application/x-xz",
    "zstd": "application/zstd",
}
Mime2Encoding: dict[str, str] = dict(
    [(_val, _key) for _key, _val in Encoding2Mime.items()]
)

LegacyMimeType: dict[str, str] = {
    # libmagic before version 5.14 identified .gz files as application/x-gzip
    'application/x-gzip': "application/gzip",
    # libmagic before version 5.46 identified .rar files as application/x-rar
    'application/x-rar': "application/vnd.rar",
}


def guess_mime_mimedb(filename: str) -> tuple[str | None, str | None]:
    """Guess MIME type from given filename.
    @return: tuple (mime, encoding)
    """
    mime, encoding = None, None
    if mimedb is not None:
        mime, encoding = mimedb.guess_type(filename, strict=False)
    if mimedb is not None and mime is None and encoding is None:
        # try with lowercase extension, since we configure our mimedb entries only with lowercase
        # this way, files like "t.GZ" are recognized
        root, ext = os.path.splitext(filename)
        mime, encoding = mimedb.guess_type(root + ext.lower(), strict=False)
    if mime not in ArchiveMimetypes and encoding in ArchiveCompressions:
        # Files like 't.txt.gz' are recognized with encoding as format, and
        # an unsupported mime-type like 'text/plain'. Fix this.
        mime = Encoding2Mime[encoding]
        encoding = None
    return mime, encoding


def guess_mime_file(filename: str) -> tuple[str | None, str | None]:
    """Determine MIME type of filename with file(1):
     (a) using `file --brief --mime-type`
     (b) using `file --brief` and look at the result string
     (c) detect compressed archives (eg. .tar.gz) using
         `file --brief --mime --uncompress --no-sandbox`
    @return: tuple (mime, encoding)
    """
    mime, encoding = None, None
    if os.path.isfile(filename):
        file_prog = find_program("file")
        if file_prog is not None:
            mime, encoding = guess_mime_file_mime(file_prog, filename)
            if mime is None:
                mime = guess_mime_file_text(file_prog, filename)
                encoding = None
        else:
            log_info(
                "could not find a 'file' executable, falling back to guess mime type by file extension"
            )
    if mime in Mime2Encoding:
        # try to look inside compressed archives
        mime2 = None
        if file_prog is not None:
            cmd = [
                file_prog,
                "--brief",
                "--mime",
                "--uncompress",
                "--no-sandbox",
                filename,
            ]
            try:
                outparts = backtick(cmd).strip().split(";")
                mime2 = outparts[0].split(" ", 1)[0]
            except (OSError, subprocess.CalledProcessError) as err:
                log_warning(f"error executing {cmd}: {err}")

        if mime2 in LegacyMimeType:
            mime2 = LegacyMimeType[mime2]

        # Some file(1) implementations return an empty or unknown mime type
        # when the uncompressor program is not installed, other
        # implementation return the original file type.
        # The following detects both cases.
        if (
            mime2 in ('application/x-empty', 'application/octet-stream')
            or mime2 in Mime2Encoding
            or not mime2
        ):
            # The uncompressor program file(1) uses is not installed
            # or is not able to uncompress.
            # Try to get mime information from the file extension.
            mime2, encoding2 = guess_mime_mimedb(filename)
            if mime2 in ArchiveMimetypes:
                mime = mime2
                encoding = encoding2
        elif mime2 in ArchiveMimetypes:
            mime = mime2
            encoding = get_file_mime_encoding(outparts)
    return mime, encoding


def guess_mime_file_mime(
    file_prog: str, filename: str
) -> tuple[str | None, str | None]:
    """Determine MIME type of filename with file(1) and --mime option.
    @return: tuple (mime, encoding)
    """
    mime, encoding = None, None
    cmd = [file_prog, "--brief", "--mime-type", filename]
    try:
        mime = backtick(cmd).strip()
    except OSError as err:
        # ignore errors, as file(1) is only a fallback
        log_warning(f"error executing {cmd}: {err}")

    if mime in LegacyMimeType:
        mime = LegacyMimeType[mime]

    if mime not in ArchiveMimetypes:
        mime, encoding = None, None
    return mime, encoding


def get_file_mime_encoding(parts: Sequence[str]) -> str | None:
    """Get encoding value from splitted output of file --mime --uncompress."""
    for part in parts:
        for subpart in part.split(" "):
            if subpart.startswith("compressed-encoding="):
                mime = subpart.split("=")[1].strip()
                return Mime2Encoding.get(mime)
    return None


# Match file(1) output text to mime types
FileText2Mime: dict[str, str] = {
    "7-zip archive data": "application/x-7z-compressed",
    "ACE archive data": "application/x-ace",
    "ALZ archive data": "application/x-alzip",
    "Amiga DOS disk": "application/x-adf",
    "ARJ archive data": "application/x-arj",
    "bzip2 compressed data": "application/x-bzip2",
    "bzip3 compressed data": "application/x-bzip3",
    "cpio archive": "application/x-cpio",
    "ASCII cpio archive": "application/x-cpio",
    "Debian binary package": "application/x-debian-package",
    "FreeArc archive": "application/x-freearc",
    "gzip compressed data": "application/gzip",
    "LZMA compressed data": "application/x-lzma",
    "LRZIP compressed data": "application/x-lrzip",
    "lzop compressed data": "application/x-lzop",
    "Microsoft Cabinet archive data": "application/vnd.ms-cab-compressed",
    "RAR archive data": "application/vnd.rar",
    "RPM ": "application/x-rpm",
    "POSIX tar archive": "application/x-tar",
    "xz compressed data": "application/x-xz",
    "Zip archive data": "application/zip",
    "compress'd data": "application/x-compress",
    "lzip compressed data": "application/x-lzip",
    "rzip compressed data": "application/x-rzip",
    "current ar archive": "application/x-archive",
    "LHa ": "application/x-lha",
    "ARC archive data": "application/x-arc",
    "Zoo archive data": "application/x-zoo",
    "DMS archive data": "application/x-dms",
    "Monkey's Audio": "audio/x-ape",
    "FLAC audio bitstream data": "audio/flac",
    "MS Windows HtmlHelp Data": "application/x-chm",
    "ZPAQ stream": "application/zpaq",
}


def guess_mime_file_text(file_prog: str, filename: str) -> str | None:
    """Determine MIME type of filename with file(1)."""
    cmd = [file_prog, "--brief", filename]
    try:
        output = backtick(cmd).strip()
    except OSError as err:
        # ignore errors, as file(1) is only a fallback
        log_warning(f"error executing {cmd}: {err}")
        return None
    # match output against known strings
    for matcher, mime in FileText2Mime.items():
        if output.startswith(matcher) and mime in ArchiveMimetypes:
            return mime
    return None


init_mimedb()
