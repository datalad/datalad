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

from os import listdir
from os.path import isdir
from os.path import join as opj
from os.path import relpath

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import save_message_opt
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_add_opts
from datalad.interface.common_opts import jobs_opt
from datalad.interface.utils import save_dataset_hierarchy
from datalad.interface.utils import _discover_trace_to_known
from datalad.distribution.utils import _install_subds_inplace
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError

from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import Dataset


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.add')


def _discover_subdatasets_recursively(top, trace, spec, recursion_limit):
    # this beast walks the directory tree from a give `top` directory
    # and discovers valid repos that are scattered around, regardless
    # of whether they are already subdatasets or not
    # for all found datasets it puts an entry into the SPEC and also
    # and entry with the path in the SPEC of the parent dataset
    if recursion_limit is not None and len(trace) > recursion_limit:
        return
    if not isdir(top):
        return
    if GitRepo.is_valid_repo(top):
        # found a repo, add the entire thing
        spec[top] = spec.get(top, []) + [top]
        # and to the parent
        if trace:
            spec[trace[-1]] = spec.get(trace[-1], []) + [top]
        trace = trace + [top]
    for path in listdir(top):
        path = opj(top, path)
        if not isdir(path):
            continue
        _discover_subdatasets_recursively(path, trace, spec, recursion_limit)


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
        ds2super=Parameter(
            args=("-S", "--ds2super", "--datasets-to-super",),
            action='store_true',
            doc="""given paths of dataset (toplevel) locations will cause
            these datasets to be added to their respective superdatasets
            underneath a given base `dataset` (instead of all their content
            to themselves). If no base `dataset` is provided, this flag has
            no effect. Regular files and directories are always added to
            their respective datasets, regardless of this setting."""),
        save=nosave_opt,
        message=save_message_opt,
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
            message=None,
            recursive=False,
            recursion_limit=None,
            ds2super=False,
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None,
            jobs=None):

        # parameter constraints:
        if not path:
            raise InsufficientArgumentsError(
                "insufficient information for adding: requires at least a path")
        # never recursion, need to handle manually below to be able to
        # discover untracked content
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=False)
        if unavailable_paths:
            lgr.warning("ignoring non-existent path(s): %s",
                        unavailable_paths)
        if recursive:
            # with --recursive for each input path traverse the directory
            # tree, when we find a dataset, add it to the spec, AND add it as
            # a path to the spec of the parent
            # MIH: wrap in list() to avoid exception, because dict size might
            # change, but we want to loop over all that are in at the start
            # only
            for d in list(content_by_ds.keys()):
                for p in content_by_ds[d]:
                    _discover_subdatasets_recursively(
                        p,
                        [d],
                        content_by_ds,
                        recursion_limit)

        if not content_by_ds:
            raise InsufficientArgumentsError(
                "non-existing paths given to add")

        if dataset:
            # remeber the datasets associated with actual inputs
            input_ds = list(content_by_ds.keys())
            # forge chain from base dataset to any leaf dataset
            _discover_trace_to_known(dataset.path, [], content_by_ds)
            if ds2super:
                # now check all dataset entries corresponding to the original
                # input to see if they contain their own paths and remove them
                for inpds in input_ds:
                    content_by_ds[inpds] = [p for p in content_by_ds[inpds]
                                            if not p == inpds]
                # and lastly remove all entries that contain no path to avoid
                # saving any staged content in the final step
                content_by_ds = {d: v for d, v in content_by_ds.items() if v}

        results = []
        # simple loop over datasets -- save happens later
        # start deep down
        for ds_path in sorted(content_by_ds, reverse=True):
            ds = Dataset(ds_path)
            toadd = list(set(content_by_ds[ds_path]))
            # handle anything that looks like a wannabe subdataset
            for subds_path in [d for d in toadd
                               if GitRepo.is_valid_repo(d) and
                               d != ds_path and
                               d not in ds.get_subdatasets(
                                   recursive=False,
                                   absolute=True,
                                   fulfilled=True)]:
                # TODO add check that the subds has a commit, and refuse
                # to operate on it otherwise, or we would get a bastard
                # submodule that cripples git operations
                _install_subds_inplace(
                    ds=ds,
                    path=subds_path,
                    relativepath=relpath(subds_path, ds_path))
                # make sure that .gitmodules is added to the list of files
                toadd.append(opj(ds.path, '.gitmodules'))
                # report added subdatasets -- add below won't do it
                results.append({
                    'success': True,
                    'file': Dataset(subds_path)})
            # make sure any last minute additions make it to the saving stage
            content_by_ds[ds_path] = toadd
            added = ds.repo.add(
                toadd,
                git=to_git if isinstance(ds.repo, AnnexRepo) else True,
                commit=False)
            for a in added:
                a['file'] = opj(ds_path, a['file'])
            results.extend(added)

        if results and save:
            save_dataset_hierarchy(
                content_by_ds,
                base=dataset.path if dataset and dataset.is_installed() else None,
                message=message if message else '[DATALAD] added content')

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
            ui.message("Nothing was added{}".format(
                       '' if args.recursive else
                       " (consider --recursive if that is unexpected)"))
            return

        msg = linesep.join([
            "{suc} {path}".format(
                suc="Added" if item.get('success', False)
                    else "Failed to add. (%s)" % item.get('note',
                                                          'unknown reason'),
                path=item.get('file'))
            for item in res])
        ui.message(msg)
