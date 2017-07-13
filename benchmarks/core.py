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


class startup(SuprocBenchmarks):
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


class runner(SuprocBenchmarks):
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


