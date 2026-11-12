# Copyright (C) 2011-2023 Bastian Kleineidam
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
"""Archive commands for the xdms program."""

from .. import util


def _maybe_add_password(cmdlist, password):
    if password:
        cmdlist.extend(['-p', password])


def extract_dms(
    archive, compression, cmd, verbosity, interactive, outdir, password=None
):
    """Extract a DMS archive."""
    check_archive_ext(archive)
    cmdlist = [cmd, '-d', outdir]
    if verbosity > 1:
        cmdlist.append('-v')
    _maybe_add_password(cmdlist, password)
    cmdlist.extend(['u', archive])
    return cmdlist


def list_dms(archive, compression, cmd, verbosity, interactive, password=None):
    """List a DMS archive."""
    check_archive_ext(archive)
    cmdlist = [cmd, 'v']
    _maybe_add_password(cmdlist, password)
    cmdlist.append(archive)
    return cmdlist


def test_dms(archive, compression, cmd, verbosity, interactive, password=None):
    """Test a DMS archive."""
    check_archive_ext(archive)
    cmdlist = [cmd, 't']
    _maybe_add_password(cmdlist, password)
    cmdlist.append(archive)
    return cmdlist


def check_archive_ext(archive):
    """xdms(1) cannot handle files with extensions other than '.dms'."""
    if not archive.lower().endswith(".dms"):
        rest = archive[-4:]
        msg = f"xdms(1) archive file must end with `.dms', not `{rest}'"
        raise util.PatoolError(msg)
