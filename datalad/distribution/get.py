# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for getting dataset content

"""

import logging

from os import curdir
from os.path import isdir, join as opj, relpath

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_get_opts
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandNotAvailableError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileNotInRepositoryError

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import require_dataset
from .dataset import resolve_path
from .dataset import _with_sep

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


class Get(Interface):
    """Get data content for files and/or directories of a dataset.

    Known data locations for each requested file are evaluated and data are
    obtained from the best/fastest/cheapest location, unless a dedicated
    source is identified.

    By default this command operates recursively within a dataset, but not
    across potential subdatasets, i.e. if a directory is provided, all files in
    the directory are obtained. Recursion into subdatasets is supported too. If
    enabled, potential subdatasets are detected and installed sequentially, in
    order to fulfill a request.

    .. note::
      Power-user info: This command used :command:`git annex get` to fulfill
      requests. Subdatasets are obtained via the :func:`~datalad.api.install`
      command.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="PATH",
            doc="""specify the dataset to perform the add operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path/name of the requested dataset component. The component
            must already be known to the dataset.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar="LABEL",
            doc="""label of the data source to be used to fulfill the request.
            This can be the name of a dataset :term:`sibling` or another known
            source""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_get_opts=annex_get_opts)

    @staticmethod
    @datasetmethod(name='get')
    def __call__(
            path=None,
            source=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_get_opts=None):

        # resolve dataset:
        ds = require_dataset(dataset, check_installed=True,
                             purpose='getting content')

        # check parameters:
        if path is None:
            raise InsufficientArgumentsError("insufficient information for "
                                             "getting: requires at least a "
                                             "path.")
        # When called from cmdline `path` will be a list even if
        # there is only one item.
        # Make sure we deal with the same when called via python API:
        if not isinstance(path, list):
            path = [path]

        # resolve path(s):
        resolved_paths = [resolve_path(p, dataset) for p in path]

        # resolve associated datasets:
        resolved_datasets = dict()
        for p in resolved_paths:
            p_ds = ds.get_containing_subdataset(p,
                                                recursion_limit=recursion_limit)
            if p_ds is None:
                raise FileNotInRepositoryError(
                    msg="{0} not in dataset.".format(p))
            if not recursive and p_ds != ds:
                raise FileNotInRepositoryError(
                    msg="{0} belongs to subdataset {1}. To get its content use "
                        "option `recursive` or call get on the "
                        "subdataset.".format(p, p_ds))
            resolved_datasets[p_ds.path] = \
                resolved_datasets.get(p_ds.path, []) + [p]

            # TODO: Change behaviour of Dataset: Make subdatasets singletons to
            # always get the same object referencing a certain subdataset.

        if recursive:
            # Find implicit subdatasets to call get on:
            # If there are directories in resolved_paths (Note,
            # that this includes '.' and '..'), check for subdatasets
            # beneath them. These should be called recursively with '.'.
            # Therefore add the subdatasets to resolved_datasets and
            # corresponding '.' to resolved_paths, in order to generate the
            # correct call.
            for p in resolved_paths:
                if isdir(p):
                    for subds_path in \
                      ds.get_subdatasets(absolute=True, recursive=True,
                                         recursion_limit=recursion_limit):
                        if subds_path.startswith(_with_sep(p)):
                            if subds_path not in resolved_datasets:
                                resolved_datasets[subds_path] = []
                            resolved_datasets[subds_path].append(curdir)

        # the actual calls:
        global_results = []
        for ds_path in resolved_datasets:
            cur_ds = Dataset(ds_path)
            # needs to be an annex:
            if not isinstance(cur_ds.repo, AnnexRepo):
                raise CommandNotAvailableError(
                    cmd="get", msg="Missing annex at {0}".format(ds))

            local_results = cur_ds.repo.get(resolved_datasets[ds_path],
                                            options=['--from="%s"' % source]
                                                    if source else [])

            # if we recurse into subdatasets, adapt relative paths reported by
            # annex to be relative to the toplevel dataset we operate on:
            if recursive:
                for i in range(len(local_results)):
                    local_results[i]['file'] = \
                        relpath(opj(ds_path, local_results[i]['file']), ds.path)

            global_results.extend(local_results)
        return global_results

    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        from os import linesep
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Nothing was added")
            return

        msg = linesep.join([
            "{path} ... {suc}".format(
                suc="ok." if item.get('success', False)
                    else "failed.",
                path=item.get('file'))
            for item in res])
        ui.message(msg)

