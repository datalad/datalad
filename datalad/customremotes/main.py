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
import logging
import sys
import textwrap

import datalad
from datalad import log
from datalad.log import lgr

import datalad.cmdline as mvcmd
from datalad.cmdline import helpers
from datalad.cmdline.main import _license_info


def setup_parser():
    # setup cmdline args parser
    # main parser
    # TODO: should be encapsulated for resharing with the main datalad's
    parser = argparse.ArgumentParser(
                    fromfile_prefix_chars='@',
                    # usage="%(prog)s ...",
                    description="%s\n\n" % datalad.__doc__ +
     "git-annex-remote-datalad command line tool enriches git-annex special "
     "remotes with some additional ones",
                    epilog='"DataLad git-annex very special remote"',
                    formatter_class=argparse.RawDescriptionHelpFormatter,
                    add_help=False,
                )
    # common options
    helpers.parser_add_common_opt(parser, 'help')
    helpers.parser_add_common_opt(parser, 'log_level')
    helpers.parser_add_common_opt(parser,
                                  'version',
                                  version='datalad %s\n\n%s' % (datalad.__version__,
                                                              _license_info()))
    if __debug__:
        parser.add_argument(
            '--dbg', action='store_true', dest='common_debug',
            help="do not catch exceptions and show exception traceback")

    return parser

def main(args=None):
    import sys
    # TODO: disable redirect lgr output to stderr if it is currently stdout
    parser = setup_parser()
    # parse cmd args
    args = parser.parse_args(args)

    # run the function associated with the selected command
    try:
        # TODO: For now we have only one, but we might need to actually become aware
        # of multiple and provide multiple helpers/symlinks
        # OR consider implementing ultimate handler of all dl+ URLs within a
        # single beast -- probably wouldn't fly since we do might need different
        # initializations etc.
        from datalad.customremotes.base import AnnexTarballCustomRemote
        remote = AnnexTarballCustomRemote()
        remote.main()
    except Exception as exc:
        lgr.error('%s (%s)' % (str(exc), exc.__class__.__name__))
        if args.common_debug:
            import pdb
            pdb.post_mortem()
        sys.exit(1)
