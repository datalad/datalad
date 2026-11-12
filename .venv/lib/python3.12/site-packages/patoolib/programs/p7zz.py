# Copyright (C) 2024 Bastian Kleineidam
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
"""Archive commands for the 7zz program.
The 7zz program is included in the Linux-specific distribution of the 7-Zip
package.
"""

# All 7zz options that patool is using are compatible with the p7zip package,
# an alternative implementation for Linux of the 7z archive format.
# Therefore we import functions from the p7zip.py package.
from .p7zip import extract_7z, extract_7z_singlefile

extract_bzip2 = extract_gzip = extract_compress = extract_xz = extract_lzma = (
    extract_7z_singlefile
)

extract_zip = extract_rar = extract_cab = extract_chm = extract_arj = extract_cpio = (
    extract_rpm
) = extract_deb = extract_iso = extract_udf = extract_vhd = extract_wim = extract_7z

from .p7zip import list_7z

list_bzip2 = list_gzip = list_zip = list_compress = list_rar = list_cab = list_chm = (
    list_arj
) = list_cpio = list_rpm = list_deb = list_iso = list_xz = list_lzma = list_udf = (
    list_vhd
) = list_wim = list_7z

from .p7zip import test_7z

test_bzip2 = test_gzip = test_zip = test_compress = test_rar = test_cab = test_chm = (
    test_arj
) = test_cpio = test_rpm = test_deb = test_iso = test_xz = test_lzma = test_udf = (
    test_vhd
) = test_wim = test_7z

# ruff: noqa: F401
from .p7zip import (
    create_7z,
    create_zip,
    create_xz,
    create_gzip,
    create_bzip2,
    create_wim,
)
