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
from os import curdir

from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.utils import get_normalized_path_arguments
from datalad.interface.utils import get_paths_by_dataset
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
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

        # TODO: require dataset

        if path is None and dataset is None:
            raise InsufficientArgumentsError(
                "insufficient arguments for unlocking: needs at least "
                "a dataset or a path to unlock.")

        resolved_paths, dataset_path = get_normalized_path_arguments(
            path, dataset, default=curdir)

        content_by_ds, unavailable_paths, nondataset_paths = \
            get_paths_by_dataset(resolved_paths,
                                 recursive=recursive,
                                 recursion_limit=recursion_limit)
        res_kwargs = dict(
            action='unlock', logger=lgr,
            refds=dataset.path if isinstance(dataset, Dataset) else dataset)

        for r in results_from_paths(
                nondataset_paths, status='impossible',
                message="path does not belong to any dataset: %s",
                **res_kwargs):
            yield r
        for r in results_from_paths(
                unavailable_paths, status='impossible',
                message="path does not exist", **res_kwargs):
            yield r

        for ds_path in sorted(content_by_ds.keys()):
            ds = Dataset(ds_path)

            if not isinstance(ds.repo, AnnexRepo):
                lgr.debug("'%s' has no annex, nothing to unlock",
                          ds)
                continue

            files = content_by_ds[ds_path]

            for r in ds.repo.unlock(files):
                yield get_status_dict(
                    path=r, status='ok', type='file', **res_kwargs)

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was unlocked")
            return
        items = '\n'.join(map(str, res))
        msg = "Unlocked {n} files:\n{items}".format(
            n=len(res),
            items=items)
        ui.message(msg)
