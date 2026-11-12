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
"""Archive commands for the jar program."""

import os


def extract_zip(
    archive, compression, cmd, verbosity, interactive, outdir, password=None
):
    """Extract a ZIP archive."""
    cmdlist = [cmd, '-x']
    if verbosity > 1:
        cmdlist.append('-v')
    cmdlist.extend(["-f", os.path.abspath(archive)])
    return (cmdlist, {'cwd': outdir})


def list_zip(archive, compression, cmd, verbosity, interactive, password=None):
    """List a ZIP archive."""
    cmdlist = [cmd, '-t']
    if verbosity > 1:
        cmdlist.append('-v')
    cmdlist.extend(["-f", archive])
    return cmdlist
