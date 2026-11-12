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
"""Archive commands for the GNU tar program."""

import functools
import os
import subprocess


def extract_tar(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract a TAR archive."""
    cmdlist = [cmd, '--extract']
    cmdlist.extend(get_tar_opts(cmd, compression, verbosity))
    cmdlist.extend(["--file", archive, '--directory', outdir])
    return cmdlist


def list_tar(archive, compression, cmd, verbosity, interactive):
    """List a TAR archive."""
    cmdlist = [cmd, '--list']
    cmdlist.extend(get_tar_opts(cmd, compression, verbosity))
    cmdlist.extend(["--file", archive])
    return cmdlist


test_tar = list_tar


def create_tar(archive, compression, cmd, verbosity, interactive, filenames):
    """Create a TAR archive."""
    cmdlist = [cmd, '--create']
    cmdlist.extend(get_tar_opts(cmd, compression, verbosity))
    cmdlist.extend(["--file", archive, '--'])
    cmdlist.extend(filenames)
    return cmdlist


@functools.cache
def get_tar_opts(cmd, compression, verbosity):
    """Get tar options for cmd according to the given compression and verbosity."""
    cmdlist = []
    progname = os.path.basename(cmd).lower()
    if progname.endswith('.exe'):
        progname = progname[:-4]
    if compression:
        cmdlist.append(f'--{compression}')
    if verbosity > 1:
        cmdlist.append('--verbose')
    if progname == 'tar':
        # Some tar implementations (ie. Windows tar.exe, and macos)
        # do not support --force-local
        testcmdlist = [cmd, "--force-local", "--help"]
        from .. import util  # noqa: PLC0415

        if util.run(testcmdlist, stderr=subprocess.DEVNULL, verbosity=-1) == 0:
            cmdlist.append('--force-local')
    return cmdlist
