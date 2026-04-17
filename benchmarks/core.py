# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for DataLad"""

import os
import os.path as osp
import sys
from subprocess import call

from datalad.runner import (
    GitRunner,
    Runner,
    StdOutErrCapture,
)

from .common import (
    StartupBenchmarks,
    SuprocBenchmarks,
)

# Some tracking example -- may be we should track # of datasets.datalad.org
#import gc
#def track_num_objects():
#    return len(gc.get_objects())
#track_num_objects.unit = "objects"



scripts_dir = osp.join(osp.dirname(__file__), 'scripts')
heavyout_cmd = "{} 1000".format(osp.join(scripts_dir, 'heavyout'))


class startup(StartupBenchmarks):
    """
    Benchmarks for datalad commands startup
    """

    def time_import(self):
        call([sys.executable, "-c", "import datalad"])

    def time_import_api(self):
        call([sys.executable, "-c", "import datalad.api"])


class witlessrunner(SuprocBenchmarks):
    """Some rudimentary tests to see if there is no major slowdowns of Runner
    """

    def setup(self):
        self.runner = Runner()
        self.git_runner = GitRunner()

    def time_echo(self):
        self.runner.run(["echo"])

    def time_echo_gitrunner(self):
        self.git_runner.run(["echo"])

    def time_echo_gitrunner_fullcapture(self):
        self.git_runner.run(["echo"], protocol=StdOutErrCapture)
