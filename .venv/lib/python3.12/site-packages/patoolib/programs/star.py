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
"""Archive commands for the star program."""

import functools


def extract_tar(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract a TAR archive."""
    cmdlist = [cmd, '-x']
    cmdlist.extend(get_star_opts(cmd, compression, verbosity))
    cmdlist.extend(['-C', outdir, f"file={archive}"])
    return cmdlist


def list_tar(archive, compression, cmd, verbosity, interactive):
    """List a TAR archive."""
    cmdlist = [cmd, '-n']
    cmdlist.extend(get_star_opts(cmd, compression, verbosity))
    cmdlist.append(f"file={archive}")
    return cmdlist


test_tar = list_tar


def create_tar(archive, compression, cmd, verbosity, interactive, filenames):
    """Create a TAR archive."""
    cmdlist = [cmd, '-c']
    cmdlist.extend(get_star_opts(cmd, compression, verbosity))
    cmdlist.append(f"file={archive}")
    cmdlist.extend(filenames)
    return cmdlist


@functools.cache
def get_star_opts(cmd, compression, verbosity):
    """Add tar options to cmdlist."""
    cmdlist = []
    if compression == 'gzip':
        cmdlist.append('-z')
    elif compression == 'compress':
        cmdlist.append('-Z')
    elif compression == 'bzip2':
        cmdlist.append('-j')
    elif compression in ('lzma', 'xz', 'lzip'):
        # use the compression name as program name since
        # tar is picky which programs it can use
        program = compression
        # set compression program
        cmdlist.extend(['compress-program=', program])
    if verbosity > 1:
        cmdlist.append('-v')
    return cmdlist
