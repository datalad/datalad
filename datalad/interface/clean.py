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
from ..utils import rmtree
from ..support.param import Parameter
from ..consts import ARCHIVES_TEMP_DIR
from ..consts import ANNEX_TEMP_DIR

from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import require_dataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc

from logging import getLogger
lgr = getLogger('datalad.api.clean')


@build_doc
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
    @eval_results
    def __call__(dataset=None, what=None, recursive=False, recursion_limit=None):
        ds = require_dataset(dataset, purpose='clean-up')
        res_kwargs = dict(action='clean', logger=lgr, refds=ds.path)
        for ap in AnnotatePaths.__call__(
                dataset=ds.path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='clean',
                unavailable_path_status='impossible',
                nondataset_path_status='impossible',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                yield ap
                continue
            if ap.get('type', None) != 'dataset':
                ap.update(status='impossible',
                          message='only datasets can be cleaned')
                yield ap
                continue
            d = ap['path']
            for dirpath, flag, msg, sing_pl in [
                (ARCHIVES_TEMP_DIR, "cached-archives",
                 "temporary archive", ("directory", "directories")),
                (ANNEX_TEMP_DIR, "annex-tmp",
                 "temporary annex", ("file", "files")),
            ]:
                topdir = opj(d, dirpath)
                lgr.debug("Considering to clean %s:%s", d, dirpath)
                if not ((what is None) or (flag in what)):
                    yield get_status_dict(
                        path=topdir, status='notneeded', type='dir', **res_kwargs)
                    continue
                paths = glob(opj(topdir, '*'))
                if not paths:
                    yield get_status_dict(
                        path=topdir, status='notneeded', type='dir', **res_kwargs)
                    continue
                pl = len(paths) > 1
                message = ("Removed %d %s %s: %s",
                           len(paths), msg, sing_pl[int(pl)],
                           ", ".join(sorted([x[len(topdir) + 1:] for x in paths])))
                rmtree(topdir)
                yield get_status_dict(
                    path=topdir, status='ok', type='dir', message=message,
                    **res_kwargs)
