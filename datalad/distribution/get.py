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

from itertools import chain
from os import curdir
from os.path import isdir
from os.path import join as opj
from os.path import relpath

from datalad.interface.base import Interface
from datalad.interface.utils import get_paths_by_dataset
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import git_opts
from datalad.interface.common_opts import annex_opts
from datalad.interface.common_opts import annex_get_opts
from datalad.interface.common_opts import jobs_opt
from datalad.interface.common_opts import reckless_opt
from datalad.interface.common_opts import verbose
from datalad.support.constraints import EnsureInt
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural
from datalad.utils import get_dataset_root
from datalad.utils import with_pathsep as _with_sep

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod
from .utils import _install_subds_from_flexible_source

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


def _install_necessary_subdatasets(ds, path, reckless):
    """Installs subdatasets of `ds`, that are necessary to obtain in order
    to have access to `path`.

    Gets the subdataset containing `path` regardless of whether or not it was
    already installed. While doing so, installs everything necessary in between
    the uppermost installed one and `path`.

    Note: `ds` itself has to be installed.

    Parameters
    ----------
    ds: Dataset
    path: str
    reckless: bool

    Returns
    -------
    Dataset
      the last (deepest) subdataset, that was installed
    """
    assert ds.is_installed()

    # figuring out what dataset to start with:
    start_ds = ds.get_containing_subdataset(path, recursion_limit=None)

    if start_ds.is_installed():
        return start_ds

    # we try to install subdatasets as long as there is anything to
    # install in between the last one installed and the actual thing
    # to get (which is `path`):
    cur_subds = start_ds

    # Note, this is not necessarily `ds`:
    # MIH: would be good to know why?
    cur_par_ds = cur_subds.get_superdataset()
    assert cur_par_ds is not None

    while not cur_subds.is_installed():
        lgr.info("Installing subdataset %s%s",
                 cur_subds,
                 ' in order to get %s' % path if cur_subds.path != path else '')
        # get submodule info
        submodules = cur_par_ds.repo.get_submodules()
        submodule = [sm for sm in submodules
                     if sm.path == relpath(cur_subds.path, start=cur_par_ds.path)][0]
        # install using helper that give some flexibility regarding where to
        # get the module from
        _install_subds_from_flexible_source(
            cur_par_ds,
            submodule.path,
            submodule.url,
            reckless)

        cur_par_ds = cur_subds

        # Note: PathOutsideRepositoryError should not happen here.
        # If so, there went something fundamentally wrong, so raise something
        # different, to not let the caller mix it up with a "regular"
        # PathOutsideRepositoryError from above. (Although it could be
        # detected via its `repo` attribute)
        try:
            cur_subds = \
                cur_subds.get_containing_subdataset(path, recursion_limit=None)
        except PathOutsideRepositoryError as e:
            raise RuntimeError("Unexpected failure: {0}".format(exc_str(e)))

    return cur_subds


def _recursive_install_subds_underneath(ds, recursion_limit, reckless, start=None):
    content_by_ds = {}
    if isinstance(recursion_limit, int) and recursion_limit <= 0:
        return content_by_ds
    # loop over submodules not subdatasets to get the url right away
    # install using helper that give some flexibility regarding where to
    # get the module from
    for sub in ds.repo.get_submodules():
        subds = Dataset(opj(ds.path, sub.path))
        if start is not None and not subds.path.startswith(_with_sep(start)):
            # this one we can ignore, not underneath the start path
            continue
        if not subds.is_installed():
            try:
                lgr.info("Installing subdataset %s", subds.path)
                subds = _install_subds_from_flexible_source(
                    ds, sub.path, sub.url, reckless)
                # we want the entire thing, but mark this subdataset
                # as automatically installed
                content_by_ds[subds.path] = [curdir]
            except Exception as e:
                # skip, if we didn't manage to install subdataset
                lgr.warning(
                    "Installation of subdatasets %s failed, skipped", subds)
                lgr.debug("Installation attempt failed with exception: %s",
                          exc_str(e))
                continue
            # otherwise recurse
            # we can skip the start expression, we know we are within
            content_by_ds.update(_recursive_install_subds_underneath(
                subds,
                recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                reckless=reckless
            ))
    return content_by_ds


def _get(content_by_ds, refpath=None, source=None, jobs=None,
         get_data=True):
    """Loops through datasets and calls git-annex call where appropriate
    """
    for ds_path in sorted(content_by_ds.keys()):
        cur_ds = Dataset(ds_path)
        content = content_by_ds[ds_path]
        # TODO generator
        # remove list
        results = []
        # TODO generator
        # install result already reported before -> remove completely
        if len(content) >= 1 and content[0] == curdir:
            # we hit a subdataset that just got installed few lines above, and was
            # requested specifically, as opposed to some of its content.
            results.append(cur_ds)

        # TODO generator
        # simply return/continue, nothing to report anymore
        if not get_data:
            lgr.debug(
                "Will not get any content in %s, as instructed.",
                cur_ds)
            yield results
            continue

        # needs to be an annex:
        found_an_annex = isinstance(cur_ds.repo, AnnexRepo)
        if not found_an_annex:
            # TODO generator
            # yield `content` items as 'notneeded' results
            # and just return/continue
            lgr.debug("Found no annex at %s. Skipped.", cur_ds)
            if results:
                yield results
            continue
        # TODO move this message into AnnexRepo.get()
        lgr.info("Getting %i items of dataset %s ...",
                 len(content), cur_ds)

        # TODO generator
        # convert annex report dict into our format and yield one-by-one
        results.extend(cur_ds.repo.get(
            content,
            options=['--from=%s' % source] if source else [],
            jobs=jobs))
        # TODO generator
        # do not relpath here, but put refpath into result dict
        # relpathing will be done outside if desired
        if refpath:
            # adapt relative paths reported by annex to be relative some
            # reference
            if ds_path != refpath:
                for lr in results:
                    if isinstance(lr, dict):
                        lr['file'] = relpath(opj(ds_path, lr['file']), refpath)
        yield results


class Get(Interface):
    """Get any dataset content (files/directories/subdatasets).

    This command only operates on dataset content. To obtain a new independent
    dataset from some source use the `install` command.

    By default this command operates recursively within a dataset, but not
    across potential subdatasets, i.e. if a directory is provided, all files in
    the directory are obtained. Recursion into subdatasets is supported too. If
    enabled, relevant subdatasets are detected and installed in order to
    fulfill a request.

    Known data locations for each requested file are evaluated and data are
    obtained from some available location (according to git-annex configuration
    and possibly assigned remote priorities), unless a specific source is
    specified.

    .. note::
      Power-user info: This command uses :command:`git annex get` to fulfill
      file handles.
    """

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="PATH",
            doc="""specify the dataset to perform the add operation on, in
            which case `path` arguments are interpreted as being relative
            to this dataset.  If no dataset is given, an attempt is made to
            identify a dataset for each input `path`""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""path/name of the requested dataset component. The component
            must already be known to a dataset. To add new components to a
            dataset use the `add` command""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        source=Parameter(
            args=("-s", "--source",),
            metavar="LABEL",
            doc="""label of the data source to be used to fulfill requests.
            This can be the name of a dataset :term:`sibling` or another known
            source""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=Parameter(
            args=("--recursion-limit",),
            metavar="LEVELS",
            constraints=EnsureInt() | EnsureChoice('existing') | EnsureNone(),
            doc="""limit recursion into subdataset to the given number of levels.
            Alternatively, 'existing' will limit recursion to subdatasets that already
            existed on the filesystem at the start of processing, and prevent new
            subdatasets from being obtained recursively."""),
        get_data=Parameter(
            args=("-n", "--no-data",),
            dest='get_data',
            action='store_false',
            doc="""whether to obtain data for all file handles. If disabled, `get`
            operations are limited to dataset handles.[CMD:  This option prevents data
            for file handles from being obtained CMD]"""),
        reckless=reckless_opt,
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
            path=None,
            source=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            get_data=True,
            reckless=False,
            git_opts=None,
            annex_opts=None,
            annex_get_opts=None,
            jobs=None,
            verbose=False,
            # internal -- instead of returning 'get'ed items, return final
            # content_by_ds, unavailable_paths.  To be used by the call from
            # Install.__call__ and done so to avoid creating another reusable
            # function which would need to duplicate all this heavy list of
            # kwargs
            # TODO generator
            # remove and replace with result transformation at the receiving end
            # (i.e. `install`)
            _return_datasets=False
    ):
        # IMPLEMENTATION CONCEPT:
        #
        # 1. Sort the world into existing handles and the rest
        # 2. Try locate missing handles (obtain subdatasets along the way)
        # 3. Expand into subdatasets with recursion enables (potentially
        #    obtain even more subdatasets
        # 4. Shoot info of which handles to get in each subdataset to,
        #    git-annex, once at the very end

        dataset_path = dataset.path if isinstance(dataset, Dataset) else dataset
        if not (dataset or path):
            raise InsufficientArgumentsError(
                "Neither dataset nor target path(s) provided")
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = dataset_path
        # use lookup cache -- we need that info further down
        dir_lookup = {}
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit,
            dir_lookup=dir_lookup)
        # NOTE: Do not act upon unavailable paths yet! Done below after testing
        # which ones could be obtained

        # explore the unknown
        for path in sorted(unavailable_paths):
            # how close can we get?
            dspath = get_dataset_root(path)
            if dspath is None:
                # nothing we can do for this path
                continue
            ds = Dataset(dspath)
            # now actually obtain whatever is necessary to get to this path
            # TODO generator
            # needs to yield intermediate results inside
            containing_ds = _install_necessary_subdatasets(ds, path, reckless)
            if containing_ds.path != ds.path:
                # TODO generator
                # turn log message into result message
                lgr.debug("Installed %s to fulfill request for content for "
                          "path %s", containing_ds, path)
                # mark resulting dataset as auto-installed
                # TODO generator
                # check where this "markup" is needed and see if/how it could be
                # read from a result dict
                if containing_ds.path == path:
                    # we had to get the entire dataset, not something within
                    # mark that it just appeared
                    content_by_ds[path] = [curdir]
                else:
                    # we need to get content within
                    content_by_ds[path] = [path]

        if recursive and not recursion_limit == 'existing':
            # obtain any subdatasets underneath the paths given inside the
            # subdatasets that we know already exist
            # unless we do not want recursion into not-yet-installed datasets
            for subdspath in sorted(content_by_ds.keys()):
                for content_path in content_by_ds[subdspath]:
                    if not isdir(content_path):
                        # a non-directory cannot have content underneath
                        continue
                    subds = Dataset(subdspath)
                    lgr.info(
                        "Obtaining %s %s recursively",
                        subds,
                        ("underneath %s" % content_path
                         if subds.path != content_path
                         else ""))
                    # TODO generator
                    # needs to yield obtained datasets inside
                    # inspect results, should only get datasets, complain if not
                    # convert result info into content_by_ds update below
                    # but also yield the completed install results right here
                    cbysubds = _recursive_install_subds_underneath(
                        subds,
                        # `content_path` was explicitly given as input
                        # we count recursions from the input, hence we
                        # can start with the full number
                        recursion_limit,
                        reckless,
                        # protect against magic marker misinterpretation
                        # only relevant for _get, hence replace here
                        start=content_path if content_path != curdir else None)
                    # gets file content for all freshly installed subdatasets
                    content_by_ds.update(cbysubds)

        # we have now done everything we could to obtain whatever subdataset
        # to get something on the file system for previously unavailable paths
        # check and sort one last
        content_by_ds, unavailable_paths, nondataset_paths = \
            get_paths_by_dataset(
                unavailable_paths,
                recursive=recursive,
                recursion_limit=recursion_limit,
                out=content_by_ds,
                dir_lookup=dir_lookup)

        assert not nondataset_paths, "Somehow broken implementation logic"

        # TODO generator
        # yield unavailable_paths as 'impossible' results
        if unavailable_paths:
            lgr.warning('ignored non-existing paths: %s', unavailable_paths)

        # hand over to git-annex
        # TODO generator
        # needs to yield file `get` results individually
        # evaluate to factor the dataset loop out of _get() and put it here
        results = list(chain.from_iterable(
            _get(content_by_ds, refpath=dataset_path, source=source, jobs=jobs,
                 get_data=get_data)))
        # TODO generator
        # the remainder of the function is obsolete after generator RF
        # ??? should we in _return_datasets case just return both content_by_ds
        # and unavailable_paths may be so we provide consistent across runs output
        # and then issue outside similar IncompleteResultsError?
        if unavailable_paths:  # and likely other error flags
            if _return_datasets:
                results = sorted(set(content_by_ds).difference(unavailable_paths))
            raise IncompleteResultsError(results, failed=unavailable_paths)
        else:
            return sorted(content_by_ds) if _return_datasets else results

    # TODO generator
    # RF for new interface
    @staticmethod
    def result_renderer_cmdline(res, args):
        from datalad.ui import ui
        from os import linesep
        if res is None:
            res = []
        if not isinstance(res, list):
            res = [res]
        if not len(res):
            ui.message("Got nothing new")
            return

        # provide summary
        nsuccess = sum(item.get('success', False) if isinstance(item, dict) else True
                       for item in res)
        nfailure = len(res) - nsuccess
        msg = "Tried to get %d %s." % (
            len(res), single_or_plural("file", "files", len(res)))
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
