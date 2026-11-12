# Copyright (C) 2023 Bastian Kleineidam
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
"""Archive commands for the unar program."""


def _extract(archive, compression, cmd, verbosity, interactive, outdir, password=None):
    """Extract an archive."""
    cmdlist = [cmd, '-o', outdir]
    if password:
        cmdlist.extend(['-p', password])
    cmdlist.append(archive)
    return cmdlist


extract_rar = _extract
extract_zip = _extract
extract_7z = _extract
extract_tar = _extract
extract_gzip = _extract
extract_bzip2 = _extract
extract_lzma = _extract
extract_xz = _extract
extract_cab = _extract
extract_iso = _extract
extract_cpio = _extract
extract_compress = _extract
extract_zoo = _extract
extract_lzh = _extract
extract_dms = _extract
