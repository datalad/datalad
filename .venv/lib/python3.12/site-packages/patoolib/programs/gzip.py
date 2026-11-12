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
"""Archive commands for the gzip program."""

from . import extract_singlefile_standard, test_singlefile_standard
from .. import util, fileutil, log
import os
import subprocess

test_gzip = test_compress = test_singlefile_standard


def extract_gzip(archive, compression, cmd, verbosity, interactive, outdir):
    """Extract given gzip archive."""
    cmdlist = [util.shell_quote(cmd)]
    if verbosity > 1:
        cmdlist.append('-v')
    outfile = get_original_filename(cmd, outdir, archive)
    cmdlist.extend(
        ['-c', '-d', '--', util.shell_quote(archive), '>', util.shell_quote(outfile)]
    )
    return (cmdlist, {'shell': True})


extract_compress = extract_singlefile_standard


def get_original_filename(cmd, outdir, archive):
    """Get the original filename inside a gzip archive.
    This parses the output of gzip --name --list.
    """
    outfile = fileutil.get_single_outfile(outdir, archive)
    cmdlist = [cmd, "--name", "--list", archive]
    try:
        output = util.backtick(cmdlist).strip()
        lines = output.splitlines()
        values = lines[1].split()
        baseoutfile = os.path.basename(outfile)
        basefilename = os.path.basename(values[-1])
        if os.path.normcase(baseoutfile) != os.path.normcase(basefilename):
            basearchive = os.path.basename(archive)
            # avoid overwriting the original archive with the same name
            if os.path.normcase(basefilename) != os.path.normcase(basearchive):
                outfile = os.path.join(outdir, basefilename)
    except (OSError, subprocess.CalledProcessError) as err:
        log.log_error(f"could not run {cmd}: {err}")
    return outfile


def create_gzip(archive, compression, cmd, verbosity, interactive, filenames):
    """Create a GZIP archive."""
    cmdlist = [util.shell_quote(cmd)]
    if verbosity > 1:
        cmdlist.append('-v')
    cmdlist.extend(['-c', '--'])
    cmdlist.extend([util.shell_quote(x) for x in filenames])
    cmdlist.extend(['>', util.shell_quote(archive)])
    return (cmdlist, {'shell': True})


def list_gzip(archive, compression, cmd, verbosity, interactive):
    """List a GZIP archive."""
    cmdlist = [cmd]
    if verbosity > 0:
        cmdlist.append('-v')
    cmdlist.extend(['-l', '--', archive])
    return cmdlist
