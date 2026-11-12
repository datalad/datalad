#!/usr/bin/env python3
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
"""This is the main command line interface.
It will be made available as a script called "patool" on installation by setup.py.
The script will call the main_cli() function below on start.

Usage:
patool
   [global-options]
   {extract|list|create|repack|diff|search|formats}
   [sub-command-options]
   <command-args>
"""

import sys
import argparse
from . import (
    extract_archive,
    list_archive,
    test_archive,
    create_archive,
    diff_archives,
    search_archive,
    repack_archive,
    list_formats,
)
from .util import PatoolError
from .log import log_error, log_internal_error
from .configuration import App


def run_extract(args: argparse.Namespace) -> int:
    """Extract files from archive(s)."""
    res = 0
    for archive in args.archive:
        try:
            extract_archive(
                archive,
                verbosity=args.verbosity,
                interactive=args.interactive,
                outdir=args.outdir,
                password=args.password,
                format=args.format,
            )
        except PatoolError as msg:
            log_error(f"error extracting {archive}: {msg}")
            res += 1
    return res


def run_list(args: argparse.Namespace) -> int:
    """List files in archive(s)."""
    res = 0
    for archive in args.archive:
        try:
            verbosity = args.verbosity
            # increase default verbosity since the listing output should be visible
            if verbosity == 0:
                verbosity = 1
            list_archive(
                archive,
                verbosity=verbosity,
                interactive=args.interactive,
                password=args.password,
                format=args.format,
            )
        except PatoolError as msg:
            log_error(f"error listing {archive}: {msg}")
            res += 1
    return res


def run_test(args: argparse.Namespace) -> int:
    """Test files in archive(s)."""
    res = 0
    for archive in args.archive:
        try:
            test_archive(
                archive,
                verbosity=args.verbosity,
                interactive=args.interactive,
                password=args.password,
                format=args.format,
            )
        except PatoolError as msg:
            log_error(f"error testing {archive}: {msg}")
            res += 1
    return res


def run_create(args: argparse.Namespace) -> int:
    """Create an archive from given files."""
    res = 0
    try:
        create_archive(
            args.archive,
            args.filename,
            verbosity=args.verbosity,
            interactive=args.interactive,
            password=args.password,
            format=args.format,
        )
    except PatoolError as msg:
        log_error(f"error creating {args.archive}: {msg}")
        res = 1
    return res


def run_diff(args: argparse.Namespace) -> int:
    """Show differences between two archives."""
    try:
        res = diff_archives(
            args.archive1,
            args.archive2,
            verbosity=args.verbosity,
            interactive=args.interactive,
        )
    except PatoolError as msg:
        log_error(
            f"error showing differences between {args.archive1} and {args.archive2}: {msg}"
        )
        res = 2
    return res


def run_search(args: argparse.Namespace) -> int:
    """Search for pattern in given archive."""
    try:
        res = search_archive(
            args.pattern,
            args.archive,
            verbosity=args.verbosity,
            interactive=args.interactive,
            password=args.password,
        )
    except PatoolError as msg:
        log_error(f"error searching {args.archive}: {msg}")
        res = 2
    return res


def run_repack(args: argparse.Namespace) -> int:
    """Repackage one archive in another format."""
    res = 0
    try:
        repack_archive(
            args.archive_src,
            args.archive_dst,
            verbosity=args.verbosity,
            interactive=args.interactive,
        )
    except PatoolError as msg:
        log_error(f"error repacking {args.archive_src}: {msg}")
        res = 1
    return res


def run_formats(args: argparse.Namespace) -> int:
    """List supported and available archive formats."""
    list_formats()
    return 0


def run_version(args: argparse.Namespace) -> int:
    """Print version number."""
    print(App)
    return 0


Examples = """\
EXAMPLES
  patool extract archive.zip otherarchive.rar
  patool --verbose test dist.tar.gz
  patool list package.deb
  patool --verbose create myfiles.zip file1.txt dir/
  patool diff release1.0.tar.xz release2.0.zip
  patool search "def urlopen" python-3.3.tar.gz
  patool repack linux-2.6.33.tar.gz linux-2.6.33.tar.bz2
"""

Version = f"""\
VERSION
  {App}
"""


def create_argparser() -> argparse.ArgumentParser:
    """Construct and return an argument parser."""
    epilog = Examples + "\n" + Version
    parser = argparse.ArgumentParser(
        description="An archive file manager.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--verbose',
        '-v',
        action='count',
        default=0,
        dest='verbosity',
        help="verbose operation; can be given multiple times",
    )
    group.add_argument(
        '--quiet',
        '-q',
        action='count',
        default=0,
        dest='quiet',
        help="quiet operation; if given twice suppresses error output from archive commands",
    )
    parser.add_argument(
        '--non-interactive',
        dest='interactive',
        default=True,
        action='store_false',
        help="don't query for user input (i.e. passwords or when overwriting duplicate files); use with care since overwriting files or ignoring passwords could be unintended",
    )
    subparsers = parser.add_subparsers(
        help='the archive command; type "patool COMMAND -h" for command-specific help',
        dest='command',
        required=True,
    )
    # extract
    parser_extract = subparsers.add_parser(
        'extract', help='extract one or more archives'
    )
    parser_extract.add_argument('--outdir', help="output directory to extract to")
    parser_extract.add_argument('--password', help="password for encrypted files")
    parser_extract.add_argument(
        '--format',
        help="archive format (e.g., 7z, tar, rar) - auto detected if not provided",
    )
    parser_extract.add_argument('archive', nargs='+', help="an archive file")
    # list
    parser_list = subparsers.add_parser(
        'list', help='list members or one or more archives'
    )
    parser_list.add_argument('--password', help="password for encrypted files")
    parser_list.add_argument(
        '--format',
        help="archive format (e.g., 7z, tar, rar) - auto detected if not provided",
    )
    parser_list.add_argument('archive', nargs='+', help="an archive file")
    # create
    parser_create = subparsers.add_parser('create', help='create an archive')
    parser_create.add_argument('--password', help="password to encrypt files")
    parser_create.add_argument(
        '--format',
        help="archive format (e.g., 7z, tar, rar) - auto detected if not provided",
    )
    parser_create.add_argument(
        'archive',
        help="the archive file; the file extension determines the archive program",
    )
    parser_create.add_argument(
        'filename',
        nargs='+',
        help="a file or directory to add to the archive; note that some archive programs do not support directories",
    )
    # test
    parser_test = subparsers.add_parser('test', help='test an archive')
    parser_test.add_argument('--password', help="password for encrypted files")
    parser_test.add_argument(
        '--format',
        help="archive format (e.g., 7z, tar, rar) - auto detected if not provided",
    )
    parser_test.add_argument('archive', nargs='+', help='an archive file')
    # repack
    parser_repack = subparsers.add_parser(
        'repack', help='repack an archive to a different format'
    )
    parser_repack.add_argument('archive_src', help='source archive file')
    parser_repack.add_argument('archive_dst', help='target archive file')
    # diff
    parser_diff = subparsers.add_parser(
        'diff', help='show differences between two archives'
    )
    parser_diff.add_argument('archive1', help='the first archive file')
    parser_diff.add_argument('archive2', help='the second archive file')
    # search
    parser_search = subparsers.add_parser(
        'search', help="search contents of archive members"
    )
    parser_search.add_argument('--password', help="password for encrypted files")
    parser_search.add_argument('pattern', help='the grep(1) compatible search pattern')
    parser_search.add_argument('archive', help='the archive file')
    # formats
    subparsers.add_parser('formats', help="show supported archive formats")
    # version
    subparsers.add_parser('version', help="print version information")
    # optional bash completion
    try:
        import argcomplete  # noqa: PLC0415

        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    return parser


def main(args=None) -> int:
    """Parse options and execute commands."""
    res = 0
    try:
        argparser = create_argparser()
        pargs = argparser.parse_args(args=args)
        if pargs.quiet:
            pargs.verbosity = -pargs.quiet
        # run subcommand function
        res = globals()[f"run_{pargs.command}"](pargs)
    except KeyboardInterrupt:
        log_error("aborted")
        res = 1
    except Exception as exc:
        log_internal_error(exc)
        res = 2
    return res


def main_cli():
    """Run main() function."""
    sys.exit(main())
