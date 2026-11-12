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
"""Archive commands for the arc program."""

import os
from ..util import PatoolError


def _add_password_to_options(options, password):
    """Check password and add it to ARC options."""
    if password is None:
        return options
    if ' ' in password:
        raise PatoolError("Password for ARC can't contain spaces.")
    options += f'g{password}'
    return options


def extract_arc(
    archive, compression, cmd, verbosity, interactive, outdir, password=None
):
    """Extract a ARC archive."""
    # Since extracted files will be placed in the current directory,
    # the cwd argument has to be the output directory.
    options = _add_password_to_options('x', password)
    cmdlist = [cmd, options, os.path.abspath(archive)]
    return (cmdlist, {'cwd': outdir})


def list_arc(archive, compression, cmd, verbosity, interactive, password=None):
    """List a ARC archive."""
    cmdlist = [cmd]
    if verbosity > 1:
        cmdlist.append(_add_password_to_options('v', password))
    else:
        cmdlist.append(_add_password_to_options('l', password))
    cmdlist.append(archive)
    return cmdlist


def test_arc(archive, compression, cmd, verbosity, interactive, password=None):
    """Test a ARC archive."""
    return [cmd, _add_password_to_options('t', password), archive]


def create_arc(
    archive, compression, cmd, verbosity, interactive, filenames, password=None
):
    """Create a ARC archive."""
    cmdlist = [cmd, _add_password_to_options('a', password), archive]
    cmdlist.extend(filenames)
    return cmdlist


extract_freearc = extract_arc
list_freearc = list_arc
test_freearc = test_arc
create_freearc = create_arc
