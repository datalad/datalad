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
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from .base import Interface

lgr = logging.getLogger('datalad.interface.unlock')


class Unlock(Interface):
    """Unlock file(s) of a dataset

    Unlock files of a dataset in order to be able to edit the actual content
    """

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
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            recursion_limit=None):

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

        if nondataset_paths:
            lgr.warning(
                "ignored paths that do not belong to any dataset: %s",
                nondataset_paths)
        if unavailable_paths:
            lgr.warning('ignored non-existing paths: %s', unavailable_paths)

        unlocked = []
        for ds_path in sorted(content_by_ds.keys()):
            ds = Dataset(ds_path)

            if not isinstance(ds.repo, AnnexRepo):
                lgr.debug("'%s' has no annex, nothing to unlock",
                          ds)
                continue

            files = content_by_ds[ds_path]

            std_out, std_err = ds.repo._annex_custom_command(
                files, ['git', 'annex', 'unlock'])

            unlocked.extend(
                [line.split()[1] for line in std_out.splitlines()
                 if line.strip().endswith('ok')])
        return unlocked

    @staticmethod
    def result_renderer_cmdline(res, args):
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
