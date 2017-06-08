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
import timeit

from subprocess import call

from datalad.api import add
from datalad.api import create
from datalad.api import create_test_dataset
from datalad.api import Dataset
from datalad.api import install
from datalad.api import ls
from datalad.api import remove
from datalad.api import uninstall

from datalad.utils import rmtree
from datalad.utils import getpwd

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
        create_test_dataset(spec='1', seed=0)

    def time_create_test_dataset2x2(self):
        create_test_dataset(spec='2/2', seed=0)


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
    def setup_cache(self):
        # creating in CWD so things get removed when ASV is done
        ds_path = create_test_dataset("testds1", spec='2/-2/-2', seed=0)[0]
        # Will store into a tarfile since otherwise install -r is way too slow
        # to be invoked for every benchmark
        tarfile_path = opj(osp.dirname(ds_path), 'testds1.tar')
        with tarfile.open(tarfile_path, "w") as tar:
            # F.CK -- Python tarfile can't later extract those because key dirs are
            # read-only.  For now just a workaround - make it all writeable
            from datalad.utils import rotree
            rotree('testds1', ro=False, chmod_files=False)
            tar.add('testds1', recursive=True)
        rmtree('testds1')

        return tarfile_path

    def setup(self, tarfile_path):
        import tarfile
        tempdir = osp.dirname(tarfile_path)
        with tarfile.open(tarfile_path) as tar:
            tar.extractall(tempdir)

        # TODO -- remove this abomination after https://github.com/datalad/datalad/issues/1512 is fixed
        epath = opj(tempdir, 'testds1')
        epath_unique = epath + str(self.__class__.ds_count)
        os.rename(epath, epath_unique)
        self.__class__.ds_count += 1
        self.ds = Dataset(epath_unique)
        print("Finished setup for %s" % tempdir)

    def teardown(self, tarfile_path):
        for path in [self.ds.path + '_', self.ds.path]:
            print("Cleaning up %s" % path)
            if osp.exists(path):
                rmtree(path)

    def time_installr(self, tarfile_path):
        # somewhat duplicating setup but lazy to do different one for now
        assert install(self.ds.path + '_', source=self.ds.path, recursive=True)

    def time_createadd(self, tarfile_path):
        assert self.ds.create('newsubds')

    def time_createadd_to_dataset(self, tarfile_path):
        subds = create(opj(self.ds.path, 'newsubds'))
        self.ds.add(subds.path)

    def time_ls(self, tarfile_path):
        ls(self.ds.path)

    # TODO: since doesn't really allow to uninstall top level ds... bleh ;)
    #def time_uninstall(self, tarfile_path):
    #    uninstall(self.ds.path, recursive=True)

    def time_remove(self, tarfile_path):
        remove(self.ds.path, recursive=True)
