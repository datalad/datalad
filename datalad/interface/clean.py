# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

__docformat__ = 'restructuredtext'


from os.path import join as opj
from glob import glob
from .base import Interface
from ..ui import ui
from ..utils import rmtree, getpwd
from ..support.param import Parameter
from ..support.annexrepo import AnnexRepo
from ..cmdline.helpers import get_repo_instance
from ..consts import ARCHIVES_TEMP_DIR
from ..consts import ANNEX_TEMP_DIR

from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from logging import getLogger
lgr = getLogger('datalad.api.clean')


class Clean(Interface):
    """Clean up after DataLad (possible temporary files etc.)

    Removes extracted temporary archives, etc.

    Examples:

      $ datalad clean
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to perform the clean operation on.  If
                no dataset is given, an attempt is made to identify the dataset
                in current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        # TODO:  --info  -- which performs dry run just summarizing what is to be cleaned up
        # TODO: Python only???
        what=Parameter(
            args=("--what",),
            dest='what',
            choices=('cached-archives', 'annex-tmp'),
            nargs="*",
            doc="""What to clean.  If none specified -- all known targets are
            cleaned"""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='clean')
    def __call__(dataset=None, what=None, recursive=False, recursion_limit=None):
        dataset = require_dataset(dataset, purpose='clean-up')

        for dirpath, flag, msg, sing_pl in [
            (ARCHIVES_TEMP_DIR, "cached-archives",
             "temporary archive", ("directory", "directories")),
            (ANNEX_TEMP_DIR, "annex-tmp",
             "temporary annex", ("file", "files")),
        ]:
            lgr.info("Considering to clean %s:%s", dataset, dirpath)
            if not ((what is None) or (flag in what)):
                continue
            topdir = opj(dataset.path, dirpath)
            paths = glob(opj(topdir, '*'))
            if paths:
                pl = len(paths) > 1
                pwd = getpwd()
                # relative version if possible
                rtopdir = topdir[len(pwd) + 1:] \
                    if topdir.startswith(pwd) else topdir
                ui.message("Removing %d %s %s under %s: %s"
                           % (len(paths),
                              msg, sing_pl[int(pl)],
                              rtopdir,
                              ", ".join(sorted([x[len(topdir) + 1:] for x in paths]))))
                rmtree(topdir)

        if recursive:
            for sub in dataset.get_subdatasets(
                recursive=True,
                recursion_limit=recursion_limit,
                absolute=False):
                Dataset(sub).clean(what=what)
