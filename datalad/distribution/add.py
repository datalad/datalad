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
import os

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_add_opts
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.utils import getpwd


from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import Dataset


__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.add')


class Add(Interface):
    """Add files/directories to an existing dataset.

    Typically, files and directories to be added to a dataset would be placed
    into a directory of a dataset, and subsequently this command can be used to
    register this new content with the dataset. With recursion enabled,
    files will be added to their respective subdatasets as well.

    Alternatively, a source location can be given to indicate where to obtain
    data from. If no `path` argument is provided in this case, the content will
    be obtained from the source location and a default local name, derived from
    the source location will be generated. Alternatively, an explicit `path`
    can be given to override the default.

    If more than one `path` argument and a source location are provided, the
    `path` arguments will be sequentially used to complete the source URL/path
    (be means of concatenation), and an attempt is made to obtain data from
    those locations.


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
      Power-user info: This command uses :command:`git annex add`, :command:`git annex addurl`, or
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
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar='URL/PATH',
            doc="url or local path of the to be added component's source",
            action="append",
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
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_add_opts=annex_add_opts)

    @staticmethod
    @datasetmethod(name='add')
    def __call__(
            dataset=None,
            path=None,
            source=None,
            to_git=False,
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None):

        # parameter constraints:
        if not path and not source:
            raise InsufficientArgumentsError("insufficient information for "
                                             "adding: requires at least a path "
                                             "or a source.")
        if path and not isinstance(path, list):
            path = [path]
        if source and not isinstance(source, list):
            source = [source]

        # resolve dataset:
        if dataset:
            if not isinstance(dataset, Dataset):
                dataset = Dataset(dataset)
        else:
            dspath = GitRepo.get_toppath(getpwd())
            if dspath:
                dataset = Dataset(dspath)
            else:
                raise InsufficientArgumentsError("insufficient information for "
                                                 "adding: no dataset given and "
                                                 "none found.")
        assert isinstance(dataset, Dataset)

        # list to collect parameters for actual git/git-annex calls:
        # (dataset, path, source)
        call_tuples = []


        resolved_paths = None
        if path:
            # resolve path(s) and assign the respective (sub)dataset:
            from .dataset import resolve_path
            from .install import get_containing_subdataset

            resolved_paths = [resolve_path(p, dataset) for p in path]

            for p in resolved_paths:

                # Note, that `get_containing_subdataset` raises if `p` is
                # outside `dataset`, but it returns `dataset`, if `p` is inside
                # a subdataset not included by `recursion_limit`. In the latter
                # case, the git calls will fail instead.
                # We could check for this right here and fail early, but this
                # would lead to the need to discover the entire hierarchy no
                # matter if actually required.
                r_ds = get_containing_subdataset(dataset, p,
                                                 recursive=recursive,
                                                 recursion_limit=recursion_limit)
                call_tuples.append((r_ds, p, None))

        # TODO: RF: Dataset.get_subdatasets to return Dataset instances!
        # TODO: RF: resolve_path => datalad.utils => more general (repos => normalize paths)
        # TODO: RF: get_containing_subdatasets => Dataset (+ recursion_limit)



        # TODO: Move
        if source and resolved_paths:
            # items in source lead to 'annex addurl' and
            # we have explicit target(s) for these
            # extract source-target pairs:
            num_pairs = min([len(resolved_paths), len(source)])
            url_targets = resolved_paths[:num_pairs]
            url_sources = source[:num_pairs]
            resolved_paths = resolved_paths[num_pairs:]
            source = source[num_pairs:]

            # now, `resolved_paths` or `source` might have remaining elements to be
            # treated as if they were passed without the other parameter

        # (remaining) resolved path(s) have no source => need to exists



        raise NotImplementedError

    # Note: addurl --file=...    existing <= "record that it can be downloaded from there" => test,whether it chekcs content




