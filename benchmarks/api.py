# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks of the datalad.api functionality"""

from os.path import join as opj

from datalad.api import (
    create,
    create_test_dataset,
    drop,
    install,
    ls,
)

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


# Some tracking example -- may be we should track # of datasets.datalad.org
#import gc
#def track_num_objects():
#    return len(gc.get_objects())
#track_num_objects.unit = "objects"


from .common import (
    SampleSuperDatasetBenchmarks,
    SuprocBenchmarks,
)


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


class supers(SampleSuperDatasetBenchmarks):
    """
    Benchmarks on common operations on collections of datasets using datalad API
    """

    def time_installr(self):
        # somewhat duplicating setup but lazy to do different one for now
        assert install(self.ds.path + '_', source=self.ds.path, recursive=True)

    def time_createadd(self):
        assert self.ds.create('newsubds')

    def time_createadd_to_dataset(self):
        subds = create(opj(self.ds.path, 'newsubds'))
        self.ds.save(subds.path)

    def time_ls(self):
        ls(self.ds.path)

    def time_ls_recursive(self):
        ls(self.ds.path, recursive=True)

    def time_ls_recursive_long_all(self):
        ls(self.ds.path, recursive=True, long_=True, all_=True)

    def time_subdatasets(self):
        self.ds.subdatasets()

    def time_subdatasets_with_all_paths_recursive(self):
        # to see if we do not get O(N^2) performance
        subdatasets = self.ds.subdatasets(recursive=True, result_xfm='relpaths')
        subdatasets2 = self.ds.subdatasets(path=subdatasets, recursive=True, result_xfm='relpaths')
        assert subdatasets == subdatasets2

    def time_subdatasets_recursive(self):
        self.ds.subdatasets(recursive=True)

    def time_subdatasets_recursive_first(self):
        next(self.ds.subdatasets(recursive=True, return_type='generator'))

    def time_uninstall(self):
        for subm in self.ds.repo.get_submodules_():
            self.ds.drop(subm["path"], recursive=True, what='all',
                         reckless='kill')

    def time_remove(self):
       self.ds.drop(what='all', reckless='kill', recursive=True)

    def time_diff(self):
        self.ds.diff(fr="HEAD^")

    def time_diff_recursive(self):
        self.ds.diff(fr="HEAD^", recursive=True)

    # Status must be called with the dataset, unlike diff
    def time_status(self):
        self.ds.status()

    def time_status_recursive(self):
        self.ds.status(recursive=True)


supers.time_remove.warmup_time = 0
