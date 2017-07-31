# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a proxy to git annex unlock

"""

__docformat__ = 'restructuredtext'

import logging

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from .base import Interface

lgr = logging.getLogger('datalad.interface.unlock')


@build_doc
class Unlock(Interface):
    """Unlock file(s) of a dataset

    Unlock files of a dataset in order to be able to edit the actual content
    """

    result_xfm = 'paths'
    on_failure = 'continue'

    _params_ = dict(
        path=Parameter(
            args=("path",),
            doc="""file(s) to unlock""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to unlock files in. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory. If the latter fails, an
            attempt is made to identify the dataset based on `path` """,
            constraints=EnsureDataset() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='unlock')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None):

        if path is None and dataset is None:
            raise InsufficientArgumentsError(
                "insufficient arguments for unlocking: needs at least "
                "a dataset or a path to unlock.")

        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='unlock', logger=lgr, refds=refds_path)

        to_process = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='unlock',
                unavailable_path_status='impossible',
                unavailable_path_msg="path does not exist",
                nondataset_path_status='impossible',
                modified=None,
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', 'dataset') == 'dataset':
                # this is a dataset
                ap['process_content'] = True
            to_process.append(ap)

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        for ds_path in sorted(content_by_ds.keys()):
            ds = Dataset(ds_path)
            content = content_by_ds[ds_path]

            if not isinstance(ds.repo, AnnexRepo):
                for ap in content:
                    ap['status'] = 'notneeded'
                    ap['message'] = "not annex'ed, nothing to unlock"
                    ap.update(res_kwargs)
                    yield ap
                continue

            files = [ap['path'] for ap in content]

            for r in ds.repo.unlock(files):
                yield get_status_dict(
                    path=r, status='ok', type='file', **res_kwargs)
