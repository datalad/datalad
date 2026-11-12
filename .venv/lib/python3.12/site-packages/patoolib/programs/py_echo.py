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
"""Archive commands printing resulting filenames for single-file
compressed archives, implemented by the Python print function.
"""

from .. import fileutil


def list_bzip2(archive, compression, cmd, verbosity, interactive):
    """List a BZIP2 archive."""
    return stripext(cmd, archive, verbosity)


list_compress = list_lzma = list_xz = list_lzip = list_lrzip = list_rzip = list_bzip2


def list_ape(archive, compression, cmd, verbosity, interactive):
    """List an APE archive."""
    return stripext(cmd, archive, verbosity, extension=".wav")


list_shn = list_flac = list_ape


def stripext(cmd, archive, verbosity, extension=""):
    """Print the name without suffix."""
    if verbosity >= 0:
        print(fileutil.stripext(archive) + extension)
    return
