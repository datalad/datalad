# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helpers for benchmarks of DataLad"""

import os
import sys
import tarfile
import tempfile
import timeit
import os.path as op
from glob import glob

from datalad.utils import (
    getpwd,
    get_tempfile_kwargs,
    rmtree,
)

from datalad.api import (
    Dataset,
    create_test_dataset,
)

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
        if not self.remove_paths:
            return  # Nothing TODO
        self.log("Cleaning up %d paths", len(self.remove_paths))
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

    def log(self, msg, *args):
        """Consistent benchmarks logging"""
        print("BM: "+ str(msg % tuple(args)))


class SampleSuperDatasetBenchmarks(SuprocBenchmarks):
    """
    Setup a sample hierarchy of datasets to be used
    """

    timeout = 3600
    # need to assure that we are working in a different repository now
    # see https://github.com/datalad/datalad/issues/1512
    # might not be sufficient due to side effects between tests and
    # thus getting into the same situation
    ds_count = 0

    # Creating in CWD so things get removed when ASV is done
    #  https://asv.readthedocs.io/en/stable/writing_benchmarks.html
    # that is where it would be run and cleaned up after

    dsname = 'testds1'
    tarfile = 'testds1.tar'

    def setup_cache(self):
        ds_path = create_test_dataset(
            self.dsname
            , spec='2/-2/-2'
            , seed=0
        )[0]
        self.log("Setup cache ds path %s. CWD: %s", ds_path, getpwd())
        # Will store into a tarfile since otherwise install -r is way too slow
        # to be invoked for every benchmark
        # Store full path since apparently setup is not ran in that directory
        self.tarfile = op.realpath(SampleSuperDatasetBenchmarks.tarfile)
        with tarfile.open(self.tarfile, "w") as tar:
            # F.CK -- Python tarfile can't later extract those because key dirs are
            # read-only.  For now just a workaround - make it all writeable
            from datalad.utils import rotree
            rotree(self.dsname, ro=False, chmod_files=False)
            tar.add(self.dsname, recursive=True)
        rmtree(self.dsname)

    def setup(self):
        self.log("Setup ran in %s, existing paths: %s", getpwd(), glob('*'))

        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm")
        )
        self.remove_paths.append(tempdir)
        with tarfile.open(self.tarfile) as tar:
            tar.extractall(tempdir)

        # TODO -- remove this abomination after https://github.com/datalad/datalad/issues/1512 is fixed
        epath = op.join(tempdir, 'testds1')
        epath_unique = epath + str(self.__class__.ds_count)
        os.rename(epath, epath_unique)
        self.__class__.ds_count += 1
        self.ds = Dataset(epath_unique)
        self.repo = self.ds.repo
        self.log("Finished setup for %s", tempdir)
