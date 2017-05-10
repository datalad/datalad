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
import timeit

from subprocess import call

from datalad.api import add
from datalad.api import create
from datalad.api import create_test_dataset
from datalad.api import install
from datalad.api import ls

from datalad.utils import rmtree

# Some tracking example -- may be we should track # of datasets.datalad.org
#import gc
#def track_num_objects():
#    return len(gc.get_objects())
#track_num_objects.unit = "objects"


class SuprocBenchmarks(object):
    # manually set a number since otherwise takes way too long!
    # see https://github.com/spacetelescope/asv/issues/497
    #number = 3
    # although seems to work ok with a timer which accounts for subprocesses

    # custom timer so we account for subprocess times
    timer = timeit.default_timer


class StartupSuite(SuprocBenchmarks):
    """
    Benchmarks for datalad commands startup
    """

    def setup(self):
        # we need to prepare/adjust PATH to point to installed datalad
        # We will base it on taking sys.executable
        python_path = osp.dirname(sys.executable)
        self.env = os.environ.copy()
        self.env['PATH'] = '%s:%s' % (python_path, self.env.get('PATH', ''))

    def time_help_np(self):
        call(["datalad", "--help-np"], env=self.env)
        
    def time_import(self):
        call([sys.executable, "-c", "import datalad"])

    def time_import_api(self):
        call([sys.executable, "-c", "import datalad.api"])


class RunnerSuite(SuprocBenchmarks):
    """Some rudimentary tests to see if there is no major slowdowns from Runner
    """

    def setup(self):
        from datalad.cmd import Runner
        self.runner = Runner()
        # older versions might not have it
        try:
            from datalad.cmd import GitRunner
            self.git_runner = GitRunner()
        except ImportError:
            pass

    def time_echo(self):
        self.runner.run("echo")

    def time_echo_gitrunner(self):
        self.git_runner.run("echo")


class CreateTestDatasetSuite(SuprocBenchmarks):
    """
    Benchmarks to test on create_test_dataset how fast we could generate datasets
    """

    def time_create_test_dataset1(self):
        create_test_dataset(spec='1', seed=0)

    def time_create_test_dataset2x2(self):
        create_test_dataset(spec='2/2', seed=0)


class SuperdatasetsOperationsSuite(SuprocBenchmarks):
    """
    Benchmarks on common operations on collections of datasets using datalad API
    """

    def setup_cache(self):
        # creating in CWD so things get removed when ASV is done
        return create_test_dataset("testds1", spec='2/-3/-2', seed=0)[0]

    def setup(self, orig_ds_path):
        self.ds = install(orig_ds_path + '_clone',
                          source=orig_ds_path,
                          recursive=True)
        # 0.5.x versions return a list of all installed datasets when recursive
        if isinstance(self.ds, list):
            self.ds = self.ds[0]

    def teardown(self, orig_ds_path):
        rmtree(self.ds.path)
        possibly_installed = self.ds.path + '_'
        if osp.exists(possibly_installed):
            rmtree(possibly_installed)

    def time_installr(self, orig_ds_path):
        # somewhat duplicating setup but lazy to do different one for now
        assert install(self.ds.path + '_', source=self.ds.path, recursive=True)

    def time_createadd(self, orig_ds_path):
        assert self.ds.create('newsubds')

    def time_createadd_to_dataset(self, orig_ds_path):
        subds = create(opj(self.ds.path, 'newsubds'))
        self.ds.add(subds.path)

    def time_ls(self, orig_ds_path):
        ls(self.ds.path)
