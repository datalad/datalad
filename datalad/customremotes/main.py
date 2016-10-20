# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""""""

__docformat__ = 'restructuredtext'


import argparse
import os

from .. import __doc__ as m__doc__, __version__ as m__version__
from ..log import lgr

from ..cmdline import helpers
from ..cmdline.main import _license_info

from ..utils import setup_exceptionhook
from ..ui import ui

backends = ['archive']


def setup_parser(backend):

    suffix, desc = {
        'datalad': (
            '',
            "download content from various URLs (http{,s}, s3, etc) possibly "
            "requiring authentication or custom access mechanisms using "
            "DataLad's downloaders"),
        'archive': (
            '-archive',
            "extract content from archives (.tar{,.gz}, .zip, etc) which are "
            "in turn managed by git-annex.  See `datalad add-archive-content` "
            "command")
    }[backend]
    # setup cmdline args parser
    # main parser
    # TODO: should be encapsulated for resharing with the main datalad's
    parser = argparse.ArgumentParser(
        fromfile_prefix_chars='@',
        # usage="%(prog)s ...",
        description="%s\n\n" % m__doc__ +
                    "git-annex-remote-datalad%s is a git-annex custom special remote to %s" % (suffix, desc),
        epilog='"DataLad\'s git-annex very special remote"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    # common options
    helpers.parser_add_common_opt(parser, 'help')
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(
        parser,
        'version',
        version='datalad %s\n\n%s' % (m__version__, _license_info()))
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="Catch exceptions and fall into debugger upon exception")

    parser.add_argument(
        "command", nargs="?",
        help="Command to run. TODO: list per each custom remote"
    )
    return parser


def _main(args, backend=None):
    """Unprotected portion"""
    # TODO: For now we have only one, but we might need to actually become aware
    # of multiple and provide multiple helpers/symlinks
    # OR consider implementing ultimate handler of all dl+ URLs within a
    # single beast -- probably wouldn't fly since we do might need different
    # initializations etc.
    assert(backend is not None)
    if backend == 'archive':
        from .archives import ArchiveAnnexCustomRemote
        remote = ArchiveAnnexCustomRemote()
    elif backend == 'datalad':
        from .datalad import DataladAnnexCustomRemote
        remote = DataladAnnexCustomRemote()
    else:
        raise ValueError("I don't know anything about %r backend. "
                         "Known are: %s" % backends)

    # TODO: handle args -- not used ATM
    # Generic commands to support:
    #   get-uri-prefix
    #   get-uri [options] with [options] being backend specific
    #           e.g. for archive --key KEY(archive) --file FILE
    command = args.command
    if command == 'get-uri-prefix':
        print(remote.url_prefix)
    elif args.command is None:
        # If no command - run the special remote
        if 'DATALAD_TESTS_USECASSETTE' in os.environ:
            # optionally feeding it a cassette, used by tests
            from ..support.vcr_ import use_cassette
            with use_cassette(os.environ['DATALAD_TESTS_USECASSETTE']):
                remote.main()
        else:
            remote.main()
    else:
        raise ValueError("Unknown command %s" % command)


def main(args=None, backend=None):
    import sys
    # TODO: redirect lgr output to stderr if it is stdout and not "forced"
    # by env variable...
    #
    parser = setup_parser(backend=backend)
    # parse cmd args
    args = parser.parse_args(args)

    ui.set_backend('annex')  # stdin/stdout will be used for interactions with annex

    if args.common_debug:
        # So we could see/stop clearly at the point of failure
        setup_exceptionhook()
        _main(args, backend)
    else:
        # Otherwise - guard and only log the summary. Postmortem is not
        # as convenient if being caught in this ultimate except
        try:
            _main(args, backend)
        except Exception as exc:
            lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
            sys.exit(1)
