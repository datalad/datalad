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
from os.path import isdir
from os.path import join as opj
from os.path import relpath

from datalad.interface.base import Interface
from datalad.interface.utils import get_paths_by_dataset
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.interface.results import YieldDatasets
from datalad.interface.results import annexjson2result
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


def _install_necessary_subdatasets(ds, path, reckless, refds_path):
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
        if not start_ds.path == refds_path:
            # we don't want to report the base dataset as notneeded
            # when `get` was called as a method of that dataset
            yield get_status_dict(
                'install', ds=start_ds, status='notneeded', logger=lgr,
                refds=refds_path, message=('%s is already installed', start_ds))
        return

    # we try to install subdatasets as long as there is anything to
    # install in between the last one installed and the actual thing
    # to get (which is `path`):
    cur_subds = start_ds

    # Note, this is not necessarily `ds`:
    # MIH: would be good to know why?
    cur_par_ds = cur_subds.get_superdataset()
    assert cur_par_ds is not None

    while not cur_subds.is_installed():
        # get submodule info
        submodules = cur_par_ds.repo.get_submodules()
        submodule = [sm for sm in submodules
                     if sm.path == relpath(cur_subds.path, start=cur_par_ds.path)][0]
        # install using helper that give some flexibility regarding where to
        # get the module from
        sd = _install_subds_from_flexible_source(
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

        yield get_status_dict(
            'install', ds=sd, status='ok', logger=lgr, refds=refds_path,
            message=(
                "Installed subdataset %s%s",
                cur_subds,
                ' in order to get %s' % path if cur_subds.path != path else ''))


def _recursive_install_subds_underneath(ds, recursion_limit, reckless, start=None,
                                        refds_path=None):
    if isinstance(recursion_limit, int) and recursion_limit <= 0:
        return
    # loop over submodules not subdatasets to get the url right away
    # install using helper that give some flexibility regarding where to
    # get the module from
    for sub in ds.repo.get_submodules():
        subds = Dataset(opj(ds.path, sub.path))
        if start is not None and not subds.path.startswith(_with_sep(start)):
            # this one we can ignore, not underneath the start path
            continue
        if subds.is_installed():
            yield get_status_dict(
                'install', ds=subds, status='notneeded', logger=lgr,
                refds=refds_path)
            continue
        try:
            subds = _install_subds_from_flexible_source(
                ds, sub.path, sub.url, reckless)
            yield get_status_dict(
                'install', ds=subds, status='ok', logger=lgr, refds=refds_path,
                message=("Installed subdataset %s", subds))
        except Exception as e:
            # skip all of downstairs, if we didn't manage to install subdataset
            yield get_status_dict(
                'install', ds=subds, status='error', logger=lgr, refds=refds_path,
                message=("Installation of subdatasets %s failed with exception: %s",
                         subds, exc_str(e)))
            continue
        # otherwise recurse
        # we can skip the start expression, we know we are within
        for res in _recursive_install_subds_underneath(
                subds,
                recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                reckless=reckless,
                refds_path=refds_path):
            yield res


def _get(ds, content, refds_path=None, source=None, jobs=None):
    """Loops through datasets and calls git-annex call where appropriate
    """
    # needs to be an annex:
    found_an_annex = isinstance(ds.repo, AnnexRepo)
    if not found_an_annex:
        for r in results_from_paths(
                content, status='notneeded',
                message="no dataset annex, content already present: %s",
                action='get', logger=lgr,
                refds=refds_path):
            yield r
        return
    for res in ds.repo.get(
            content,
            options=['--from=%s' % source] if source else [],
            jobs=jobs):
        res = annexjson2result(res, ds, type_='file', logger=lgr,
                               refds=refds_path)
        yield res


@build_doc
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
    @eval_results
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
    ):
        # helper
        as_ds = YieldDatasets()
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
        refds_path = dataset.path if isinstance(dataset, Dataset) else dataset
        # NOTE: Do not act upon unavailable paths yet! Done below after testing
        # which ones could be obtained

        # report dataset we already have and don't need to get
        for dspath in content_by_ds:
            d = Dataset(dspath)
            if not d.is_installed() or (dspath == refds_path):
                # do not report what hasn't arived yet
                # also do not report the base dataset that is already
                # present -- no surprise
                continue
            yield get_status_dict(
                'install', ds=d, status='notneeded', logger=lgr,
                refds=refds_path, message=('%s is already installed', d))

        # explore the unknown
        for path in sorted(unavailable_paths):
            # how close can we get?
            dspath = get_dataset_root(path)
            if dspath is None:
                # nothing we can do for this path
                continue
            ds = Dataset(dspath)
            # now actually obtain whatever is necessary to get to this path
            containing_ds = ds
            for res in _install_necessary_subdatasets(
                    ds, path, reckless, refds_path):
                # yield immediately so errors could be acted upon outside, before
                # we continue
                yield res
                # update to the current innermost dataset
                containing_ds = as_ds(res)

            # important to only do the next for the innermost subdataset
            # as the `recursive` logic below relies on that!
            if containing_ds.path != ds.path:
                # mark resulting dataset as auto-installed
                # TODO generator
                # check where this "markup" is needed and see if/how it could be
                # read from a result dict
                if containing_ds.path == path:
                    # we had to get the entire dataset, not something within
                    # mark that it just appeared
                    content_by_ds[containing_ds.path] = [curdir]
                else:
                    # we need to get content within
                    content_by_ds[containing_ds.path] = [path]

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
                    for res in _recursive_install_subds_underneath(
                            subds,
                            # `content_path` was explicitly given as input
                            # we count recursions from the input, hence we
                            # can start with the full number
                            recursion_limit,
                            reckless,
                            # protect against magic marker misinterpretation
                            # only relevant for _get, hence replace here
                            start=content_path if content_path != curdir else None,
                            refds_path=refds_path):
                        # yield immediately so errors could be acted upon
                        # outside, before we continue
                        yield res
                        if not (res['status'] == 'ok' and res['type'] == 'dataset'):
                            # nothing that we could act upon, we just reported it
                            # upstairs
                            continue
                        sd = as_ds(res)
                        # paranoia, so popular these days...
                        assert sd.is_installed()
                        # TODO: again the magic marker (like above) figure out if needed
                        content_by_ds[sd.path] = [curdir]

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

        for r in results_from_paths(
                unavailable_paths, status='impossible',
                message="path does not exist: %s",
                action='get', logger=lgr,
                refds=refds_path):
            yield r

        if not get_data:
            # done already
            return

        # hand over to git-annex
        for ds_path in sorted(content_by_ds.keys()):
            for res in _get(
                    Dataset(ds_path),
                    content_by_ds[ds_path],
                    refds_path=refds_path,
                    source=source,
                    jobs=jobs):
                yield res

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
