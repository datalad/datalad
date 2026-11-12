# Copyright (C) 2016-2023 Bastian Kleineidam
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
"""Archive commands for the 7zr program.

7zr is a light executable supporting only the 7z archive format.
"""

# ruff: noqa: F401
from .p7zip import create_7z


def extract_7z(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract a 7z archive."""
    cmdlist = [cmd, 'x']
    if not interactive:
        cmdlist.append('-y')
    cmdlist.extend([f'-o{outdir}', '--', archive])
    return cmdlist


def list_7z(archive, compression, cmd, verbosity, interactive):
    """List a 7z archive."""
    cmdlist = [cmd, 'l']
    if not interactive:
        cmdlist.append('-y')
    cmdlist.extend(['--', archive])
    return cmdlist


def test_7z(archive, compression, cmd, verbosity, interactive):
    """Test a 7z archive."""
    cmdlist = [cmd, 't']
    if not interactive:
        cmdlist.append('-y')
    cmdlist.extend(['--', archive])
    return cmdlist
