# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for benchmarks of DataLad"""

import sys
import timeit
import os.path as op

from datalad.utils import rmtree

############
# Monkey patches

# Robust is_interactive.  Should be not needed since 0.11.4
# https://github.com/datalad/datalad/pull/3268
def _is_stream_tty(stream):
    try:
        # TODO: check on windows if hasattr check would work correctly and
        # add value:
        return stream.isatty()
    except ValueError as exc:
        # Who knows why it is a ValueError, but let's try to be specific
        # If there is a problem with I/O - non-interactive, otherwise reraise
        if "I/O" in str(exc):
            return False
        raise


def is_interactive():
    """Return True if all in/outs are tty"""
    return all(_is_stream_tty(s) for s in (sys.stdin, sys.stdout, sys.stderr))


class SuprocBenchmarks(object):
    # manually set a number since otherwise takes way too long!
    # see https://github.com/spacetelescope/asv/issues/497
    #number = 3
    # although seems to work ok with a timer which accounts for subprocesses

    # custom timer so we account for subprocess times
    timer = timeit.default_timer

    _monkey_patched = False

    def __init__(self):
        if not self._monkey_patched:
            # monkey patch things if needed
            # ASV started to close one of the std streams since some point
            # which caused our is_interactive to fail.  We need to provide
            # more robust version
            from datalad.support.external_versions import external_versions
            # comparing to 0.12.1  since the returned version is "loose"
            # so fails correctly identify rc as pre .0
            if external_versions['datalad'] < '0.12.1':
                from datalad import utils
                from datalad.interface import ls
                utils.is_interactive = is_interactive
                ls.is_interactive = is_interactive
            SuprocBenchmarks._monkey_patched = True
        self.remove_paths = []

    def _cleanup(self):
        while self.remove_paths:
            path = self.remove_paths.pop()
            if op.lexists(path):
                rmtree(path)

    def teardown(self):
        self._cleanup()

    def __del__(self):
        # We will at least try
        try:
            self._cleanup()
        except:
            pass
