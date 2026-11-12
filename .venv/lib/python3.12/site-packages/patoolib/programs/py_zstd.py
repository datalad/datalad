# Copyright (C) 2012-2023 Bastian Kleineidam
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
"""Archive commands for the lzma Python module.
Raises ImportError when neither compression.zstd nor pyzst module is found.
"""

from .. import fileutil, util, log

# try importing a python zstd module
try:
    from compression import zstd
except ImportError:
    import pyzstd as zstd  # ty: ignore[unresolved-import]

READ_SIZE_BYTES = 1024 * 1024


def extract_zstd(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract a ZSTD archive with the zstd Python module."""
    targetname = fileutil.get_single_outfile(outdir, archive)
    try:
        with zstd.ZstdFile(archive) as zstdfile:
            with open(targetname, 'wb') as targetfile:
                if verbosity >= 1:
                    log.log_info(f"extracting ZstdFile({archive}) to {targetname}")
                data = zstdfile.read(READ_SIZE_BYTES)
                while data:
                    targetfile.write(data)
                    data = zstdfile.read(READ_SIZE_BYTES)
    except Exception as err:
        msg = f"error extracting {archive} to {targetname}"
        raise util.PatoolError(msg) from err
    return


def create_zstd(archive, compression, cmd, verbosity, interactive, filenames):
    """Create a ZSTD archive with the zstd Python module."""
    if len(filenames) > 1:
        raise util.PatoolError('multi-file compression not supported in Python zstd')
    try:
        with zstd.ZstdFile(archive, mode='wb') as zstdfile:
            filename = filenames[0]
            with open(filename, 'rb') as srcfile:
                if verbosity >= 1:
                    log.log_info("compressing {filename} to ZstdFile({archive})")
                data = srcfile.read(READ_SIZE_BYTES)
                while data:
                    zstdfile.write(data)
                    data = srcfile.read(READ_SIZE_BYTES)
    except Exception as err:
        raise util.PatoolError(f"error creating {archive}") from err
    return
