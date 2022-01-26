# Import functions to be tested with _ suffix and name the suite after the
# original function so we could easily benchmark it e.g. by
#    asv run --python=same -b get_parent_paths
# without need to discover what benchmark to use etc

import os
from pathlib import Path, PurePosixPath
import datalad.api as dl

from ..common import SuprocBenchmarks

import tempfile
from datalad.utils import get_tempfile_kwargs, rmtree

from datalad import lgr


class addurls1(SuprocBenchmarks):

    # Try with excluding autometa and not
    params = [None, '*']
    param_names = ['exclude_metadata']


    def setup(self, exclude_metadata):
        self.nfiles = 20
        self.temp = Path(
            tempfile.mkdtemp(
                **get_tempfile_kwargs({}, prefix='bm_addurls1')))

        self.ds = dl.create(self.temp / "ds")
        self.ds.config.set('annex.security.allowed-url-schemes', 'file', scope='local')

        # populate list.csv and files
        srcpath = PurePosixPath(self.temp)

        rows = ["url,filename,bogus1,bogus2"]
        for i in range(self.nfiles):
            (self.temp / str(i)).write_text(str(i))
            rows.append(
              "file://{}/{},{},pocus,focus"
               .format(srcpath, i, i)
            )

        self.listfile = self.temp / "list.csv"
        self.listfile.write_text(os.linesep.join(rows))

    def teardown(self, exclude_metadata):
        # would make no sense if doesn't work correctly
        # IIRC we cannot provide custom additional depends so cannot import nose
        # assert_repo_status(self.ds.path)
        status = self.ds.status()
        assert all(r['state'] == 'clean' for r in status)
        assert len(status) >= self.nfiles
        rmtree(self.temp)

    def time_addurls(self, exclude_autometa):
        lgr.warning("CSV: " + self.listfile.read_text())
        ret = dl.addurls(
            str(self.listfile), '{url}', '{filename}',
            dataset=self.ds,
            exclude_autometa=exclude_autometa
        )
        assert not any(r['status'] == 'error' for r in ret)
