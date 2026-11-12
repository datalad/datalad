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
"""Archive commands for the lzma Python module."""

from .. import fileutil, util
import lzma

READ_SIZE_BYTES = 1024 * 1024

# Adapters for different lzma bindings.
if hasattr(lzma, 'FORMAT_ALONE'):

    def _get_lzma_options(format):
        return {
            'format': {
                'alone': lzma.FORMAT_ALONE,
                'xz': lzma.FORMAT_XZ,
            }[format]
        }
else:
    # might not be available e.g. in Debian's python-lzma 0.5.3
    # which is pyliblzma.
    def _get_lzma_options(format):
        return {'options': {'format': format}}


def _extract(archive, compression, cmd, format, verbosity, outdir):
    """Extract an LZMA or XZ archive with the lzma Python module."""
    targetname = fileutil.get_single_outfile(outdir, archive)
    try:
        with lzma.LZMAFile(archive, **_get_lzma_options(format)) as lzmafile:
            with open(targetname, 'wb') as targetfile:
                data = lzmafile.read(READ_SIZE_BYTES)
                while data:
                    targetfile.write(data)
                    data = lzmafile.read(READ_SIZE_BYTES)
    except Exception as err:
        msg = f"error extracting {archive} to {targetname}"
        raise util.PatoolError(msg) from err
    return


def extract_lzma(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract an LZMA archive with the lzma Python module."""
    return _extract(archive, compression, cmd, 'alone', verbosity, outdir)


def extract_xz(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract an XZ archive with the lzma Python module."""
    return _extract(archive, compression, cmd, 'xz', verbosity, outdir)


def _create(archive, compression, cmd, format, verbosity, filenames):
    """Create an LZMA or XZ archive with the lzma Python module."""
    if len(filenames) > 1:
        raise util.PatoolError('multi-file compression not supported in Python lzma')
    try:
        with lzma.LZMAFile(archive, mode='wb', **_get_lzma_options(format)) as lzmafile:
            filename = filenames[0]
            with open(filename, 'rb') as srcfile:
                data = srcfile.read(READ_SIZE_BYTES)
                while data:
                    lzmafile.write(data)
                    data = srcfile.read(READ_SIZE_BYTES)
    except Exception as err:
        raise util.PatoolError(f"error creating {archive}") from err
    return


def create_lzma(archive, compression, cmd, verbosity, interactive, filenames):
    """Create an LZMA archive with the lzma Python module."""
    return _create(archive, compression, cmd, 'alone', verbosity, filenames)


def create_xz(archive, compression, cmd, verbosity, interactive, filenames):
    """Create an XZ archive with the lzma Python module."""
    return _create(archive, compression, cmd, 'xz', verbosity, filenames)
