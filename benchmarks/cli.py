# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for DataLad CLI"""

import os
import sys
import os.path as osp

from subprocess import call
from .common import SuprocBenchmarks


class startup(SuprocBenchmarks):
    """
    Benchmarks for datalad command startup
    """

    def setup(self):
        # we need to prepare/adjust PATH to point to installed datalad
        # We will base it on taking sys.executable
        python_path = osp.dirname(sys.executable)
        self.env = os.environ.copy()
        self.env['PATH'] = '%s:%s' % (python_path, self.env.get('PATH', ''))

    def time_usage_advice(self):
        call(["datalad"], env=self.env)

    def time_short_help(self):
        call(["datalad", "-h"], env=self.env)

    def time_help_np(self):
        call(["datalad", "--help-np"], env=self.env)

    def time_command_short_help(self):
        call(["datalad", "wtf", "-h"], env=self.env)

    def time_command_help_np(self):
        call(["datalad", "wtf", "--help-np"], env=self.env)

    def time_command_execution(self):
        # pick a command that should be minimally impacted by
        # non-CLI factors
        call(["datalad", "wtf", "-S", "python"], env=self.env)
