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
from datalad.interface.common_opts import jobs_opt
from datalad.interface.common_opts import verbose
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural
from datalad.utils import assure_list

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import require_dataset
from .dataset import resolve_path
from .dataset import _with_sep
from .utils import install_necessary_subdatasets

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


def _report_ifjustinstalled(ds, p, recursion_limit):
    p_ds = None
    fresh = None
    try:
        # where would the current dataset think this path belongs
        present_container = ds.get_containing_subdataset(p, recursion_limit)
        was_installed = present_container.is_installed()
        # where does it actually belong
        p_ds = install_necessary_subdatasets(ds, p)
        # take note of whether the final subdataset just came to life
        fresh = present_container.path != p_ds.path or not was_installed
        if fresh:
            lgr.debug("Installed necessary (sub-)datasets: %s", p_ds)
    except PathOutsideRepositoryError as e:
        lgr.warning(exc_str(e) + linesep + "Ignored.")
    except Exception as e:
        # skip p, if we didn't manage to install its containing
        # subdataset
        lgr.warning(
            "Installation of necessary subdatasets for %s failed. Skipped.", p)
        lgr.debug("Installation attempt failed with exception: %s%s",
                  linesep, exc_str(e))
    return p_ds, fresh


class Get(Interface):
    """Get data content for files/directories of a dataset.

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
        fulfill=Parameter(
            args=("--fulfill",),
            choices=('auto', 'all'),
            doc="""whether to fulfill file handles. The default will do the
            right thing (TM). But it could be forced ('all')."""),
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_get_opts=annex_get_opts,
        jobs=jobs_opt,
        verbose=verbose)

    # Note: May be use 'git annex find --not --in here' to have a list of all
    # files to actually get and give kind of a progress in terms of number
    # files processed ...

    @staticmethod
    @datasetmethod(name='get')
    def __call__(
            path,
            source=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            fulfill='auto',
            git_opts=None,
            annex_opts=None,
            annex_get_opts=None,
            jobs=None,
            verbose=False):

        path = assure_list(path)
        if not path:
            raise InsufficientArgumentsError(
                "`get` needs at least one path as argument")

        # resolve path(s):
        # those aren't necessarily absolute paths
        resolved_paths = [resolve_path(p, dataset) for p in path]
        lgr.debug('Resolved targets to get: %s', resolved_paths)

        # resolve base dataset:
        ds = require_dataset(dataset, check_installed=True,
                             purpose='getting content')
        lgr.debug("Resolved dataset: %s", ds)

        # resolve possible subdatasets:
        lgr.debug("Determine necessary (sub-)datasets ...")
        resolved_datasets = dict()
        just_installed = dict()
        for p in resolved_paths:
            # install any required subdatasets
            p_ds, jinst = _report_ifjustinstalled(ds, p, recursion_limit)
            if p_ds is None:
                # error logging happens in function above
                continue
            just_installed[p_ds.path] = jinst

            if not lexists(p):
                # Note: Skipping non-existing paths currently.
                # We could also include them in the call to AnnexRepo and get
                # it reported with success=False and the reason in 'note'.
                # But not even invoking annex at all is faster, so we skip
                # it early:
                lgr.warning("%s not found. Ignored.", p)
                continue

            if p == relpath(p_ds.path, start=ds.path):
                # path to get is the entire subdataset itself
                # present it as such to annex below
                p = curdir

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
            # prefetch info on any possibly relevant subdataset
            subdss = sorted(ds.get_subdatasets(
                absolute=True,
                # we cannot do this, because we want to fulfill
                # dataset handles too
                #fulfilled=True,
                recursive=True,
                recursion_limit=recursion_limit))
            for p in resolved_paths:
                if not isdir(p):
                    # this cannot contain a subdataset
                    continue
                for subds_path in subdss:
                    # check all subdatasets and find all that are mounted
                    # underneath this directory -> we need to get them too
                    if not subds_path.startswith(_with_sep(p)):
                        # this one we can ignore for this path
                        continue
                    subds, jinst = _report_ifjustinstalled(
                        ds, subds_path, recursion_limit)
                    if subds is None:
                        # error reporting in _report_ifjustinstalled
                        continue
                    if jinst:
                        # we found one that we did not know before
                        lgr.debug("Obtained subdataset %s",
                                  subds_path)
                    resolved_datasets[subds_path] = [curdir]
                    just_installed[subds_path] = jinst
        # Note: While the following is not very telling in terms of progress,
        # it remains at info level atm to have at least some idea, what `get` is
        # doing (in combination with "Getting x files of Dataset y") until we
        # have a working solution for showing progress. Then it should go to
        # debug level.
        lgr.info("Found %i datasets to operate on.", len(resolved_datasets))
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
            if just_installed.get(ds_path, False):
                # Datasets are also people!
                global_results.append(cur_ds)
            if fulfill != 'all' \
                    and just_installed.get(ds_path, False) \
                    and len(resolved_datasets[ds_path]) \
                    and resolved_datasets[ds_path][0] == ds_path:
                # we hit a subdataset that just got installed few lines above, and was
                # requested specifically, as opposed to some of its content. Unless we
                # are asked to fulfill all handles that at some point in the process
                # we consider having fulfilled the dataset handle good enough
                lgr.debug(
                    "Will not get any content in subdataset %s without recursion enabled",
                    cur_ds)
                continue
            # needs to be an annex:
            found_an_annex = isinstance(cur_ds.repo, AnnexRepo)
            if not found_an_annex:
                lgr.debug("Found no annex at {0}. Skipped.".format(cur_ds))
                continue
            lgr.info("Getting {0} file/dir(s) of dataset "
                     "{1} ...".format(len(resolved_datasets[ds_path]), cur_ds))

            local_results = cur_ds.repo.get(resolved_datasets[ds_path],
                                            options=['--from=%s' % source]
                                                     if source else [],
                                            jobs=jobs)

            # if we recurse into subdatasets, adapt relative paths reported by
            # annex to be relative to the toplevel dataset we operate on:
            if cur_ds != ds:
                for lr in local_results:
                    lr['file'] = relpath(opj(ds_path, lr['file']), ds.path)

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
            ui.message("Got nothing")
            return

        # provide summary
        nsuccess = sum(item.get('success', False) if isinstance(item, dict) else True
                       for item in res)
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
                    suc="ok." if isinstance(item, Dataset) or item.get('success', False)
                        else "failed. (%s)" % item.get('note', 'unknown reason'),
                    path=item.get('file') if isinstance(item, dict) else item.path)
                for item in res])
            ui.message(msg)
