# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""CLI entrypoint for special remotes"""

__docformat__ = 'restructuredtext'


import argparse
import logging

from datalad.cli.parser import (
    parser_add_common_opt,
    parser_add_version_opt,
)
from datalad.cli.utils import setup_exceptionhook
from datalad.ui import ui

lgr = logging.getLogger('datalad.customremotes')


def setup_parser(remote_name, description):
    # setup cmdline args parser
    # main parser
    parser = argparse.ArgumentParser(
        description= \
        f"git-annex-remote-{remote_name} is a git-annex custom special " \
        f"remote to {description}",
        epilog='"DataLad\'s git-annex very special remote"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    # common options
    parser_add_common_opt(parser, 'log_level')
    parser_add_version_opt(parser, 'datalad', include_name=True)
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="Catch exceptions and fall into debugger upon exception")
    return parser


def _main(args, cls):
    """Unprotected portion"""
    assert(cls is not None)
    from annexremote import Master
    master = Master()
    remote = cls(master)
    master.LinkRemote(remote)
    master.Listen()
    # cleanup
    if hasattr(remote, 'stop'):
        remote.stop()


def main(args=None, cls=None, remote_name=None, description=None):
    import sys

    from datalad.support.entrypoints import load_extensions

    # load extensions requested by configuration
    # analog to what coreapi is doing for a Python session
    # importantly, load them prior to parser construction, such
    # that CLI tuning is also within reach for extensions
    load_extensions()

    parser = setup_parser(remote_name, description)
    # parse cmd args
    args = parser.parse_args(args)

    # stdin/stdout will be used for interactions with annex
    ui.set_backend('annex')

    if args.common_debug:
        # So we could see/stop clearly at the point of failure
        setup_exceptionhook()
        _main(args, cls)
    else:
        # Otherwise - guard and only log the summary. Postmortem is not
        # as convenient if being caught in this ultimate except
        try:
            _main(args, cls)
        except Exception as exc:
            lgr.debug('%s (%s) - passing ERROR to git-annex and exiting',
                      str(exc), exc.__class__.__name__)
            # `SpecialRemote` classes are supposed to catch everything and
            # turn it into a `RemoteError` resulting in an ERROR message to
            # annex. If we end up here, something went wrong outside of the
            # `master.Listen()` call in `_main`.
            # In any case, exiting the special remote process should be
            # accompanied by such an ERROR message to annex rather than a log
            # message.
            print("ERROR %s (%s)" % (str(exc), exc.__class__.__name__))
            sys.exit(1)
