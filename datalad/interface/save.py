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
from os.path import relpath
from os.path import lexists


from datalad.utils import unique
from datalad.support.annexrepo import AnnexRepo
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

from .base import Interface

lgr = logging.getLogger('datalad.interface.save')


def save_dataset(
        ds,
        paths,
        message=None,
        version_tag=None):
    """Save changes in a single dataset.

    Parameters
    ----------
    ds : Dataset
      The dataset to be saved.
    paths : list
      Annotated paths to dataset components to be saved.
    message: str, optional
      (Commit) message to be attached to the saved state.
    version_tag : str, optional
      Tag to be assigned to the saved state.

    Returns
    -------
    bool
      Whether a new state was saved. If all to be saved content was unmodified
      no new state will be saved.
    """
    # XXX paths must be in the given ds, no further sanity checks!

    # make sure that all pending changes (batched annex operations, etc.)
    # are actually reflected in Git
    ds.repo.precommit()

    # track what is to be committed, so it becomes
    # possible to decide when/what to save further down
    # and one level up
    orig_hexsha = ds.repo.get_hexsha()

    # check whether we want to commit anything staged, or individual pieces
    # this is independent of actually staging individual bits
    save_entire_ds = False
    for ap in paths:
        if ap['path'] == ds.path:
            save_entire_ds = True
            break

    # asking yourself why we need to `add` at all? For example, freshly
    # unlocked files in a v5 repo are listed as "typechange" and commit
    # refuses to touch them without an explicit `add`
    to_gitadd = [ap['path'] for ap in paths
                 # if not flagged as staged
                 if not ap.get('staged', False) and
                 # must exist, anything else needs no staging, can be committed directly
                 lexists(ap['path']) and
                 # not an annex repo, hence no choice other than git
                 (not isinstance(ds.repo, AnnexRepo) or
                  # even in an annex repo we want to use `git add` for submodules
                  (ap.get('type', None) == 'dataset' and not ap['path'] == ds.path))]
    to_annexadd = [ap['path'] for ap in paths
                   # not passed to git add
                   if ap['path'] not in to_gitadd and
                   # if not flagged as staged
                   not ap.get('staged', False) and
                   # prevent `git annex add .` in a subdataset, if not desired
                   not ap.get('process_updated_only', False) and
                   # must exist, anything else needs no staging, can be committed directly
                   lexists(ap['path'])]

    if to_gitadd or save_entire_ds:
        ds.repo.add(to_gitadd, git=True, commit=False,
                    # this makes sure that pending submodule updates are added too
                    update=save_entire_ds)
    if to_annexadd:
        ds.repo.add(to_annexadd, commit=False)

    _datalad_msg = False
    if not message:
        message = 'Recorded existing changes'
        _datalad_msg = True

    # we will blindly call commit not knowing if there is anything to
    # commit -- this is cheaper than to anticipate all possible ways
    # a repo in whatever mode is dirty
    ds.repo.commit(
        message,
        files=[ap['path'] for ap in paths] if not save_entire_ds else None,
        _datalad_msg=_datalad_msg,
        careless=True)

    # MIH: let's tag even if there was nothing commit. I'd forget this
    # option too often...
    if version_tag:
        ds.repo.tag(version_tag)

    _was_modified = ds.repo.get_hexsha() != orig_hexsha
    return ds.repo.repo.head.commit if _was_modified else None


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
            doc="""if no explicit paths are given, save changes of all known
            components in a datasets""",
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
                 all_updated=True, all_changes=None, version_tag=None,
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
        refds_path = Interface.get_refds_path(dataset)

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
                return_type='generator',
                on_failure='ignore'):
            # next check should not be done during annotation, as it is possibly expensive
            # and not generally useful
            if ap.get('status', None) == 'impossible' and \
                    ap.get('state', None) == 'absent' and \
                    ap.get('parentds', None):
                # this is not here anymore, but it might actually have been a deleted
                # component
                if relpath(ap['path'], start=ap['parentds']) \
                        in Dataset(ap['parentds']).repo.get_deleted_files():
                    # ok, this is a staged deletion that we want to save
                    ap['status'] = ''
                    del ap['message']
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            # for things like: `ds.save()`
            # or recursively discovered datasets
            if ap['path'] == refds_path or \
                    (ap.get('type', None) == 'dataset' and
                     not ap.get('raw_input', False) and
                     not ap.get('state', None) == 'absent'):
                ap['process_content'] = True
                ap['process_updated_only'] = all_updated
            to_process.append(ap)

        if not to_process:
            # nothing left to do, potentially all errored before
            return

        if super_datasets:
            # search for the topmost superdatasets of any path
            dss = [Dataset(ap.get('parentds', ap['path'])) for ap in to_process]
            superdss = [ds.get_superdataset(topmost=True)
                        for ds in dss]
            superdss = get_tree_roots(
                unique(ds.path for ds in dss + superdss if ds))
            if dataset:
                # need to adjust the reference to the new superds
                # if we had one ref before, we should still have exactly one
                assert len(superdss) <= 1
                dataset = list(superdss.keys())[0]
                refds_path = dataset
        elif refds_path:
            # there is a single superdataset
            superdss = {
                refds_path: unique([ap['parentds']
                                    for ap in to_process if 'parentds' in ap])}
        else:
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
        # if this is called from e.g. `add` this is actually not necessary,
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
        discovered_added = set()
        for parentds in discovered:
            for subds in discovered[parentds]:
                to_process.append(dict(
                    path=subds,
                    parentds=parentds,
                    type='dataset'))
                discovered_added.add(subds)
        # make sure we have an entry for each dataset, including those
        # tha are just parents
        for parentds in discovered:
            if parentds not in discovered_added:
                to_process.append(dict(
                    path=parentds,
                    type='dataset',
                    # make sure we save content of superds later on
                    process_content=True))

        # now re-annotate all paths, this will be fast for already annotated ones
        # and will amend the annotation for others, deduplication happens here too
        annotated_paths = AnnotatePaths.__call__(
            path=to_process,
            dataset=dataset,
            # never recursion, done already
            recursive=False,
            action='save',
            unavailable_path_status='',
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
                content_by_ds[dspath],
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
