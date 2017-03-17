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
from datalad.utils import with_pathsep as _with_sep
from datalad.utils import get_dataset_root

from .base import Interface

lgr = logging.getLogger('datalad.interface.save')


def process_vanished_paths(unavailable_paths, content_by_ds):
    # presently unavailable paths could be, e.g., deleted files, or
    # uninstalled subdatasets, or simply nothing -> figure it out and act
    # accordingly
    dsinfo = {}
    nonexistent_paths = []
    for p in unavailable_paths:
        # we need to check whether any of these correspond
        # to a known subdataset, and add those to the list of
        # things to be removed
        toppath = get_dataset_root(p)
        if not toppath:
            nonexistent_paths.append(p)
            continue
        ds = Dataset(toppath)
        dinfo = dsinfo.get(toppath,
                           {'deleted': ds.repo.get_deleted_files(),
                            'subds': ds.get_subdatasets(
                                recursive=False, absolute=True)})
        # cache for a potentially following request
        dsinfo[toppath] = dinfo
        if p in dinfo['subds']:
            # test for subds needs to come first, as it would also show
            # up in "deleted_files"
            # this is a known subdataset that has vanished
            lgr.debug('deinit vanished subdataset {} in {}'.format(p, ds))
            # simply deinit to complete a "forced uninstallation", without
            # an explicit "remove" there is nothing to be save in this
            # case
            ds.repo.deinit_submodule(p[len(_with_sep(ds.path)):])
        elif p in dinfo['deleted']:
            # vanished file -> 'git rm' it to stage the change
            ds.repo.remove(p)
            # record that we are "saving" this path
            dpaths = content_by_ds.get(ds.path, [])
            dpaths.append(p)
            content_by_ds[ds.path] = dpaths
        else:
            # this is nothing we can anyhow handle
            nonexistent_paths.append(p)
    return content_by_ds, nonexistent_paths


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
        if unavailable_paths:
            lgr.warning("ignoring non-existent path(s): %s",
                        unavailable_paths)
        # here we know all datasets associated with any inputs
        # so we can expand "all_updated" right here to avoid confusion
        # wrt to "super" and "intermediate" datasets discovered later on
        if all_updated:
            # and we do this by replacing any given paths with the respective
            # datasets' base path
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

        saved_ds = save_dataset_hierarchy(
            content_by_ds,
            base=dataset.path if dataset and dataset.is_installed() else None,
            message=message,
            version_tag=version_tag)

        return saved_ds

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        if not res:
            return
        for ds in res:
            commit = ds.repo.repo.head.commit
            ui.message('Saved state: {0} for {1}'.format(
                commit.hexsha,
                ds))
