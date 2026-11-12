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
"""Archive commands for the tarfile Python module."""

from .. import util
import tarfile


def list_tar(archive, compression, cmd, verbosity, interactive):
    """List a TAR archive with the tarfile Python module."""
    try:
        with tarfile.open(archive) as tfile:
            tfile.list(verbose=verbosity > 1)
    except Exception as err:
        raise util.PatoolError(f"error listing {archive}") from err
    return


test_tar = list_tar


def extract_tar(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract a TAR archive with the tarfile Python module."""
    try:
        with tarfile.open(archive) as tfile:
            tfile.extractall(path=outdir, filter='data')
    except Exception as err:
        raise util.PatoolError(f"error extracting {archive}") from err
    return


def create_tar(archive, compression, cmd, verbosity, interactive, filenames):
    """Create a TAR archive with the tarfile Python module."""
    mode = get_tar_mode(compression)
    try:
        with tarfile.open(archive, mode) as tfile:
            for filename in filenames:
                tfile.add(filename)
    except Exception as err:
        raise util.PatoolError(f"error creating {archive}") from err
    return


def get_tar_mode(compression):
    """Determine tarfile open mode according to the given compression."""
    if compression == 'gzip':
        return 'w:gz'
    if compression == 'bzip2':
        return 'w:bz2'
    if compression in ('lzma', 'xz'):
        return 'w:xz'
    if compression:
        msg = f'pytarfile does not support {compression} for tar compression'
        raise util.PatoolError(msg)
    # no compression
    return 'w'
