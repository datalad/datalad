# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""For now just a wrapper for Dataset.save()

"""

__docformat__ = 'restructuredtext'

import logging
from os import curdir
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import super_datasets_flag
from datalad.interface.common_opts import save_message_opt
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import amend_pathspec_with_superdatasets
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.utils import with_pathsep as _with_sep
from datalad.utils import get_dataset_root

from .base import Interface

lgr = logging.getLogger('datalad.interface.save')


@build_doc
class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records all changes that have been made
    to it. This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions
    at a later point in time.

    || PYTHON >>
    Returns
    -------
    commit or None
      `None` if nothing was saved, the resulting commit otherwise.
    << PYTHON ||
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to save. If a dataset is given, but
            no `files`, the entire dataset will be saved.""",
            constraints=EnsureDataset() | EnsureNone()),
        files=Parameter(
            args=("files",),
            metavar='FILES',
            doc="""list of files to consider. If given, only changes made
            to those files are recorded in the new state.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        message=save_message_opt,
        all_changes=Parameter(
            args=("-a", "--all-changes"),
            doc="""save all changes (even to not yet added files) of all components
            in datasets that contain any of the given paths [DEPRECATED!].""",
            action="store_true"),
        all_updated=Parameter(
            args=("-u", "--all-updated"),
            doc="""save changes of all known components in datasets that contain
            any of the given paths.""",
            action="store_true"),
        version_tag=Parameter(
            args=("--version-tag",),
            metavar='ID',
            doc="""an additional marker for that state.""",
            constraints=EnsureStr() | EnsureNone()),
        super_datasets=super_datasets_flag,
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    @staticmethod
    @datasetmethod(name='save')
    @eval_results
    def __call__(message=None, files=None, dataset=None,
                 all_updated=False, all_changes=None, version_tag=None,
                 recursive=False, recursion_limit=None, super_datasets=False
                 ):
        if all_changes is not None:
            from datalad.support.exceptions import DeprecatedError
            raise DeprecatedError(
                new="all_updated option where fits and/or datalad add",
                version="0.5.0",
                msg="RF: all_changes option passed to the save"
            )
        if not dataset and not files:
            # we got nothing at all -> save what is staged in the repo in "this" directory?
            # we verify that there is an actual repo next
            dataset = curdir
        if dataset:
            dataset = require_dataset(
                dataset, check_installed=True, purpose='saving')
        content_by_ds, unavailable_paths = Interface._prep(
            path=files,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit)
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset

        if unavailable_paths:
            for p in unavailable_paths:
                yield get_status_dict(
                    'get', path=p, status='impossible', refds=refds_path,
                    logger=lgr, message=(
                        "ignored non-existing path: %s",
                        p))

        # here we know all datasets associated with any inputs
        # so we can expand "all_updated" right here to avoid confusion
        # wrt to "super" and "intermediate" datasets discovered later on
        if all_updated:
            # and we do this by replacing any given paths with the respective
            # datasets' base path
            # MIH: this is wrong, it makes the desired use case indistinguishable
            # from an explicit "save everything underneath the dataset root"
            # remember that we have to call `git add` inside the technical reasons
            # and here we need to avoid that somehow -- yet not like this (see #1419)
            for ds in content_by_ds:
                content_by_ds[ds] = [ds]

        if super_datasets:
            content_by_ds = amend_pathspec_with_superdatasets(
                content_by_ds,
                # save up to and including the base dataset (if one is given)
                # otherwise up to the very top
                topmost=dataset if dataset else True,
                limit_single=False)

        if dataset:
            # stuff all paths also into the base dataset slot to make sure
            # we get all links between relevant subdatasets
            bp = content_by_ds.get(dataset.path, [])
            for c in content_by_ds:
                bp.extend(content_by_ds[c])
            content_by_ds[dataset.path] = list(set(bp))

        for res in save_dataset_hierarchy(
                content_by_ds,
                base=dataset.path if dataset and dataset.is_installed() else None,
                message=message,
                version_tag=version_tag):
            yield res

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if not res or res.get('type', None) != 'dataset' or 'path' not in res:
            return
        ds = Dataset(res['path'])
        commit = ds.repo.repo.head.commit
        ui.message('Saved state: {0} for {1}'.format(
            commit.hexsha,
            ds))
