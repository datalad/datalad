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
    def setup(self):
        # we need to prepare/adjust PATH to point to installed datalad
        # We will base it on taking sys.executable
        python_path = osp.dirname(sys.executable)
        self.env = os.environ.copy()
        self.env['PATH'] = '%s:%s' % (python_path, self.env.get('PATH', ''))
        pass

    def time_help_np(self):
        call(["datalad", "--help-np"], env=self.env)
        
    def time_import(self):
        call([sys.executable, "-c", "'import datalad'"])
        


