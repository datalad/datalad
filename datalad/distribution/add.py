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

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import nosave_opt
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_add_opts
from datalad.interface.common_opts import if_dirty_opt
from datalad.interface.utils import handle_dirty_dataset
from datalad.interface.save import Save
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
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
        save=nosave_opt,
        if_dirty=if_dirty_opt,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_add_opts=annex_add_opts)

    @staticmethod
    @datasetmethod(name='add')
    def __call__(
            path=None,
            source=None,
            dataset=None,
            to_git=False,
            save=True,
            recursive=False,
            recursion_limit=None,
            if_dirty='ignore',
            git_opts=None,
            annex_opts=None,
            annex_add_opts=None):

        # parameter constraints:
        if not path and not source:
            raise InsufficientArgumentsError("insufficient information for "
                                             "adding: requires at least a path "
                                             "or a source.")

        # When called from cmdline `path` and `source` will be a list even if
        # there is only one item.
        # Make sure we deal with the same when called via python API:
        # always yields list; empty if None
        path = assure_list(path)
        source = assure_list(source)

        # TODO: Q: are the list operations in the following 3 blocks (resolving
        #          paths, sources and datasets) guaranteed to be stable
        #          regarding order?

        # resolve path(s):
        # TODO: RF: resolve_path => datalad.utils => more general (repos => normalize paths)
        resolved_paths = [resolve_path(p, dataset) for p in path]

        # must come after resolve_path()!!
        # resolve dataset:
        dataset = require_dataset(dataset, check_installed=True,
                                  purpose='adding')
        handle_dirty_dataset(dataset, if_dirty)

        # resolve source(s):
        resolved_sources = []
        for s in source:
            if not is_datalad_compat_ri(s):
                raise ValueError("invalid source parameter: %s" % s)
            resolved_sources.append(_get_git_url_from_source(s))

        # find (sub-)datasets to add things to (and fail on invalid paths):
        if recursive:

            # 1. Find the (sub-)datasets containing the given path(s):
            # Note, that `get_containing_subdataset` raises if `p` is
            # outside `dataset`, but it returns `dataset`, if `p` is inside
            # a subdataset not included by `recursion_limit`. In the latter
            # case, the git calls will fail instead.
            # We could check for this right here and fail early, but this
            # would lead to the need to discover the entire hierarchy no
            # matter if actually required.
            resolved_datasets = [dataset.get_containing_subdataset(
                p, recursion_limit=recursion_limit) for p in resolved_paths]

            # 2. Find implicit subdatasets to call add on:
            # If there are directories in resolved_paths (Note,
            # that this includes '.' and '..'), check for subdatasets
            # beneath them. These should be called recursively with '.'.
            # Therefore add the subdatasets to resolved_datasets and
            # corresponding '.' to resolved_paths, in order to generate the
            # correct call.
            for p in resolved_paths:
                if isdir(p):
                    for subds_path in \
                        dataset.get_subdatasets(absolute=True, recursive=True,
                                                recursion_limit=recursion_limit):
                        if subds_path.startswith(_with_sep(p)):
                            resolved_datasets.append(Dataset(subds_path))
                            resolved_paths.append(curdir)

        else:
            # if not recursive, try to add everything to dataset itself:
            resolved_datasets = [dataset for i in range(len(resolved_paths))]

        # we need a resolved dataset per path:
        assert len(resolved_paths) == len(resolved_datasets)

        # sort parameters for actual git/git-annex calls:
        # (dataset, path, source)
        from six.moves import zip_longest

        param_tuples = list(zip_longest(resolved_datasets,
                                        resolved_paths, resolved_sources))
        # possible None-datasets in `param_tuples` were filled in by zip_longest
        # and need to be replaced by `dataset`:
        param_tuples = [(d if d is not None else dataset, p, s)
                        for d, p, s in param_tuples]

        calls = {d.path: {  # list of paths to 'git-add':
                            'g_add': [],
                            # list of paths to 'git-annex-add':
                            'a_add': [],
                            # list of sources to 'git-annex-addurl':
                            'addurl_s': [],
                            # list of (path, source) to
                            # 'git-annex-addurl --file':
                            'addurl_f': []
                         } for d in [i for i, p, s in param_tuples]}

        for ds, p, s in param_tuples:
            # it should not happen, that `path` as well as `source` are None:
            assert p or s

            if not s:
                # we have a path only
                if to_git:
                    calls[ds.path]['g_add'].append(p)
                else:
                    calls[ds.path]['a_add'].append(p)
            elif not p:
                # we have a source only
                if to_git:
                    raise NotImplementedError("Can't add a remote source "
                                              "directly to git.")
                calls[ds.path]['addurl_s'].append(s)
            else:
                # we have a path and a source
                if to_git:
                    raise NotImplementedError("Can't add a remote source "
                                              "directly to git.")
                calls[ds.path]['addurl_f'].append((p, s))

        # now do the actual add operations:
        # TODO: implement git/git-annex/git-annex-add options

        return_values = []
        for dspath in calls:
            ds = Dataset(dspath)

            lgr.info("Processing dataset %s ..." % ds)

            # check every (sub-)dataset for annex once, since we can't add or
            # addurl anything, if there is no annex:
            # TODO: Q: Alternatively, just call git-annex-init if there's no
            # annex yet and we have an annex-add/annex-addurl request?
            _is_annex = isinstance(ds.repo, AnnexRepo)

            if calls[ds.path]['g_add']:
                return_values.extend(ds.repo.add(calls[dspath]['g_add'],
                                                 git=True,
                                                 git_options=git_opts))
            if calls[ds.path]['a_add']:
                if _is_annex:
                    return_values.extend(
                        ds.repo.add(calls[dspath]['a_add'],
                                    git=False,
                                    git_options=git_opts,
                                    annex_options=annex_opts,
                                    options=annex_add_opts
                                    )
                    )
                else:
                    lgr.debug("{0} is no annex. Skip 'annex-add' for "
                              "files {1}".format(ds, calls[dspath]['a_add']))
                    return_values.extend(
                        [{'file': f,
                          'success': False,
                          'note': "no annex at %s" % ds.path}
                         for f in calls[dspath]['a_add']]
                    )

            # TODO: AnnexRepo.add_urls' return value doesn't contain the created
            #       file name but the url
            if calls[ds.path]['addurl_s']:
                if _is_annex:
                    return_values.extend(
                        ds.repo.add_urls(calls[ds.path]['addurl_s'],
                                         options=annex_add_opts,
                                         # TODO: extra parameter for addurl?
                                         git_options=git_opts,
                                         annex_options=annex_opts
                                         )
                    )
                else:
                    lgr.debug("{0} is no annex. Skip 'annex-addurl' for "
                              "files {1}".format(ds, calls[dspath]['addurl_s']))
                    return_values.extend(
                        [{'file': f,
                          'success': False,
                          'note': "no annex at %s" % ds.path}
                         for f in calls[dspath]['addurl_s']]
                    )

            if calls[ds.path]['addurl_f']:
                if _is_annex:
                    for f, u in calls[ds.path]['addurl_f']:
                        return_values.append(
                            ds.repo.add_url_to_file(f, u,
                                                    options=annex_add_opts,  # TODO: see above
                                                    git_options=git_opts,
                                                    annex_options=annex_opts,
                                                    batch=True))
                else:
                    lgr.debug("{0} is no annex. Skip 'annex-addurl' for "
                              "files {1}".format(ds, calls[dspath]['addurl_f']))
                    return_values.extend(
                        [{'file': f,
                          'success': False,
                          'note': "no annex at %s" % ds.path}
                         for f in calls[dspath]['addurl_f']]
                    )

        if save and len(return_values):
            # we got something added -> save
            # everything we care about at this point should be staged already
            Save.__call__(
                message='[DATALAD] added content',
                dataset=ds,
                auto_add_changes=False,
                recursive=False)

        return return_values

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
