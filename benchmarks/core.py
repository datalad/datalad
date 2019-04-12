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

from time import time
from subprocess import call

from datalad.cmd import Runner

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

scripts_dir = osp.join(osp.dirname(__file__), 'scripts')
heavyout_cmd = "{} 1000".format(osp.join(scripts_dir, 'heavyout'))

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

    # Following "track" measures computing overhead comparing to the simplest
    # os.system call on the same command without carrying for in/out

    unit = "% overhead"

    def _get_overhead(self, cmd, nrepeats=3, **run_kwargs):
        """Estimate overhead over running command via the simplest os.system
        and to not care about any output
        """
        # asv does not repeat tracking ones I think, so nrepeats
        overheads = []
        for _ in range(nrepeats):
            t0 = time()
            os.system(cmd + " >/dev/null 2>&1")
            t1 = time()
            self.runner.run(cmd, **run_kwargs)
            t2 = time()
            overhead = 100 * ((t2 - t1) / (t1 - t0) - 1.0)
            # print("O :", t1 - t0, t2 - t0, overhead)
            overheads.append(overhead)
        overhead = round(sum(overheads) / len(overheads), 2)
        #overhead = round(min(overheads), 2)
        return overhead

    def track_overhead_echo(self):
        return self._get_overhead("echo")

    # 100ms chosen below as providing some sensible stability for me.
    # at 10ms -- too much variability
    def track_overhead_100ms(self):
        return self._get_overhead("sleep 0.1")

    def track_overhead_heavyout(self):
        # run busyloop for 100ms outputing as much as it could
        return self._get_overhead(heavyout_cmd)

    def track_overhead_heavyout_online_through(self):
        return self._get_overhead(heavyout_cmd,
                                  log_stderr='offline',  # needed to would get stuck
                                  log_online=True)

    def track_overhead_heavyout_online_process(self):
        return self._get_overhead(heavyout_cmd,
                                  log_stdout=lambda s: '',
                                  log_stderr='offline',  # needed to would get stuck
                                  log_online=True)

    # # Probably not really interesting, and good lord wobbles around 0
    # def track_overhead_heavyout_offline(self):
    #     return self._get_overhead(heavyout_cmd,
    #                               log_stdout='offline',
    #                               log_stderr='offline')

    # TODO: track the one with in/out, i.e. for those BatchedProcesses