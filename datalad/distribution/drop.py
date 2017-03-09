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
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.distribution.dataset import Dataset, EnsureDataset, \
    datasetmethod
from datalad.interface.base import Interface
from datalad.interface.base import report_result_objects
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.interface.utils import handle_dirty_datasets
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


res_kwargs = dict(action='drop', logger=lgr)


def _drop_files(ds, files, check):
    if not hasattr(ds.repo, 'drop'):
        msg = 'no annex in dataset'
        for f in files:
            yield get_status_dict(
                status='impossible', path=f, message=msg, **res_kwargs)
        return

    opts = ['--force'] if not check else []
    # TODO capture for which files it fails and report them properly
    # not embedded in a command error
    for f in ds.repo.drop(files, options=opts):
        yield get_status_dict(
            status='ok', path=opj(ds.path, f), **res_kwargs)


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

        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit)
        for r in results_from_paths(
                unavailable_paths, status='impossible',
                message="path does not exist: %s",
                **res_kwargs):
            yield r
        # TODO generator
        # this should yield what it did
        handle_dirty_datasets(
            content_by_ds.keys(), mode=if_dirty, base=dataset)

        # iterate over all datasets, order doesn't matter
        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            paths = content_by_ds[ds_path]
            for r in _drop_files(ds, paths, check=check):
                yield r
        # there is nothing to save at the end
