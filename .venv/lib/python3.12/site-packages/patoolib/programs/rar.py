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
"""Archive commands for the rar program."""

import os


def extract_rar(
    archive, compression, cmd, verbosity, interactive, outdir, password=None
):
    """Extract a RAR archive."""
    cmdlist = [cmd, 'x']
    if not interactive:
        cmdlist.extend(['-p-', '-y'])
    if password:
        cmdlist.append(f'-p{password}')
    cmdlist.extend(['-kb', '-or', '--', os.path.abspath(archive)])
    return (cmdlist, {'cwd': outdir})


def list_rar(archive, compression, cmd, verbosity, interactive, password=None):
    """List a RAR archive."""
    cmdlist = [cmd]
    if verbosity > 1:
        cmdlist.append('v')
    else:
        cmdlist.append('l')
    if not interactive:
        cmdlist.extend(['-p-', '-y'])
    if password:
        cmdlist.append(f'-p{password}')
    cmdlist.extend(['--', archive])
    return cmdlist


def test_rar(archive, compression, cmd, verbosity, interactive, password=None):
    """Test a RAR archive."""
    cmdlist = [cmd, 't']
    if not interactive:
        cmdlist.extend(['-p-', '-y'])
    if password:
        cmdlist.append(f'-p{password}')
    cmdlist.extend(['--', archive])
    return cmdlist


def create_rar(
    archive, compression, cmd, verbosity, interactive, filenames, password=None
):
    """Create a RAR archive."""
    cmdlist = [cmd, 'a']
    if not interactive:
        cmdlist.append('-y')
    if password:
        cmdlist.append(f'-p{password}')
    cmdlist.extend(['-r', '-m5', '--', archive])
    cmdlist.extend(filenames)
    return cmdlist
