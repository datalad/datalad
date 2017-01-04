# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding dataset components

"""

import logging

from os import curdir
from os.path import isdir
from os.path import join as opj
from os.path import relpath
from collections import defaultdict

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_add_opts
from datalad.interface.common_opts import jobs_opt
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import sort_paths_into_subdatasets
from datalad.interface.utils import amend_pathspec_with_superdatasets
from datalad.distribution.utils import _install_subds_inplace
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.network import is_datalad_compat_ri
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep

from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import Dataset
from .dataset import resolve_path
from .dataset import require_dataset
from .install import _get_git_url_from_source


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.add')


class Add(Interface):
    """Add files/directories to an existing dataset.

    Typically, files and directories to be added to a dataset would be placed
    into a directory of a dataset, and subsequently this command can be used to
    register this new content with the dataset. With recursion enabled,
    files will be added to their respective subdatasets as well.

    || REFLOW >>
    By default all files are added to the dataset's :term:`annex`, i.e. only
    their content identity and availability information is tracked with Git.
    This results in lightweight datasets. If desired, the [PY: `to_git`
    PY][CMD: --to-git CMD] flag can be used to tell datalad to inject files
    directly into Git. While this is not recommended for binary data or large
    files, it can be used for source code and meta-data to be able to benefit
    from Git's track and merge capabilities. Files checked directly into Git
    are always and unconditionally available immediately after installation of
    a dataset.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git annex add`, or
      :command:`git add` to incorporate new dataset content.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='PATH',
            doc="""specify the dataset to perform the add operation on.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory and/or the `path` given""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name of the component to be added. The component
            must either exist on the filesystem already, or a `source`
            has to be provided.""",
            nargs="+",
            constraints=EnsureStr() | EnsureNone()),
        to_git=Parameter(
            args=("--to-git",),
            action='store_true',
            doc="""flag whether to add data directly to Git, instead of
            tracking data identity only.  Usually this is not desired,
            as it inflates dataset sizes and impacts flexibility of data
            transport"""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        save=nosave_opt,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_add_opts=annex_add_opts,
        jobs=jobs_opt
    )

    @staticmethod
    @datasetmethod(name='add')
    def __call__(
            path=None,
            dataset=None,
            to_git=False,
            save=True,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None,
            jobs=None):

        # parameter constraints:
        if not path:
            raise InsufficientArgumentsError(
                "insufficient information for adding: requires at least a path")
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit)
        if unavailable_paths:
            lgr.warning("ignoring non-existent path(s): %s",
                        unavailable_paths)
        if not content_by_ds:
            raise InsufficientArgumentsError(
                "no existing content given to add")

        # TODO with --recursive for each input path traverse the directory
        # tree until the end or until we hit a known dataset
        # when we find an unknown dataset, add it to the spec, AND add it as
        # a path to the spec of the parent

        if dataset:
            # we have a base dataset, so make sure that any added content will
            # be directly or indirectly (via intermediate subdatasets) linked
            # to it
            content_by_ds = amend_pathspec_with_superdatasets(
                content_by_ds,
                topmost=dataset,
                limit_single=True)
            # forge chain from base dataset to any leaf dataset
            sort_paths_into_subdatasets(
                dataset.path,
                content_by_ds.keys(),
                content_by_ds)

        results = []
        # simple loop over datasets -- save happens later
        # start deep down
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            toadd = content_by_ds[ds_path]
            # handle anything that looks like a wannabe subdataset
            for subds_path in [d for d in toadd
                               if GitRepo.is_valid_repo(d) and
                               d != ds_path and
                               d not in ds.get_subdatasets(
                                   recursive=False,
                                   absolute=True,
                                   fulfilled=True)]:
                _install_subds_inplace(
                    ds=ds,
                    path=subds_path,
                    relativepath=relpath(subds_path, ds_path))
                # make sure that .gitmodules is added to the list of files
                toadd.append(opj(ds.path, '.gitmodules'))
            added = ds.repo.add(
                toadd,
                git=to_git if isinstance(ds.repo, AnnexRepo) else True,
                commit=False)
            for a in added:
                a['file'] = opj(ds_path, a['file'])
            results.extend(added)

        if save:
            save_dataset_hierarchy(
                content_by_ds,
                base=dataset.path if dataset and dataset.is_installed() else None,
                message='[DATALAD] added content')

        return results

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
            "{suc} {path}".format(
                suc="Added" if item.get('success', False)
                    else "Failed to add. (%s)" % item.get('note',
                                                          'unknown reason'),
                path=item.get('file'))
            for item in res])
        ui.message(msg)
