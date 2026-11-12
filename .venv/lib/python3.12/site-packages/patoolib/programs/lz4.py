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
"""Archive commands for the lz4 program."""

from . import (
    extract_singlefile_standard,
    create_singlefile_standard,
    test_singlefile_standard,
)

extract_lz4 = extract_singlefile_standard
create_lz4 = create_singlefile_standard
test_lz4 = test_singlefile_standard


def list_lz4(archive, compression, cmd, verbosity, interactive):
    """List a LZ4 archive."""
    cmdlist = [cmd]
    cmdlist.append("--list")
    if verbosity > 1:
        cmdlist.append("--verbose")
    cmdlist.append("--")
    cmdlist.append(archive)
    return cmdlist
