# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dropping dataset content

"""

__docformat__ = 'restructuredtext'

import logging

from os.path import join as opj
from os.path import isabs
from os.path import normpath

from datalad.utils import assure_list
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.gitrepo import GitRepo
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.results import get_status_dict
from datalad.interface.results import annexjson2result
from datalad.interface.results import success_status_map
from datalad.interface.results import results_from_annex_noinfo
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc

lgr = logging.getLogger('datalad.distribution.drop')

dataset_argument = Parameter(
    args=("-d", "--dataset"),
    metavar="DATASET",
    doc="""specify the dataset to perform the operation on.
    If no dataset is given, an attempt is made to identify a dataset
    based on the `path` given""",
    constraints=EnsureDataset() | EnsureNone())


check_argument = Parameter(
    args=("--nocheck",),
    doc="""whether to perform checks to assure the configured minimum
    number (remote) source for data.[CMD:  Give this
    option to skip checks CMD]""",
    action="store_false",
    dest='check')


def _drop_files(ds, paths, check, noannex_iserror=False, **kwargs):
    """Helper to drop content in datasets.

    Parameters
    ----------
    ds : Dataset
    paths : path or list(path)
      which content to drop
    check : bool
      whether to instruct annex to perform minimum copy availability
      checks
    noannex_iserror : bool
      whether calling this function on a pur Git repo results in an
      'impossible' or 'notneeded' result.
    **kwargs
      additional payload for the result dicts
    """
    if 'action' not in kwargs:
        kwargs['action'] = 'drop'
    # always need to make sure that we pass a list
    # `normalize_paths` decorator will otherwise screw all logic below
    paths = assure_list(paths)
    if not hasattr(ds.repo, 'drop'):
        for p in paths:
            r = get_status_dict(
                status='impossible' if noannex_iserror else 'notneeded',
                path=p if isabs(p) else normpath(opj(ds.path, p)),
                message="no annex'ed content",
                **kwargs)
            r['action'] = 'drop'
            yield r
        return

    opts = ['--force'] if not check else []
    respath_by_status = {}
    for res in ds.repo.drop(paths, options=opts):
        res = annexjson2result(
            # annex reports are always about files
            res, ds, type='file', **kwargs)
        success = success_status_map[res['status']]
        respath_by_status[success] = \
            respath_by_status.get(success, []) + [res['path']]
        yield res
    # report on things requested that annex was silent about
    for r in results_from_annex_noinfo(
            ds, paths, respath_by_status,
            dir_fail_msg='could not drop some content in %s %s',
            noinfo_dir_msg='nothing to drop from %s',
            noinfo_file_msg="no annex'ed content",
            **kwargs):
        r['action'] = 'drop'
        yield r


@build_doc
class Drop(Interface):
    """Drop file content from datasets

    This command takes any number of paths of files and/or directories. If
    a common (super)dataset is given explicitly, the given paths are
    interpreted relative to this dataset.

    Recursion into subdatasets needs to be explicitly enabled, while recursion
    in subdirectories within a dataset as always done automatically. An
    optional recursion limit is applied relative to each given input path.

    By default, the availability of at least one remote copy is verified,
    before file content is dropped. As these checks could lead to slow
    operation (network latencies, etc), they can be disabled.


    Examples
    --------

    Drop all file content in a dataset::

      ~/some/dataset$ datalad drop

    Drop all file content in a dataset and all its subdatasets::

      ~/some/dataset$ datalad drop --recursive

    """
    _action = 'drop'

    _params_ = dict(
        dataset=dataset_argument,
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path/name of the component to be dropped",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
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
            recursion_limit=None,
            check=True,
            if_dirty='save-before'):

        if not dataset and not path:
            raise InsufficientArgumentsError(
                "insufficient information for `drop`: requires at least a path or dataset")
        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(action='drop', logger=lgr, refds=refds_path)
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path
        to_drop = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='drop',
                # justification for status:
                # content need not be dropped where there is none
                unavailable_path_status='notneeded',
                nondataset_path_status='error',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if ap.get('type', None) == 'dataset' and \
                    GitRepo.is_valid_repo(ap['path']) and \
                    not ap['path'] == refds_path:
                ap['process_content'] = True
            to_drop.append(ap)

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_drop,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        # iterate over all datasets, order doesn't matter
        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            # TODO generator
            # this should yield what it did
            handle_dirty_dataset(ds, mode=if_dirty)
            # ignore submodule entries
            content = [ap['path'] for ap in content_by_ds[ds_path]
                       if ap.get('type', None) != 'dataset' or ap['path'] == ds.path]
            if not content:
                continue
            for r in _drop_files(ds, content, check=check, **res_kwargs):
                yield r
        # there is nothing to save at the end
