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
from os import linesep
from os.path import isdir
from os.path import join as opj
from os.path import relpath
from os.path import lexists

from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_get_opts
from datalad.interface.common_opts import verbose
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandNotAvailableError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural

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
    order to fulfill a request. However, this implicit installation of
    subdatasets is done only, if an explicitly specified path belongs to such a
    subdataset and for that purpose `recursion_limit` is ignored. Otherwise get
    recurses into already installed subdatasets only and the depth of this
    recursion can be limited by `recursion_limit`.

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
        annex_get_opts=annex_get_opts,
        verbose=verbose)

    # Note: May be use 'git annex find --not --in here' to have a list of all
    # files to actually get and give kind of a progress in terms of number
    # files processed ...

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
            annex_get_opts=None,
            verbose=False):

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
        lgr.debug("Resolving paths ...")
        resolved_paths = [resolve_path(p, dataset) for p in path]

        # resolve base dataset:
        ds = require_dataset(dataset, check_installed=True,
                             purpose='getting content')
        lgr.debug("Resolved dataset: %s" % ds)

        # resolve possible subdatasets:
        lgr.debug("Resolving (sub-)datasets ...")
        resolved_datasets = dict()
        for p in resolved_paths:
            # Note: For explicitly given paths we do consider
            # (possibly to be installed) subdatasets without `recursion_limit`.
            # It is applied only for implicit recursion into subdatasets -
            # see below under "if recursive"-block.
            try:
                p_ds = ds.get_containing_subdataset(p, recursion_limit=None)
            except PathOutsideRepositoryError as e:
                lgr.warning(exc_str(e) + linesep + "Ignored.")
                continue

            # Note: A not yet existing thing might need several levels of
            # subdataset installation until we can actually get it.
            if not p_ds.is_installed():
                # this is expected to be ensured by require_dataset:
                assert p_ds != ds

                # we try to install subdatasets as long as there is anything to
                # install in between the last one installed and the actual thing
                # to get (which is `p`):
                cur_subds = p_ds
                cur_par_ds = p_ds.get_superdataset()
                assert cur_par_ds is not None
                _install_success = False
                while not cur_subds.is_installed():
                    lgr.info("Installing subdataset {0} in order to get "
                             "{1}".format(cur_subds, p))
                    try:
                        cur_par_ds.install(cur_subds.path)
                        _install_success = True
                    except Exception as e:
                        lgr.warning("Installation of subdataset {0} failed. {1}"
                                    " ignored.".format(cur_subds, p))
                        lgr.debug("Installation attempt failed with exception:"
                                  "{0}{1}".format(linesep, exc_str(e)))
                        _install_success = False
                        # TODO: Should we try to clean up here and remove
                        # anything we installed along the way? (Currently needs
                        # to wait for being clear about uninstall)
                        # Another approach: Record what went wrong and have a
                        # dedicated 'datalad clean' or sth
                        break
                    cur_par_ds = cur_subds

                    # Note: PathOutsideRepositoryError should not happen here.
                    # If so, there went something fundamentally wrong, so:
                    # raise instead of just log a warning.
                    cur_subds = \
                        p_ds.get_containing_subdataset(p, recursion_limit=None)

                if not _install_success:
                    # skip p, if we didn't manage to install its containing
                    # subdataset
                    continue

                # assign the last one installed to p_ds to associate it with p:
                p_ds = cur_subds

            if not lexists(p):
                # Note: Skipping non-existing paths currently.
                # We could also include them in the call to AnnexRepo and get
                # it reported with success=False and the reason in 'note'.
                # But not even invoking annex at all is faster, so we skip
                # it early:
                lgr.warning("{0} not found. Ignored.".format(p))
                continue

            # collect all paths belonging to a certain (sub-)datasets in order
            # to have one call to git-annex per repo:
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
                                         recursion_limit=recursion_limit,
                                         fulfilled=True):
                        if subds_path.startswith(_with_sep(p)):
                            if subds_path not in resolved_datasets:
                                lgr.debug("Added implicit subdataset {0} "
                                          "from path {1}".format(subds_path, p))
                                resolved_datasets[subds_path] = []
                            resolved_datasets[subds_path].append(curdir)
        # Note: While the following is not very telling in terms of progress,
        # it remains at info level atm to have at least some idea, what `get` is
        # doing (in combination with "Getting x files of Dataset y") until we
        # have a working solution for showing progress. Then it should go to
        # debug level.
        lgr.info("Found {0} datasets to "
                 "operate on.".format(len(resolved_datasets)))
        # TODO:
        # git_opts
        # annex_opts
        # annex_get_opts

        # now we are ready to actually get the stuff

        found_an_annex = False
        global_results = []
        # the actual calls:
        for ds_path in resolved_datasets:
            cur_ds = Dataset(ds_path)
            # needs to be an annex:
            if not isinstance(cur_ds.repo, AnnexRepo):
                lgr.debug("Found no annex at {0}. Skipped.".format(cur_ds))
                continue
            found_an_annex = True
            lgr.info("Getting {0} file/dir(s) of dataset "
                     "{1} ...".format(len(resolved_datasets[ds_path]), cur_ds))

            local_results = cur_ds.repo.get(resolved_datasets[ds_path],
                                            options=['--from=%s' % source]
                                                     if source else [])

            # if we recurse into subdatasets, adapt relative paths reported by
            # annex to be relative to the toplevel dataset we operate on:
            if cur_ds != ds:
                for i in range(len(local_results)):
                    local_results[i]['file'] = \
                        relpath(opj(ds_path, local_results[i]['file']), ds.path)

            global_results.extend(local_results)

        if not found_an_annex:
            lgr.warning("Found no annex. Could not perform any get operation.")
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
            ui.message("Got nothing")
            return

        # provide summary
        nsuccess = sum(item.get('success', False) for item in res)
        nfailure = len(res) - nsuccess
        msg = "Tried to get %d %s." % (len(res), single_or_plural("file", "files", len(res)))
        if nsuccess:
            msg += " Got %d. " % nsuccess
        if nfailure:
            msg += " Failed to get %d." % (nfailure,)
        ui.message(msg)

        # if just a few or less than initially explicitly requested
        if len(res) < 10 or args.verbose:
            msg = linesep.join([
                "{path} ... {suc}".format(
                    suc="ok." if item.get('success', False)
                        else "failed. (%s)" % item.get('note', 'unknown reason'),
                    path=item.get('file'))
                for item in res])
            ui.message(msg)


