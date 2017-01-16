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

from subprocess import call


class StartupSuite:
    """
    Benchmarks for datalad commands startup
    """

    # manually set a number since otherwise takes way too long!
    # see https://github.com/spacetelescope/asv/issues/497
    number = 5

    def setup(self):
        # we need to prepare/adjust PATH to point to installed datalad
        # We will base it on taking sys.executable
        python_path = osp.dirname(sys.executable)
        self.env = os.environ.copy()
        self.env['PATH'] = '%s:%s' % (python_path, self.env.get('PATH', ''))

    def time_help_np(self):
        call(["datalad", "--help-np"], env=self.env)
        
    def time_import(self):
        call([sys.executable, "-c", "'import datalad'"])

    def time_import_api(self):
        call([sys.executable, "-c", "'import datalad.api'"])


class RunnerSuite:
    """Some rudimentary tests to see if there is no major slowdowns from Runner
    """

    def setup(self):
        from datalad.cmd import Runner, GitRunner
        self.runner = Runner()
        self.git_runner = GitRunner()

    def time_echo(self):
        self.runner.run("echo")

    def time_echo_gitrunner(self):
        self.git_runner.run("echo")