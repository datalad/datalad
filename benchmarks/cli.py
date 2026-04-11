# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Benchmarks for DataLad CLI"""

from subprocess import call

from .common import StartupBenchmarks


class startup(StartupBenchmarks):
    """
    Benchmarks for datalad command startup
    """

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
