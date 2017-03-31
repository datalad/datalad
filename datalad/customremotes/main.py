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
from ..dochelpers import exc_str

BACKENDS = {
        'datalad': (
            '',
            'datalad.DataladAnnexCustomRemote',
            "download content from various URLs (http{,s}, s3, etc) possibly "
            "requiring authentication or custom access mechanisms using "
            "DataLad's downloaders"),
        'archive': (     # heh -- life would have been easier if consistent
            '-archive',  # suffix for cmdline
            'archives.ArchiveAnnexCustomRemote',
            "extract content from archives (.tar{,.gz}, .zip, etc) which are "
            "in turn managed by git-annex.  See `datalad add-archive-content` "
            "command"),
        'zenodo': (
            '-zenodo',
            'zenodo.ZenodoAnnexCustomRemote',
            "creates a deposition and uploads data to zenodo.org. You could "
            "later finalize that dataset and officially 'publish' by "
            "visiting its page on zenodo. Finalized datasets though cannot "
            "be changed"),
}


def setup_parser(backend):

    suffix, _, desc = BACKENDS[backend]
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


def _main(args, backend=None, leftout_args=None):
    """Unprotected portion"""
    # TODO: For now we have only one, but we might need to actually become aware
    # of multiple and provide multiple helpers/symlinks
    # OR consider implementing ultimate handler of all dl+ URLs within a
    # single beast -- probably wouldn't fly since we do might need different
    # initializations etc.
    assert(backend is not None)
    if backend not in BACKENDS:
        raise ValueError("I don't know anything about %r backend. "
                         "Known are: %s" % list(BACKENDS))
    _, module_cls, _ = BACKENDS[backend]
    try:
        module_name, cls_name = module_cls.rsplit('.', 1)
        backend_module = __import__(
            'datalad.customremotes.%s' % module_name,
            fromlist=['datalad.customremotes']
        )
    except ImportError as exc:
        raise RuntimeError(
            "Failed to import module corresponding with %s custom special "
            "remote backend: %s" % (backend, exc_str(exc))
        )

    # find subclass
    backend_cls = getattr(backend_module, cls_name)
    from .base import AnnexCustomRemote
    assert issubclass(backend_cls, AnnexCustomRemote)
    remote = backend_cls()
    if not remote:
        raise RuntimeError(
            "Failed to find an *AnnexCustomRemote class within %s"
            % backend_module)

    # TODO: handle args -- not used ATM
    # Generic commands to support:
    #   get-uri-prefix
    #   get-uri [options] with [options] being backend specific
    #           e.g. for archive --key KEY(archive) --file FILE
    command = args.command
    if command is None:
        assert not leftout_args, "not expecting any additional arguments"
        ui.set_backend('annex')  # stdin/stdout will be used for interactions with annex
        # If no command - run the special remote
        if 'DATALAD_TESTS_USECASSETTE' in os.environ:
            # optionally feeding it a cassette, used by tests
            from ..support.vcr_ import use_cassette
            with use_cassette(os.environ['DATALAD_TESTS_USECASSETTE']):
                remote.main()
        else:
            remote.main()
    elif command == 'get-uri-prefix':
        print(remote.url_prefix)
    else:
        # might be a command provided by the corresponding backend
        cmd_funcname = 'cmd_%s' % command
        cmd_func = getattr(remote, cmd_funcname, None)
        if not cmd_func:
            known = [f[4:] for f in dir(remote) if f.startswith('cmd_')]
            raise ValueError(
                "Unknown command %r. Known for %s: %s"
                % (command, backend, ', '.join(known) or 'none')
            )
        # pass all leftout args into the command
        cmd_func(leftout_args)


def main(args=None, backend=None):
    import sys
    # TODO: redirect lgr output to stderr if it is stdout and not "forced"
    # by env variable...
    #
    parser = setup_parser(backend=backend)
    # parse cmd args
    args, leftout_args = parser.parse_known_args(args)

    if args.common_debug:
        # So we could see/stop clearly at the point of failure
        setup_exceptionhook()
        _main(args, backend, leftout_args)
    else:
        # Otherwise - guard and only log the summary. Postmortem is not
        # as convenient if being caught in this ultimate except
        try:
            _main(args, backend, leftout_args)
        except Exception as exc:
            lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
            sys.exit(1)
