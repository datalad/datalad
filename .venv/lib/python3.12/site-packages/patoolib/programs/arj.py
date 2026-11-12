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
"""Archive commands for the arj program."""

from ..util import PatoolError


def _get_password_switch(password):
    """Check password and return password switch for ARJ."""
    if ' ' in password:
        raise PatoolError("Password for ARJ can't contain spaces.")
    return f'-g{password}'


def _maybe_add_password(cmdlist, password):
    if password:
        cmdlist.append(_get_password_switch(password))


def extract_arj(
    archive, compression, cmd, verbosity, interactive, outdir, password=None
):
    """Extract an ARJ archive."""
    cmdlist = [cmd, 'x', '-r']
    _maybe_add_password(cmdlist, password)
    if not interactive:
        cmdlist.append('-y')
    cmdlist.extend([archive, outdir])
    return cmdlist


def list_arj(archive, compression, cmd, verbosity, interactive, password=None):
    """List an ARJ archive."""
    cmdlist = [cmd]
    _maybe_add_password(cmdlist, password)
    if verbosity > 1:
        cmdlist.append('v')
    else:
        cmdlist.append('l')
    if not interactive:
        cmdlist.append('-y')
    cmdlist.extend(['-r', archive])
    return cmdlist


def test_arj(archive, compression, cmd, verbosity, interactive, password=None):
    """Test an ARJ archive."""
    cmdlist = [cmd, 't', '-r']
    _maybe_add_password(cmdlist, password)
    if not interactive:
        cmdlist.append('-y')
    cmdlist.append(archive)
    return cmdlist


def create_arj(
    archive, compression, cmd, verbosity, interactive, filenames, password=None
):
    """Create an ARJ archive."""
    cmdlist = [cmd, 'a', '-r']
    _maybe_add_password(cmdlist, password)
    if not interactive:
        cmdlist.append('-y')
    cmdlist.append(archive)
    cmdlist.extend(filenames)
    return cmdlist
