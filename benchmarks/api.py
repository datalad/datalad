# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for DataLad"""

import os
import sys
import os.path as osp
from os.path import join as opj
import tarfile
import tempfile

from subprocess import call

from datalad.api import add
from datalad.api import create
from datalad.api import create_test_dataset
from datalad.api import Dataset
from datalad.api import install
from datalad.api import ls
from datalad.api import remove
from datalad.api import uninstall

#
# Following ones could be absent in older versions
#
try:
    from datalad.api import diff
except ImportError:
    diff = None

try:
    from datalad.api import status
except ImportError:
    status = None

from datalad.utils import (
    getpwd,
    get_tempfile_kwargs,
    rmtree,
)

# Some tracking example -- may be we should track # of datasets.datalad.org
#import gc
#def track_num_objects():
#    return len(gc.get_objects())
#track_num_objects.unit = "objects"


from .common import SuprocBenchmarks


class testds(SuprocBenchmarks):
    """
    Benchmarks to test on create_test_dataset how fast we could generate datasets
    """

    def time_create_test_dataset1(self):
        self.remove_paths.extend(
            create_test_dataset(spec='1', seed=0)
        )

    def time_create_test_dataset2x2(self):
        self.remove_paths.extend(
            create_test_dataset(spec='2/2', seed=0)
        )


class supers(SuprocBenchmarks):
    """
    Benchmarks on common operations on collections of datasets using datalad API
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
        self.tarfile = osp.realpath(supers.tarfile)
        with tarfile.open(self.tarfile, "w") as tar:
            # F.CK -- Python tarfile can't later extract those because key dirs are
            # read-only.  For now just a workaround - make it all writeable
            from datalad.utils import rotree
            rotree(self.dsname, ro=False, chmod_files=False)
            tar.add(self.dsname, recursive=True)
        rmtree(self.dsname)

    def setup(self):
        import tarfile
        from glob import glob
        self.log("Setup ran in %s, existing paths: %s", getpwd(), glob('*'))

        tempdir = tempfile.mkdtemp(
            **get_tempfile_kwargs({}, prefix="bm")
        )
        self.remove_paths.append(tempdir)
        with tarfile.open(self.tarfile) as tar:
            tar.extractall(tempdir)

        # TODO -- remove this abomination after https://github.com/datalad/datalad/issues/1512 is fixed
        epath = opj(tempdir, 'testds1')
        epath_unique = epath + str(self.__class__.ds_count)
        os.rename(epath, epath_unique)
        self.__class__.ds_count += 1
        self.ds = Dataset(epath_unique)
        self.log("Finished setup for %s", tempdir)

    def time_installr(self):
        # somewhat duplicating setup but lazy to do different one for now
        assert install(self.ds.path + '_', source=self.ds.path, recursive=True)

    def time_createadd(self):
        assert self.ds.create('newsubds')

    def time_createadd_to_dataset(self):
        subds = create(opj(self.ds.path, 'newsubds'))
        self.ds.add(subds.path)

    def time_ls(self):
        ls(self.ds.path)

    def time_ls_recursive(self):
        ls(self.ds.path, recursive=True)

    def time_ls_recursive_long_all(self):
        ls(self.ds.path, recursive=True, long_=True, all_=True)

    def time_get_subdatasets(self):
        self.ds.get_subdatasets()

    def time_get_subdatasets_recursive(self):
        self.ds.get_subdatasets(recursive=True)

    def time_subdatasets(self):
        self.ds.subdatasets()

    def time_subdatasets_recursive(self):
        self.ds.subdatasets(recursive=True)

    def time_subdatasets_recursive_first(self):
        next(self.ds.subdatasets(recursive=True, return_type='generator'))

    def time_uninstall(self):
        for subm in self.ds.repo.get_submodules():
            self.ds.uninstall(subm.path, recursive=True, check=False)

    def time_remove(self):
        remove(self.ds.path, recursive=True)

    def time_diff(self):
        diff(self.ds.path, revision="HEAD^")

    def time_diff_recursive(self):
        diff(self.ds.path, revision="HEAD^", recursive=True)

    def time_status(self):
        status(self.ds.path)

    def time_status_recursive(self):
        status(self.ds.path, recursive=True)