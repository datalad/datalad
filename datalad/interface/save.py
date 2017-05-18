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
from os.path import abspath


from datalad.utils import unique
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.distribution.dataset import Dataset
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import super_datasets_flag
from datalad.interface.common_opts import save_message_opt
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.utils import get_tree_roots
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.utils import save_dataset

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
            # TODO do only if a path actually is a dataset, otherwise too much magic
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
    # TODO files -> path
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
            dataset = abspath(curdir)
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset
        if super_datasets:
            # TODO search for the topmost superdataset of any path and
            # make that one the reference
            pass

        to_process = []
        for ap in AnnotatePaths.__call__(
                path=files,
                dataset=refds_path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='save',
                unavailable_path_status='impossible',
                unavailable_path_msg="path does not exist: %s",
                nondataset_path_status='impossible',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', None) == 'dataset' and all_updated:
                ap['updated_only'] = True
                ap['process_content'] = True
            to_process.append(ap)

        if not to_process:
            # nothing left to do, potentially all errored before
            return

        # sort all datasets under their potential superdatasets
        # start from the top to get all subdatasets down the line
        # and collate them into as few superdatasets as possible
        # this is quick, just string operations
        superdss = get_tree_roots(
            unique([ap['parentds'] for ap in to_process if 'parentds' in ap]))
        # for each "superdataset" check the tree of subdatasets and make sure
        # we gather all datasets between the super and any subdataset
        # so we can save them all bottom-up in order to be able to properly
        # save the superdataset
        # if this is called from e.g. `add` this is actually no necessary,
        # but in the general case we cannot avoid it
        # TODO maybe introduce a switch?
        discovered = {}
        for superds_path in superdss:
            target_subs = superdss[superds_path]
            discover_dataset_trace_to_targets(
                # from here
                superds_path,
                # to all
                target_subs,
                [],
                discovered)
        # create a new minimally annotated path for each discovered dataset
        for parentds in discovered:
            for subds in discovered[parentds]:
                to_process.append(dict(
                    path=subds,
                    parentds=parentds,
                    type='dataset'))

        # now re-annotate all paths, this will be fast for already annotated ones
        # and will amend the annotation for others, deduplication happens here too
        annotated_paths = AnnotatePaths.__call__(
            path=to_process,
            dataset=dataset,
            # never recursion, done already
            recursive=False,
            action='save',
            unavailable_path_status='impossible',
            unavailable_path_msg="path does not exist: %s",
            nondataset_path_status='impossible',
            return_type='generator',
            # if there is an error now, we made this mistake in here
            on_failure='stop')

        # now sort into datasets so we can process them one by one
        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                annotated_paths,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        # iterate over all datasets, starting at the bottom
        for dspath in sorted(content_by_ds.keys(), reverse=True):
            ds = Dataset(dspath)
            res = get_status_dict('save', ds=ds, logger=lgr)
            if not ds.is_installed():
                # TODO This is likely impossible now
                res['status'] = 'impossible'
                res['message'] = ('dataset %s is not installed', ds)
                yield res
                continue
            saved_state = save_dataset(
                ds,
                # TODO pass all the goodness inside
                [p['path'] if isinstance(p, dict) else p
                 for p in content_by_ds[dspath]],
                message=message,
                version_tag=version_tag)
            if saved_state:
                res['status'] = 'ok'
            else:
                res['status'] = 'notneeded'
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
