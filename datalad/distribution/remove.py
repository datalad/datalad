# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for removing dataset content

"""

__docformat__ = 'restructuredtext'

import os
import logging

from os.path import exists
from os.path import relpath
from os.path import join as opj
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import Dataset, \
    datasetmethod, require_dataset
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.utils import handle_dirty_datasets
from datalad.interface.utils import path_is_under
from datalad.interface.utils import discover_dataset_trace_to_targets
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.interface.save import Save
from datalad.utils import get_dataset_root
from datalad.distribution.drop import _drop_files
from datalad.distribution.drop import dataset_argument
from datalad.distribution.drop import check_argument
from datalad.distribution.uninstall import _uninstall_dataset


lgr = logging.getLogger('datalad.distribution.remove')


@build_doc
class Remove(Interface):
    """Remove components from datasets

    This command can remove any components (subdatasets, and (directories with)
    files) from datasets. Removing a component implies any present content to
    be dropped, and any associated subdatasets to be uninstalled. Subsequently,
    the component is "unregistered" from the respective dataset. This means
    that the respective component is no longer present on the file system.

    By default, the availability of at least one remote copy is verified, by
    default, before file content is dropped. As these checks could lead to slow
    operation (network latencies, etc), they can be disabled.

    Any number of paths to process can be given as input. Recursion into
    subdatasets needs to be explicitly enabled, while recursion in
    subdirectories within a dataset as always done automatically. An optional
    recursion limit is applied relative to each given input path.

    Examples
    --------

    Permanently remove a subdataset from a dataset and wipe out the subdataset
    association too::

      ~/some/dataset$ datalad remove somesubdataset1
    """
    _action = 'remove'

    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be removed",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        check=check_argument,
        if_dirty=if_dirty_opt,
    )

    @staticmethod
    @datasetmethod(name=_action)
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            if_dirty='save-before'):
        res_kwargs = dict(action='remove', logger=lgr)
        if not dataset and not path:
            raise InsufficientArgumentsError(
                "insufficient information for `remove`: requires at least a path or dataset")
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs['refds'] = refds_path
        if refds_path and not path and not GitRepo.is_valid_repo(refds_path):
            # nothing here, nothing to remove
            yield get_status_dict(path=refds_path, status='notneeded', **res_kwargs)
            return
        if refds_path and not path:
            # act on the whole dataset if nothing else was specified
            # TODO i think that would happen automatically in annotation?
            path = refds_path

        to_process = []

        for ap in AnnotatePaths.__call__(
                path=path,
                dataset=refds_path,
                recursive=recursive,
                # we only ever want to discover immediate subdatasets, the rest
                # will happen in `uninstall`
                recursion_limit=1,
                action='remove',
                unavailable_path_status='',
                nondataset_path_status='error',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('state', None) == 'absent' and \
                    ap.get('parentds', None) is None:
                # nothing exists at location, and there is no parent to
                # remove from
                ap['status'] = 'notneeded'
                ap['message'] = "path does not exist and is not in a dataset"
                yield ap
                continue
            to_process.append(ap)

        if not to_process:
            # nothing left to do, potentially all errored before
            return

        if path_is_under([ap['path'] for ap in to_process]):
            # behave like `rm` and refuse to remove where we are
            raise ValueError(
                "refusing to uninstall current or parent directory")

        # now sort into datasets so we can process them one by one
        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        # iterate over all datasets, starting at the bottom
        # to make the removal of dataset content known upstairs
        to_save = []
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            to_reporemove = []
            # PLAN any dataset that was not raw_input, uninstall (passing recursive flag)
            # if dataset itself is in paths, skip any nondataset
            # sort reverse so we get subdatasets first
            for ap in sorted(paths, key=lambda x: x ['path'], reverse=True):
                if ap.get('type', None) == 'dataset':
                    # entire dataset needs to go, uninstall if present, pass recursive!
                    uninstall_failed = False
                    if ap['path'] != ds_path and ap.get('state', None) != 'absent':
                        # anything that is not the top-level -> regular uninstall
                        for r in ds.uninstall(
                                # TODO pass annotated path when receiver is ready
                                ap['path'], recursive=recursive, check=check,
                                if_dirty=if_dirty, result_xfm=None, result_filter=None,
                                on_failure='ignore'):
                            if r['status'] in ('impossible', 'error'):
                                # we need to inspect if something went wrong, in order
                                # to prevent failure from removing a non-empty dir below,
                                # but at the same time allow for continued processing
                                uninstall_failed = True
                            yield r
                    if ap['path'] == ds_path:
                        # this is the top-level, "I know what I am doing"-uninstall
                        for r in _uninstall_dataset(ds, check=check, has_super=False,
                                                    **res_kwargs):
                            if r['status'] in ('impossible', 'error'):
                                # we need to inspect if something went wrong, in order
                                # to prevent failure from removing a non-empty dir below,
                                # but at the same time allow for continued processing
                                uninstall_failed = True
                            yield r
                    if not ap.get('raw_input', False):
                        # we only ever want to actually unregister subdatasets that
                        # were given explicitly
                        continue
                    if not uninstall_failed and ap.get('registered_subds', False):
                        # strip from superdataset
                        assert(ap['parentds'] == ds_path)
                        subds_relpath = relpath(ap['path'], start=ap['parentds'])
                        # remove submodule reference
                        submodule = [sm for sm in ds.repo.repo.submodules
                                     if sm.path == subds_relpath]
                        # there can only be one!
                        # TODO have a test for #1526
                        assert len(submodule) == 1, \
                            "Found multiple subdatasets with registered path {}:" \
                            "{}{}{}There should be only one." \
                            "".format(subds_relpath, os.linesep,
                                      submodule, os.linesep)
                        submodule = submodule[0]
                        submodule.remove()
                        yield dict(ap, status='ok', **res_kwargs)
                        # need .gitmodules update in parent
                        to_save.append(dict(
                            path=opj(ds.path, '.gitmodules'),
                            parents=ds.path,
                            type='file'))
                        # and the removal itself needs to be committed
                        # inform `save` that it is OK that this path
                        # doesn't exist on the filesystem anymore
                        ap['unavailable_path_status'] = ''
                        to_save.append(ap)
                    if not uninstall_failed and exists(ap['path']):
                        # could be an empty dir in case an already uninstalled subdataset
                        # got removed
                        os.rmdir(ap['path'])
                else:
                    # anything that is not a dataset can simply be passed on
                    to_reporemove.append(ap['path'])
            # avoid unnecessary git calls when there is nothing to do
            if to_reporemove:
                if check and hasattr(ds.repo, 'drop'):
                    for r in _drop_files(ds, to_reporemove, check=True):
                        yield r
                for r in ds.repo.remove(to_reporemove, r=True):
                    # these were removed, but we still need to save the removal
                    ap['unavailable_path_status'] = ''
                    to_save.append(ap)
                    yield get_status_dict(
                        status='ok',
                        path=r,
                        **res_kwargs)

        if not to_save:
            # nothing left to do, potentially all errored before
            return

        for res in Save.__call__(
                # TODO compose hand-selected annotated paths
                files=to_save,
                dataset=refds_path,
                # TODO allow for custom message
                #message=message if message else '[DATALAD] removed content',
                message='[DATALAD] removed content',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
