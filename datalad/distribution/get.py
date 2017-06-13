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

from os.path import join as opj
from os.path import relpath

from six.moves.urllib.parse import quote as urlquote

from datalad.interface.base import Interface
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.results import results_from_paths
from datalad.interface.results import annexjson2result
from datalad.interface.results import count_results
from datalad.interface.results import success_status_map
from datalad.interface.results import results_from_annex_noinfo
from datalad.interface.common_opts import recursion_flag
# from datalad.interface.common_opts import git_opts
# from datalad.interface.common_opts import annex_opts
# from datalad.interface.common_opts import annex_get_opts
from datalad.interface.common_opts import location_description
from datalad.interface.common_opts import jobs_opt
from datalad.interface.common_opts import reckless_opt
from datalad.interface.common_opts import verbose
from datalad.support.constraints import EnsureInt
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import InstallFailedError
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.network import URL
from datalad.support.network import RI
from datalad.dochelpers import exc_str
from datalad.dochelpers import single_or_plural
from datalad.utils import get_dataset_root
from datalad.utils import with_pathsep as _with_sep
from datalad.utils import unique

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod
from .clone import Clone
from .utils import _get_flexible_source_candidates
from .utils import _get_tracking_source
from .utils import _fixup_submodule_dotgit_setup

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


def _get_flexible_source_candidates_for_submodule(ds, sm_path, sm_url=None):
    """Retrieve candidates from where to install the submodule

    Even if url for submodule is provided explicitly -- first tries urls under
    parent's module tracking branch remote.
    """
    clone_urls = []
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    remote_name, remote_url = _get_tracking_source(ds)

    # Directly on parent's ds url
    if remote_url:
        # attempt: submodule checkout at parent remote URL
        # We might need to quote sm_path portion, e.g. for spaces etc
        if isinstance(RI(remote_url), URL):
            sm_path_url = urlquote(sm_path)
        else:
            sm_path_url = sm_path

        clone_urls.extend(
            _get_flexible_source_candidates(
                # alternate suffixes are tested by `clone` anyways
                sm_path_url, remote_url, alternate_suffix=False))

    # attempt: provided (configured?) submodule URL
    # TODO: consider supporting DataLadRI here?  or would confuse
    #  git and we wouldn't want that (i.e. not allow pure git clone
    #  --recursive)
    if sm_url:
        clone_urls += _get_flexible_source_candidates(
            sm_url,
            remote_url if remote_url else ds.path,
            alternate_suffix=False)

    return unique(clone_urls)


def _install_subds_from_flexible_source(
        ds, sm_path, sm_url, reckless, description=None):
    """Tries to obtain a given subdataset from several meaningful locations"""
    # TODO remove this assertion eventually, for now it assures intented
    # usage of this helper function
    assert(sm_path in ds.subdatasets(recursive=False, result_xfm='relpaths'))

    # compose a list of candidate clone URLs
    clone_urls = _get_flexible_source_candidates_for_submodule(
        ds, sm_path, sm_url)

    # prevent inevitable exception from `clone`
    dest_path = opj(ds.path, sm_path)
    clone_urls = [src for src in clone_urls if src != dest_path]

    # now loop over all candidates and try to clone
    subds = None
    try:
        subds = Clone.__call__(
            clone_urls[0],
            path=dest_path,
            # pretend no parent -- we don't want clone to add to ds
            # because this is a submodule already!
            dataset=None,
            reckless=reckless,
            # if we have more than one source, pass as alternatives
            alt_sources=clone_urls[1:],
            description=description,
            result_xfm='datasets',
            # not really need, but should protect against future RF
            on_failure='stop',
            result_renderer='disabled',
            return_type='item-or-list')
        # failure will raise an exception, hence if we got here we can
        # leave the loop and have a successful clone
    except IncompleteResultsError:
        # details of the failure are logged already by common code
        pass
    if subds is None:
        raise InstallFailedError(
            msg="Failed to install dataset from{}: {}".format(
                ' any of' if len(clone_urls) > 1 else '',
                clone_urls))

    assert(subds.is_installed())
    _fixup_submodule_dotgit_setup(ds, sm_path)

    # do fancy update
    lgr.debug("Update cloned subdataset {0} in parent".format(subds))
    # TODO: move all of that into update_submodule ??
    # TODO: direct mode ramifications?
    # track branch originally cloned
    subrepo = subds.repo
    branch = subrepo.get_active_branch()
    branch_hexsha = subrepo.get_hexsha(branch)
    ds.repo.update_submodule(sm_path, init=True)
    updated_branch = subrepo.get_active_branch()
    if branch and not updated_branch:
        # got into 'detached' mode
        # trace if current state is a predecessor of the branch_hexsha
        lgr.debug(
            "Detected detached HEAD after updating submodule %s which was "
            "in %s branch before", subds.path, branch)
        detached_hexsha = subrepo.get_hexsha()
        if subrepo.get_merge_base(
                [branch_hexsha, detached_hexsha]) == detached_hexsha:
            # TODO: config option?
            # in all likely event it is of the same branch since
            # it is an ancestor -- so we could update that original branch
            # to point to the state desired by the submodule, and update
            # HEAD to point to that location
            lgr.info(
                "Submodule HEAD got detached. Resetting branch %s to point "
                "to %s. Original location was %s",
                branch, detached_hexsha[:8], branch_hexsha[:8]
            )
            branch_ref = 'refs/heads/%s' % branch
            subrepo.update_ref(branch_ref, detached_hexsha)
            assert(subrepo.get_hexsha(branch) == detached_hexsha)
            subrepo.update_ref('HEAD', branch_ref, symbolic=True)
            assert(subrepo.get_active_branch() == branch)
        else:
            lgr.warning(
                "%s has a detached HEAD since cloned branch %s has another common ancestor with %s",
                subrepo.path, branch, detached_hexsha[:8]
            )
    return subds


def _install_necessary_subdatasets(
        ds, path, reckless, refds_path, description=None):
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
    """
    # figuring out what dataset to start with, --contains limits --recursive
    # to visit only subdataset on the trajectory to the target path
    subds_trail = ds.subdatasets(contains=path, recursive=True)
    if not subds_trail:
        # there is not a single known subdataset (installed or not)
        # for this path -- job done
        return
    # otherwise we start with the one deepest down
    cur_subds = subds_trail[-1]

    while not GitRepo.is_valid_repo(cur_subds['path']):
        # install using helper that give some flexibility regarding where to
        # get the module from
        try:
            sd = _install_subds_from_flexible_source(
                Dataset(cur_subds['parentds']),
                relpath(cur_subds['path'], start=cur_subds['parentds']),
                cur_subds['gitmodule_url'],
                reckless,
                description=description)
        except Exception as e:
            # skip all of downstairs, if we didn't manage to install subdataset
            yield get_status_dict(
                'install', path=cur_subds['path'], type='dataset',
                status='error', logger=lgr, refds=refds_path,
                message=("Installation of subdatasets %s failed with exception: %s",
                         cur_subds['path'], exc_str(e)))
            return

        # report installation, whether it helped or not
        yield get_status_dict(
            'install', ds=sd, status='ok', logger=lgr, refds=refds_path,
            message=("Installed subdataset in order to get %s", path))

        # now check whether the just installed subds brought us any closer to
        # the target path
        subds_trail = sd.subdatasets(contains=path, recursive=False)
        if not subds_trail:
            # no (newly available) subdataset get's us any closer
            return
        # next round
        cur_subds = subds_trail[-1]


def _recursive_install_subds_underneath(ds, recursion_limit, reckless, start=None,
                                        refds_path=None, description=None):
    if isinstance(recursion_limit, int) and recursion_limit <= 0:
        return
    # install using helper that give some flexibility regarding where to
    # get the module from
    for sub in ds.subdatasets(
            return_type='generator', result_renderer='disabled'):
        subds = Dataset(sub['path'])
        if start is not None and not subds.path.startswith(_with_sep(start)):
            # this one we can ignore, not underneath the start path
            continue
        if sub['state'] != 'absent':
            # dataset was already found to exist
            yield get_status_dict(
                'install', ds=subds, status='notneeded', logger=lgr,
                refds=refds_path)
            # do not continue, even if an intermediate dataset exists it
            # does not imply that everything below it does too
        else:
            # try to get this dataset
            try:
                subds = _install_subds_from_flexible_source(
                    ds,
                    relpath(sub['path'], start=ds.path),
                    sub['gitmodule_url'],
                    reckless,
                    description=description)
                yield get_status_dict(
                    'install', ds=subds, status='ok', logger=lgr, refds=refds_path,
                    message=("Installed subdataset %s", subds), parentds=ds.path)
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
        description=location_description,
        reckless=reckless_opt,
        # git_opts=git_opts,
        # annex_opts=annex_opts,
        # annex_get_opts=annex_get_opts,
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
            description=None,
            reckless=False,
            #git_opts=None,
            #annex_opts=None,
            #annex_get_opts=None,
            jobs=None,
            verbose=False,
    ):
        # IMPLEMENTATION CONCEPT:
        #
        # 1. Sort the world into existing handles and the rest
        # 2. Try locate missing handles (obtain subdatasets along the way)
        # 3. Expand into subdatasets with recursion enables (potentially
        #    obtain even more subdatasets
        # 4. Shoot info of which handles to get in each subdataset to,
        #    git-annex, once at the very end

        refds_path = Interface.get_refds_path(dataset)
        if not (dataset or path):
            raise InsufficientArgumentsError(
                "Neither dataset nor target path(s) provided")
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path

        # remember which results we already reported, to avoid duplicates
        yielded_ds = []
        to_get = []
        unavailable_paths = []
        for ap in AnnotatePaths.__call__(
                path=path,
                dataset=refds_path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='get',
                # NOTE: Do not act upon unavailable paths yet! Done below after
                # testing which ones could be obtained
                unavailable_path_status='',
                nondataset_path_status='impossible',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # we know what to report already
                yield ap
                continue
            if ap.get('state', None) == 'absent' and ap.get('raw_input', False):
                # if this wasn't found, but directly requested, queue for further
                # exploration
                unavailable_paths.append(ap)
                continue
            if ap.get('type', None) == 'dataset' and \
                    GitRepo.is_valid_repo(ap['path']) and \
                    not ap['path'] == refds_path:
                # do not report what hasn't arived yet
                # also do not report the base dataset that is already
                # present -- no surprise
                yield dict(ap, status='notneeded', logger=lgr,
                           message='already installed')
                yielded_ds.append(ap['path'])
                ap['process_content'] = get_data
            to_get.append(ap)

        # explore the unknown
        for ap in sorted(unavailable_paths, key=lambda x: x['path']):
            lgr.debug("Investigate yet unavailable path %s", ap)
            # how close can we get?
            dspath = ap.get('parentds', get_dataset_root(ap['path']))
            if dspath is None:
                # nothing we can do for this path
                continue
            lgr.debug("Found containing dataset %s for path %s", dspath, ap['path'])
            ds = Dataset(dspath)
            # now actually obtain whatever is necessary to get to this path
            containing_ds = [dspath]
            for res in _install_necessary_subdatasets(
                    ds, ap['path'], reckless, refds_path, description=description):
                # yield immediately so errors could be acted upon outside, before
                # we continue
                if not (res['type'] == 'dataset' and res['path'] in yielded_ds):
                    # unless we reported on this dataset before
                    if res['type'] == 'dataset':
                        # make a record, recursive below might now want to report
                        # a 'notneeded'
                        yielded_ds.append(res['path'])
                    yield res
                # update to the current innermost dataset
                containing_ds.append(res['path'])

            if len(containing_ds) < 2:
                # no subdataset was installed, hence if the path was unavailable
                # before it still is, no need to bother git annex
                ap.update(status='impossible',
                          message='path does not exist')
                yield ap
                continue
            # important to only do the next for the innermost subdataset
            # as the `recursive` logic below relies on that!
            # set the correct parent, for a dataset this would be the second-last
            # reported subdataset
            ap.update(parentds=containing_ds[-1])
            if containing_ds[-1] == ap['path']:
                # the path actually refers to the last installed dataset
                ap.update(parentds=containing_ds[-2],
                          process_content=get_data,
                          type='dataset')
            to_get.append(ap)

        # results of recursive installation of yet undiscovered datasets
        rec_get = []
        if recursive and not recursion_limit == 'existing':
            # obtain any subdatasets underneath the paths given inside the
            # subdatasets that we know already exist
            # unless we do not want recursion into not-yet-installed datasets
            for ap in sorted(to_get, key=lambda x: x['path']):
                if ap['type'] not in ('dataset', 'directory') or not ap.get('raw_input', False):
                    # a non-directory cannot have content underneath
                    # also we do NOT want to recurse into anything that was specifically
                    # requested, to avoid duplication
                    continue
                subds = Dataset(ap['path'] if ap['type'] == 'dataset' else ap['parentds'])
                lgr.info(
                    "Installing %s%s recursively",
                    subds,
                    (" underneath %s" % ap['path']
                     if subds.path != ap['path']
                     else ""))
                for res in _recursive_install_subds_underneath(
                        subds,
                        # `ap['path']` was explicitly given as input
                        # we count recursions from the input, hence we
                        # can start with the full number
                        recursion_limit,
                        reckless,
                        start=ap['path'],
                        refds_path=refds_path,
                        description=description):
                    # yield immediately so errors could be acted upon
                    # outside, before we continue
                    if not (res['type'] == 'dataset' and res['path'] in yielded_ds):
                        # unless we reported on this dataset before
                        if res['type'] == 'dataset':
                            # make a record
                            yielded_ds.append(res['path'])
                    yield res
                    if not (res['status'] == 'ok' and res['type'] == 'dataset'):
                        # not a dataset that was just installed, we just reported it
                        # upstairs, and can ignore it from now on
                        continue
                    # paranoia, so popular these days...
                    assert GitRepo.is_valid_repo(res['path'])
                    # keep a copy of the install record for `get` later on
                    get_ap = {k: v for k, v in res.items()
                              if not k == 'status'}
                    get_ap['process_content'] = get_data
                    rec_get.append(get_ap)

        if not get_data:
            # done already
            return

        # merge the two AP lists
        to_get.extend(rec_get)

        # sort into datasets
        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_get,
                refds_path=refds_path,
                path_only=False)
        assert(not completed)

        # hand over to git-annex, get files content,
        # report files in git as 'notneeded' to get
        for ds_path in sorted(content_by_ds.keys()):
            ds = Dataset(ds_path)
            # grab content, ignore subdataset entries
            content = [ap['path'] for ap in content_by_ds[ds_path]
                       if ap.get('type', None) != 'dataset' or ap['path'] == ds.path]
            if not content:
                # cut this short should there be nothing
                continue
            # needs to be an annex to get content
            if not isinstance(ds.repo, AnnexRepo):
                for r in results_from_paths(
                        content, status='notneeded',
                        message="no dataset annex, content already present",
                        action='get', logger=lgr,
                        refds=refds_path):
                    yield r
                continue
            respath_by_status = {}
            for res in ds.repo.get(
                    content,
                    options=['--from=%s' % source] if source else [],
                    jobs=jobs):
                res = annexjson2result(res, ds, type='file', logger=lgr,
                                       refds=refds_path)
                success = success_status_map[res['status']]
                respath_by_status[success] = \
                    respath_by_status.get(success, []) + [res['path']]
                yield res

            for r in results_from_annex_noinfo(
                    ds,
                    content,
                    respath_by_status,
                    dir_fail_msg='could not get some content in %s %s',
                    noinfo_dir_msg='nothing to get from %s',
                    noinfo_file_msg='already present',
                    action='get',
                    logger=lgr,
                    refds=refds_path):
                yield r

    @staticmethod
    def custom_result_summary_renderer(res):
        from datalad.ui import ui
        from os import linesep
        if not len(res):
            ui.message("Got nothing new")
            return

        nfiles = count_results(res, type='file')
        nsuccess_file = count_results(res, type='file', status='ok')
        nfailure = nfiles - nsuccess_file
        msg = "Tried to get %d %s that had no content yet." % (
            nfiles, single_or_plural("file", "files", nfiles))
        if nsuccess_file:
            msg += " Successfully obtained %d. " % nsuccess_file
        if nfailure:
            msg += " %d (failed)." % (nfailure,)
        ui.message(msg)

        # if just a few or less than initially explicitly requested
        if len(res) < 10:
            msg = linesep.join([
                "{path}{type} ... {suc}".format(
                    suc=item.get('status'),
                    path=item.get('path'),
                    type=' [{}]'.format(item['type']) if 'type' in item else '')
                for item in res])
            ui.message(msg)
