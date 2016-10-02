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
from os.path import dirname

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
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import PathOutsideRepositoryError
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural
from datalad.utils import assure_list
from datalad.utils import with_pathsep as _with_sep  # TODO: RF whenever merge conflict is not upon us

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod
from .dataset import resolve_path
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
        lgr.debug("Installation attempt failed with exception: %s",
                  exc_str(e))
    return p_ds, fresh


def _sort_paths_into_datasets(paths, out=None, dir_lookup=None,
                              recursive=False, recursion_limit=None):
    """Returns dict of `existing dataset path`: `directory` mappings

    Any paths that are not part of a dataset or ignored.
    """
    # sort paths into the respective datasets
    if dir_lookup is None:
        dir_lookup = {}
    if out is None:
        out = {}
    # paths that don't exist (yet)
    unavailable_paths = []
    for path in paths:
        if not lexists(path):
            # not there yet, impossible to say which ds it will actually
            # be in, if any
            unavailable_paths.append(path)
            continue
        # the path exists in some shape or form
        if isdir(path):
            # this could contain all types of additional content
            d = path
        else:
            # for everything else we are interested in the container
            d = dirname(path)
            if not d:
                d = curdir
        # this could be `None` if there is no git repo
        dspath = dir_lookup.get(d, GitRepo.get_toppath(d))
        dir_lookup[d] = dspath
        if not dspath:
            lgr.warning("%s is not part of a dataset, ignored.", path)
            continue
        if isdir(path):
            ds = Dataset(dspath)
            # we need to doublecheck that this is not a subdataset mount
            # point, in whic case get_toppath() would point to the parent
            smpath = ds.get_containing_subdataset(
                path, recursion_limit=1).path
            if smpath != dspath:
                # fix entry
                dir_lookup[d] = smpath
                # submodule still needs to be obtained
                unavailable_paths.append(path)
                continue
            if recursive:
                # make sure we get everything relevant in all _checked out_
                # subdatasets, obtaining of previously unavailable subdataset
                # else done elsewhere
                subs = ds.get_subdatasets(fulfilled=True,
                                          recursive=recursive,
                                          recursion_limit=recursion_limit)
                for sub in subs:
                    subdspath = opj(dspath, sub)
                    if subdspath.startswith(_with_sep(path)):
                        # this subdatasets is underneath the search path
                        # we want it all
                        out[subdspath] = [subdspath]
        out[dspath] = out.get(dspath, []) + [path]
    return out, unavailable_paths, dir_lookup


def _get(content_by_ds, refpath=None, source=None, jobs=None, fulfillnew=False):
    for ds_path in sorted(content_by_ds.keys()):
        cur_ds = Dataset(ds_path)
        content = content_by_ds[ds_path]
        results = []
        if len(content) >= 1 and content[0] == curdir:
            # we hit a subdataset that just got installed few lines above, and was
            # requested specifically, as opposed to some of its content. Unless we
            # are asked to fulfill all handles that at some point in the process
            # we consider having fulfilled the dataset handle good enough
            results.append(cur_ds)
            if not fulfillnew:
                lgr.debug(
                    "Will not get any content in subdataset %s without recursion enabled",
                    cur_ds)
                yield results
                continue

        # needs to be an annex:
        found_an_annex = isinstance(cur_ds.repo, AnnexRepo)
        if not found_an_annex:
            lgr.debug("Found no annex at %s. Skipped.", cur_ds)
            if results:
                yield results
            continue
        lgr.info("Getting %s file/dir(s) of dataset %s ...",
                 len(content), cur_ds)

        results.extend(cur_ds.repo.get(
            content,
            options=['--from=%s' % source] if source else [],
            jobs=jobs))

        if refpath:
            # adapt relative paths reported by annex to be relative some
            # reference
            if ds_path != refpath:
                for lr in results:
                    if isinstance(lr, dict):
                        lr['file'] = relpath(opj(ds_path, lr['file']), refpath)
        yield results


def _recursive_install_subds_underneath(ds, recursion_limit, start=None):
    from .install import _install_subds_from_flexible_source
    content_by_ds = {}
    if recursion_limit is not None and recursion_limit <= 0:
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
                subds = _install_subds_from_flexible_source(
                    ds, sub.path, sub.url)
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
                recursion_limit=None if recursion_limit is None else recursion_limit - 1
            ))
    return content_by_ds


def _unwind(generators):
    res = []
    for item in generators:
        res.extend(item)
    return res


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

        dataset_path = dataset.path if isinstance(dataset, Dataset) else dataset
        path = assure_list(path)
        if not path:
            raise InsufficientArgumentsError(
                "`get` needs at least one path as argument")

        # IMPLEMENTATION CONCEPT:
        #
        # 1. turn all input paths into absolute paths
        # 2. Sort the world into existing handles and the rest
        # 3. Try locate missing handles (obtain subdatasets along the way)
        # 4. Expand into subdatasets with recursion enables (potentially
        #    obtain even more subdatasets
        # 5. Shoot info of which handles to get in each subdataset to,
        #    git-annex, once at the very end

        # resolve path(s):
        resolved_paths = [resolve_path(p, dataset) for p in path]
        if dataset:
            # guarantee absolute paths relative to any given dataset
            resolved_paths = [opj(dataset_path, p) for p in resolved_paths]
        lgr.debug('Resolved targets to get: %s', resolved_paths)

        # sort paths into the respective datasets
        content_by_ds, unavailable_paths, dir_lookup = \
            _sort_paths_into_datasets(resolved_paths,
                                      recursive=recursive,
                                      recursion_limit=recursion_limit)
        # IMPORTANT NOTE re `content_by_ds`
        # each key is a subdataset that we need to get something in
        # if the value[0] is the subdataset's path, we want all of it
        # if the value[0] == curdir, we just installed it as part of
        # resolving file handles and we did not say anything but "give
        # me the dataset handle" -- without fulfill='all' not file handles
        # in such a subdataset will be fulfilled

        # explore the unknown
        for path in sorted(unavailable_paths):
            # how close can we get?
            dspath = GitRepo.get_toppath(path)
            if dspath is None:
                # nothing we can do for this path
                continue
            ds = Dataset(dspath)
            # must always yield a dataset -- we sorted out the ones outside
            # any dataset at the very top
            assert ds.is_installed()
            # now actually obtain whatever is necessary to get to this path
            containing_ds = install_necessary_subdatasets(ds, path)
            if containing_ds.path != ds.path:
                # mark resulting dataset as auto-installed
                if containing_ds.path == path:
                    # we had to get the entire dataset, not something within
                    # mark that it just appeared
                    content_by_ds[path] = [curdir]
                else:
                    # we need to get content within
                    content_by_ds[path] = [path]

        if recursive:
            # obtain any subdatasets underneath the paths given inside the
            # subdatasets that we know already exist
            for subdspath in sorted(content_by_ds.keys()):
                for content_path in content_by_ds[subdspath]:
                    if not isdir(content_path):
                        # a non-directory cannot have content underneath
                        continue
                    cbysubds = _recursive_install_subds_underneath(
                        Dataset(subdspath),
                        # `content_path` was explicitly given as input
                        # we count recursions from the input, hence we
                        # can start with the full number
                        recursion_limit,
                        start=content_path)
                    # gets file content for all freshly installed subdatasets
                    content_by_ds.update(cbysubds)

        ## we have now done everything we could to obtain whatever subdataset
        ## to get something on the file system for previously unavailable paths
        ## check and sort one last
        content_by_ds, unavailable_paths, dir_lookup = \
            _sort_paths_into_datasets(
                unavailable_paths,
                out=content_by_ds,
                dir_lookup=dir_lookup,
                recursive=recursive,
                recursion_limit=recursion_limit)

        if unavailable_paths:
            lgr.warning('could not find and ignored paths: %s', unavailable_paths)

        # hand over to git-annex
        return _unwind(
            _get(content_by_ds, refpath=dataset_path, source=source, jobs=jobs,
                 fulfillnew=fulfill == 'all'))

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
