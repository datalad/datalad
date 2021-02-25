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
from os.path import pardir
from os.path import join as opj
from datalad.utils import rmdir
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import Dataset, \
    datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import save_message_opt
from datalad.interface.utils import path_is_under
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.core.local.save import Save
from datalad.distribution.drop import _drop_files
from datalad.distribution.drop import dataset_argument
from datalad.distribution.drop import check_argument
from datalad.distribution.uninstall import _uninstall_dataset
from datalad.distribution.uninstall import Uninstall


lgr = logging.getLogger('datalad.distribution.remove')


@build_doc
class Remove(Interface):
    """Remove components from datasets

    This command can remove subdatasets and paths, including non-empty
    directories, from datasets. Removing a component implies dropping present
    content and uninstalling associated subdatasets. Subsequently, the
    component is "unregistered" from the respective dataset. This means that
    the component is no longer present on the file system.

    By default, the availability of at least one remote copy is verified before
    file content is dropped. As these checks could lead to slow operation
    (network latencies, etc), they can be disabled.

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
        save=nosave_opt,
        message=save_message_opt,
        if_dirty=if_dirty_opt,
    )

    _examples_ = [
        dict(text="Permanently remove a subdataset from a dataset and wipe out "
                  "the subdataset association too",
             code_py="remove(dataset='path/to/dataset', path='path/to/subds')",
             code_cmd="datalad remove -d <path/to/dataset> <path/to/subds>"),
        dict(text="Permanently remove a dataset and all subdatasets",
             code_py="remove(dataset='path/to/dataset', recursive=True)",
             code_cmd="datalad remove -d <path/to/dataset/> -r"),
        dict(text="Permanently remove a dataset and all subdatasets even if there "
                  "are fewer than the configured minimum number of (remote) sources "
                  "for data",
             code_py="remove(dataset='path/to/dataset', recursive=True, check=False)",
             code_cmd="datalad remove -d <path/to/dataset/> -r --nocheck"),
    ]

    @staticmethod
    @datasetmethod(name=_action)
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            check=True,
            save=True,
            message=None,
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
                return_type='generator',
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
            if ap.get('raw_input', False) and ap.get('type', None) == 'dataset':
                # make sure dataset sorting yields a dedicted entry for this one
                ap['process_content'] = True
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
                refds_path=refds_path)
        assert(not completed)

        # iterate over all datasets, starting at the bottom
        # to make the removal of dataset content known upstairs
        to_save = []
        # track which submodules we have removed in the process, to avoid
        # failure in case we revisit them due to a subsequent path argument
        subm_removed = []
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            to_reporemove = dict()
            # PLAN any dataset that was not raw_input, uninstall (passing recursive flag)
            # if dataset itself is in paths, skip any nondataset
            # sort reverse so we get subdatasets first
            for ap in sorted(paths, key=lambda x: x['path'], reverse=True):
                if ap.get('type', None) == 'dataset':
                    # entire dataset needs to go, uninstall if present, pass recursive!
                    uninstall_failed = False
                    if ap['path'] == refds_path or \
                            (refds_path is None and ap.get('raw_input', False)):
                        # top-level handling, cannot use regular uninstall call, as
                        # it will refuse to uninstall a top-level dataset
                        # and rightfully so, it is really a remove in that case
                        # bypass all the safety by using low-level helper
                        for r in _uninstall_dataset(ds, check=check, has_super=False,
                                                    **res_kwargs):
                            if r['status'] in ('impossible', 'error'):
                                # we need to inspect if something went wrong, in order
                                # to prevent failure from removing a non-empty dir below,
                                # but at the same time allow for continued processing
                                uninstall_failed = True
                            r['refds'] = refds_path
                            yield r
                    # recheck that it wasn't removed during a previous iteration
                    elif ap.get('state', None) != 'absent' and GitRepo.is_valid_repo(ap['path']):
                        # anything that is not the top-level -> regular uninstall
                        # this is for subdatasets of the to-be-removed dataset
                        # we want to simply uninstall them in a regular manner
                        for r in Uninstall.__call__(
                                ap['path'],
                                dataset=refds_path, recursive=recursive, check=check,
                                if_dirty=if_dirty, result_xfm=None, result_filter=None,
                                on_failure='ignore'):
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
                    if not uninstall_failed and \
                            not ap['path'] in subm_removed and \
                            refds_path and \
                            ap.get('parentds', None) and \
                            not (relpath(ap['path'], start=refds_path).startswith(pardir) or
                                 ap['path'] == refds_path) and \
                            ap.get('registered_subds', False):
                        # strip from superdataset, but only if a dataset was given explcitly
                        # as in "remove from this dataset", but not when just a path was given
                        # as in "remove from the filesystem"
                        subds_relpath = relpath(ap['path'], start=ap['parentds'])
                        # remove submodule reference
                        parentds = Dataset(ap['parentds'])
                        # play safe, will fail on dirty
                        parentds.repo.deinit_submodule(ap['path'])
                        # remove now empty submodule link
                        parentds.repo.remove(ap['path'])
                        # make a record that we removed this already, should it be
                        # revisited via another path argument, because do not reannotate
                        # the paths after every removal
                        subm_removed.append(ap['path'])
                        yield dict(ap, status='ok', **res_kwargs)
                        # need .gitmodules update in parent
                        to_save.append(dict(
                            path=opj(parentds.path, '.gitmodules'),
                            parents=parentds.path,
                            type='file'))
                        # and the removal itself needs to be committed
                        # inform `save` that it is OK that this path
                        # doesn't exist on the filesystem anymore
                        ap['unavailable_path_status'] = ''
                        ap['process_content'] = False
                        to_save.append(ap)
                    if not uninstall_failed and exists(ap['path']):
                        # could be an empty dir in case an already uninstalled subdataset
                        # got removed
                        rmdir(ap['path'])
                else:
                    # anything that is not a dataset can simply be passed on
                    to_reporemove[ap['path']] = ap
            # avoid unnecessary git calls when there is nothing to do
            if to_reporemove:
                if check and hasattr(ds.repo, 'drop'):
                    for r in _drop_files(ds, list(to_reporemove),
                                         check=True):
                        if r['status'] == 'error':
                            # if drop errored on that path, we can't remove it
                            to_reporemove.pop(r['path'], 'avoidKeyError')
                        yield r

                if to_reporemove:
                    for r in ds.repo.remove(list(to_reporemove), r=True):
                        # these were removed, but we still need to save the
                        # removal

                        r_abs = opj(ds.path, r)
                        if r_abs in to_reporemove:
                            ap = to_reporemove[r_abs]
                        else:
                            ap = {'path': r_abs,
                                  'parentds': ds.path,
                                  'refds': refds_path
                                  }
                        ap['unavailable_path_status'] = ''
                        to_save.append(ap)
                        yield get_status_dict(
                            status='ok',
                            path=r,
                            **res_kwargs)

        if not to_save:
            # nothing left to do, potentially all errored before
            return
        if not save:
            lgr.debug('Not calling `save` as instructed')
            return

        for res in Save.__call__(
                path=[ap["path"] for ap in to_save],
                # we might have removed the reference dataset by now, recheck
                dataset=refds_path
                        if (refds_path and GitRepo.is_valid_repo(refds_path))
                        else None,
                message=message if message else '[DATALAD] removed content',
                return_type='generator',
                result_xfm=None,
                result_filter=None,
                on_failure='ignore'):
            yield res
