# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""This is the main() CLI entryproint"""

# It should start-up and run as fast as possible for a responsive CLI.

# Imports are done inline and as late as possible to avoid paying for
# an unconditional commulative overhead that is only actually needed
# in some special cases.

__docformat__ = 'restructuredtext'

import logging

lgr = logging.getLogger('datalad.cli')

lgr.log(5, "Importing cli.main")

import os
import sys

import datalad

from .parser import setup_parser

# TODO cross-check with unconditional imports in .parser
# special case imports
#   from .helpers import _fix_datalad_ri
#   import platform
#   from .helpers import _parse_overrides_from_cmdline
#   from datalad.utils import chpwd
#   from .utils import setup_exceptionhook
#   from datalad.support.exceptions import ...

# unconditional imports, no meaningful functionality without them
#   from .parser import setup_parser


def _on_msys_tainted_paths():
    """This duplicates datalad.utils.on_msys_tainted_paths

    But it does it while minimizing runtime penalties on all irrelevant
    systems.
    """
    if os.environ.get('MSYSTEM', '')[:4] not in ('MSYS', 'MING'):
        return False
    if 'MSYS_NO_PATHCONV' in os.environ:
        return False
    import platform
    if platform.system().lower() != 'windows':
        return False
    return True


def main(args=sys.argv):
    """Main CLI entrypoint"""
    lgr.log(5, "Starting main(%r)", args)
    # record that we came in via the cmdline
    datalad.__api = 'cmdline'
    completing = "_ARGCOMPLETE" in os.environ
    if completing and 'COMP_LINE' in os.environ:
        import shlex

        # TODO support posix=False too?
        args = shlex.split(os.environ['COMP_LINE']) or args

    if _on_msys_tainted_paths():
        # Possibly present DataLadRIs were stripped of a leading /
        from .helpers import _fix_datalad_ri
        args = [_fix_datalad_ri(s) for s in args]

    from datalad.support.entrypoints import load_extensions

    # load extensions requested by configuration
    # analog to what coreapi is doing for a Python session
    # importantly, load them prior to parser construction, such
    # that CLI tuning is also within reach for extensions
    load_extensions()

    # PYTHON_ARGCOMPLETE_OK
    # TODO possibly construct a dedicated parser just for autocompletion
    # rather than lobotomizing the normal one
    parser = setup_parser(args, completing=completing)
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass

    # parse cmd args
    lgr.debug("Parsing known args among %r", args)
    cmdlineargs, unparsed_args = parser.parse_known_args(args[1:])
    # did the parser tell us what command to run?
    has_func = hasattr(cmdlineargs, 'func') and cmdlineargs.func is not None
    if unparsed_args:
        if has_func:
            lgr.error('unknown argument%s: %s',
                's' if len(unparsed_args) > 1 else '',
                unparsed_args if len(unparsed_args) > 1 else unparsed_args[0],
            )
            cmdlineargs.subparser.print_usage()
            sys.exit(1)
        else:
            # store all unparsed arguments
            cmdlineargs.datalad_unparsed_args = unparsed_args

    # pull config overrides from cmdline args and put in effect
    if cmdlineargs.cfg_overrides is not None:
        from .helpers import _parse_overrides_from_cmdline
        datalad.cfg.overrides.update(
            _parse_overrides_from_cmdline(cmdlineargs)
        )
        # enable overrides
        datalad.cfg.reload(force=True)
        # try loading extensions again, in case the configuration
        # added new ones to consider
        load_extensions()

    if 'datalad.runtime.librarymode' in datalad.cfg:
        datalad.enable_librarymode()

    if cmdlineargs.change_path is not None:
        from datalad.utils import chpwd
        for path in cmdlineargs.change_path:
            chpwd(path)

    # check argparse could determine what commands needs to be executed
    if not has_func:
        # just let argparser spit out its error, since there is smth wrong
        parser.parse_args(args)
        # if that one didn't puke -- we should
        parser.print_usage()
        lgr.error("Please specify the command")
        # matches exit code for InsufficientArgumentsError
        sys.exit(2)

    _run(cmdlineargs)


def _run(namespace):
    """Execute a CLI operation

    Depending on CLI debugging options the CLI operation is executed
    in a debug harness or an exception handler.

    Parameters
    ----------
    namespace: Namespace
      Object returned by `ArgumentParser.parse_args()` with fully
      populated and validated CLI command and arguments.

    Raises
    ------
    SystemExit
      When the CLI completed without error (exit 0).
    """
    # execute the command, either with a debugger catching
    # a crash, or with a simplistic exception handler.
    # note that result rendering is happening in the
    # execution handler, when the command-generator is unwound
    ret = _run_with_debugger(namespace) \
        if namespace.common_debug or namespace.common_idebug \
        else _run_with_exception_handler(namespace)

    # all good, not strictly needed, but makes internal testing easier
    sys.exit(0)


def _run_with_debugger(cmdlineargs):
    """Execute the command and drop into debugger if it crashes"""
    from .utils import setup_exceptionhook

    # so we could see/stop clearly at the point of failure
    setup_exceptionhook(ipython=cmdlineargs.common_idebug)
    return cmdlineargs.func(cmdlineargs)


def _run_with_exception_handler(cmdlineargs):
    """Execute the command and perform some reporting
    normalization if it crashes, but otherwise just let it go"""
    # otherwise - guard and only log the summary. Postmortem is not
    # as convenient if being caught in this ultimate except
    try:
        return cmdlineargs.func(cmdlineargs)
    # catch BaseException for KeyboardInterrupt
    except BaseException as exc:
        from datalad.support.exceptions import (
            CapturedException,
            CommandError,
            IncompleteResultsError,
            InsufficientArgumentsError,
        )
        ce = CapturedException(exc)
        # we crashed, it has got to be non-zero for starters
        exit_code = 1
        if isinstance(exc, InsufficientArgumentsError):
            # if the func reports inappropriate usage, give help output
            lgr.error('%s (%s)', ce, exc.__class__.__name__)
            cmdlineargs.subparser.print_usage(sys.stderr)
            exit_code = 2
        elif isinstance(exc, IncompleteResultsError):
            # in general we do not want to see the error again, but
            # present in debug output
            lgr.debug('could not perform all requested actions: %s', ce)
            # fish for an exit code. If any of the "failed" results
            # is caused by a command error, it will come with an `exit_code`
            # property.
            exit_codes = [
                r['exit_code'] for r in exc.failed if 'exit_code' in r]
            if exit_codes:
                # we have exit code(s), take the first non-0 one
                non0_codes = [e for e in exit_codes if e]
                if len(non0_codes) != len(exit_codes):
                    lgr.debug(
                        "Among %d incomplete results with exit codes %d had exit code 0",
                        len(exit_codes),
                        len(exit_codes) - len(non0_codes))
                if non0_codes:
                    exit_code = non0_codes[0]
        elif isinstance(exc, CommandError):
            exit_code = _communicate_commanderror(exc) or exit_code
        elif isinstance(exc, KeyboardInterrupt):
            from datalad.ui import ui
            ui.error("\nInterrupted by user while doing magic: %s" % ce)
            exit_code = 3
        else:
            # some unforeseen problem
            lgr.error('%s', ce.format_with_cause())
        sys.exit(exit_code)


def _communicate_commanderror(exc):
    """Behave as if the command ran directly"""
    exc_msg = exc.to_str(include_output=False)
    if exc_msg:
        msg = exc_msg.encode() if isinstance(exc_msg, str) else exc_msg
        os.write(2, msg + b"\n")
    # push any captured output to the respective streams
    for out, stream in ((exc.stdout, 1), (exc.stderr, 2)):
        if out:
            os.write(stream,
                     out.encode() if isinstance(out, str) else out)
    # pass on exit code
    return exc.code


lgr.log(5, "Done importing cli.main")
