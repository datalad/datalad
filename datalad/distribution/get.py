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

import os.path as op

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import (
    get_status_dict,
    results_from_paths,
    annexjson2result,
    count_results,
    success_status_map,
    results_from_annex_noinfo,
)
from datalad.interface.common_opts import (
    recursion_flag,
    location_description,
    jobs_opt,
    reckless_opt,
)
from datalad.interface.results import is_ok_dataset
from datalad.support.constraints import (
    EnsureInt,
    EnsureChoice,
    EnsureStr,
    EnsureNone,
)
from datalad.support.param import Parameter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import (
    GitRepo,
    _fixup_submodule_dotgit_setup,
)
from datalad.support.exceptions import (
    InsufficientArgumentsError,
)
from datalad.support.network import (
    URL,
    RI,
    urlquote,
)
from datalad.dochelpers import (
    single_or_plural,
)
from datalad.utils import (
    unique,
    Path,
)

from datalad.local.subdatasets import Subdatasets

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    rev_get_dataset_root,
)
from datalad.distribution.clone import Clone
from datalad.distribution.utils import _get_flexible_source_candidates

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.get')


def _get_flexible_source_candidates_for_submodule(ds, sm_path, sm_url=None):
    """Retrieve candidates from where to install the submodule

    Even if url for submodule is provided explicitly -- first tries urls under
    parent's module tracking branch remote.
    """
    clone_urls = []

    ds_repo = ds.repo

    # should be our first candidate
    tracking_remote, tracking_branch = ds_repo.get_tracking_branch()
    candidate_remotes = [tracking_remote] if tracking_remote else []

    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule
    try:
        last_commit = next(ds_repo._get_files_history(sm_path)).hexsha
        # ideally should also give preference to the remotes which have
        # the same branch checked out I guess
        candidate_remotes += list(ds_repo._get_remotes_having_commit(last_commit))
    except StopIteration:
        # no commit for it known yet, ... oh well
        pass

    for remote in unique(candidate_remotes):
        remote_url = ds_repo.get_remote_url(remote, push=False)

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
                    remote_url,
                    alternate_suffix=False
                )

    # Do based on the ds.path as the last resort
    if sm_url:
        clone_urls += _get_flexible_source_candidates(
            sm_url,
            ds.path,
            alternate_suffix=False)

    return unique(clone_urls)


def _install_subds_from_flexible_source(
        ds, sm_path, sm_url, reckless, description=None):
    """Tries to obtain a given subdataset from several meaningful locations"""
    # compose a list of candidate clone URLs
    clone_urls = _get_flexible_source_candidates_for_submodule(
        ds, sm_path, sm_url)

    # prevent inevitable exception from `clone`
    dest_path = op.join(ds.path, sm_path)
    clone_urls = [src for src in clone_urls if src != dest_path]

    if not clone_urls:
        # yield error
        yield get_status_dict(
            action='install',
            ds=ds,
            status='error',
            message=(
                "Have got no candidates to install subdataset %s from.",
                sm_path),
            logger=lgr,
        )
        return

    # now loop over all candidates and try to clone
    for res in Clone.__call__(
            clone_urls[0],
            path=dest_path,
            # pretend no parent -- we don't want clone to add to ds
            # because this is a submodule already!
            dataset=None,
            reckless=reckless,
            # if we have more than one source, pass as alternatives
            alt_sources=clone_urls[1:],
            description=description,
            result_xfm=None,
            # we yield all an have the caller decide
            on_failure='ignore',
            result_renderer='disabled',
            return_type='generator'):
        yield res

    subds = Dataset(dest_path)
    if not subds.is_installed():
        lgr.debug('Desired subdataset %s did not materialize, stopping', subds)
        return

    _fixup_submodule_dotgit_setup(ds, sm_path)

    # do fancy update
    lgr.debug("Update cloned subdataset {0} in parent".format(subds))
    # TODO: move all of that into update_submodule ??
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
    subds_trail = ds.subdatasets(contains=path, recursive=True,
                                 on_failure="ignore",
                                 result_filter=is_ok_dataset)
    if not subds_trail:
        # there is not a single known subdataset (installed or not)
        # for this path -- job done
        return
    # otherwise we start with the one deepest down
    cur_subds = subds_trail[-1]

    while not GitRepo.is_valid_repo(cur_subds['path']):
        # install using helper that give some flexibility regarding where to
        # get the module from
        for res in _install_subds_from_flexible_source(
                Dataset(cur_subds['parentds']),
                op.relpath(cur_subds['path'], start=cur_subds['parentds']),
                cur_subds['gitmodule_url'],
                reckless,
                description=description):
            if res.get('action', None) == 'install':
                if res['status'] == 'ok':
                    # report installation, whether it helped or not
                    res['message'] = (
                        "Installed subdataset in order to get %s",
                        str(path))
                    # next subdataset candidate
                    sd = Dataset(res['path'])
                    yield res
                elif res['status'] in ('impossible', 'error'):
                    yield res
                    # we cannot go deeper, we need to stop
                    return
                else:
                    # report unconditionally to caller
                    yield res

        # now check whether the just installed subds brought us any closer to
        # the target path
        subds_trail = sd.subdatasets(contains=path, recursive=False,
                                     on_failure='ignore',
                                     result_filter=is_ok_dataset)
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
            path=start,
            return_type='generator',
            result_renderer='disabled'):
        subds = Dataset(sub['path'])
        if sub.get('gitmodule_datalad-recursiveinstall', '') == 'skip':
            lgr.debug(
                "subdataset %s is configured to be skipped on recursive installation",
                sub['path'])
            continue
        if sub.get('state', None) != 'absent':
            # dataset was already found to exist
            yield get_status_dict(
                'install', ds=subds, status='notneeded', logger=lgr,
                refds=refds_path)
            # do not continue, even if an intermediate dataset exists it
            # does not imply that everything below it does too
        else:
            # try to get this dataset
            for res in _install_subds_from_flexible_source(
                    ds,
                    op.relpath(sub['path'], start=ds.path),
                    sub['gitmodule_url'],
                    reckless,
                    description=description):
                # yield everything to let the caller decide how to deal with
                # errors
                yield res
        # recurse
        # we can skip the start expression, we know we are within
        for res in _recursive_install_subds_underneath(
                subds,
                recursion_limit=recursion_limit - 1 if isinstance(recursion_limit, int) else recursion_limit,
                reckless=reckless,
                refds_path=refds_path):
            yield res


def _install_targetpath(
        ds,
        target_path,
        recursive,
        recursion_limit,
        reckless,
        refds_path,
        description):
    """Helper to install as many subdatasets as needed to verify existence
    of a target path

    Parameters
    ==========
    ds : Dataset
      Locally available dataset that contains the target path
    target_path : Path
    """
    # if it is an empty dir, it could still be a subdataset that is missing
    if (target_path.is_dir() and any(target_path.iterdir())) or \
            (not target_path.is_dir()
             and (target_path.is_symlink() or target_path.exists())):
        yield dict(
            action='get',
            type='dataset',
            # this cannot just be the dataset path, as the original
            # situation of datasets avail on disk can have changed due
            # to subdataset installation. It has to be actual subdataset
            # it resides in, because this value is used to determine which
            # dataset to call `annex-get` on
            # TODO stringification is a PY35 compatibility kludge
            path=rev_get_dataset_root(str(target_path)),
            status='notneeded',
            contains=[target_path],
            refds=refds_path,
        )
    else:
        # we don't have it yet. is it in a subdataset?
        for res in _install_necessary_subdatasets(
                ds, target_path, reckless, refds_path, description=description):
            if (target_path.is_symlink() or target_path.exists()):
                # this dataset brought the path, mark for annex
                # processing outside
                res['contains'] = [target_path]
            # just spit it out
            yield res
        if not (target_path.is_symlink() or target_path.exists()):
            # looking for subdatasets did not help -> all hope is lost
            yield dict(
                action='get',
                path=str(target_path),
                status='impossible',
                refds=refds_path,
                message='path does not exist',
            )
            return
    # we have the target path
    if not (recursive
            #and not recursion_limit == 'existing' \
            and target_path.is_dir()):
        # obtain any subdatasets underneath the paths given
        # a non-directory cannot have content underneath
        return
    if recursion_limit == 'existing':
        for res in ds.subdatasets(
                fulfilled=True,
                path=target_path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator'):
            res.update(
                contains=[Path(res['path'])],
                action='get',
                status='notneeded',
            )
            yield res
        return
    lgr.info(
        "Installing %s%s recursively",
        ds,
        (" underneath %s" % target_path
         if ds.path != target_path
         else ""))
    for res in _recursive_install_subds_underneath(
            ds,
            # target_path was explicitly given as input
            # we count recursions from the input, hence we
            # can start with the full number
            recursion_limit,
            reckless,
            # TODO keep Path when RF is done
            start=str(target_path),
            refds_path=refds_path,
            description=description):
        # yield immediately so errors could be acted upon
        # outside, before we continue
        res.update(
            action='get',
            contains=[Path(res['path'])],
        )
        yield res


def _get_targetpaths(ds, content, refds_path, source, jobs):
    # not ready for Path instances...
    content = [str(c) for c in content]
    # hand over to git-annex, get files content,
    # report files in git as 'notneeded' to get
    ds_repo = ds.repo
    # needs to be an annex to get content
    if not isinstance(ds_repo, AnnexRepo):
        for r in results_from_paths(
                content, status='notneeded',
                message="no dataset annex, content already present",
                action='get', logger=lgr,
                refds=refds_path):
            yield r
        return
    respath_by_status = {}
    for res in ds_repo.get(
            content,
            options=['--from=%s' % source] if source else [],
            jobs=jobs):
        res = annexjson2result(res, ds, type='file', logger=lgr,
                               refds=refds_path)
        success = success_status_map[res['status']]
        # TODO: in case of some failed commands (e.g. get) there might
        # be no path in the record.  yoh has only vague idea of logic
        # here so just checks for having 'path', but according to
        # results_from_annex_noinfo, then it would be assumed that
        # `content` was acquired successfully, which is not the case
        if 'path' in res:
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
            args=("-R", "--recursion-limit",),
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
        jobs=jobs_opt)

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
            jobs='auto',
    ):
        refds_path = Interface.get_refds_path(dataset)
        if not (dataset or path):
            raise InsufficientArgumentsError(
                "Neither dataset nor target path(s) provided")
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path

        # we have to have a single dataset to operate on
        refds = require_dataset(
            dataset, check_installed=True, purpose='get content')

        content_by_ds = {}
        # use subdatasets() to discover any relevant content that is not
        # already present in the root dataset (refds)
        for sdsres in Subdatasets.__call__(
                contains=path,
                # maintain path argument semantics and pass in dataset arg
                # as is
                dataset=dataset,
                # always come from the top to get sensible generator behavior
                bottomup=False,
                # when paths are given, they will constrain the recursion
                # automatically, and we need to enable recursion so we can
                # location path in subdatasets several levels down
                recursive=True if path else recursive,
                recursion_limit=None if path else recursion_limit,
                return_type='generator',
                on_failure='ignore'):
            if sdsres.get('type', None) != 'dataset':
                # if it is not about a 'dataset' it is likely content in
                # the root dataset
                if sdsres.get('status', None) == 'impossible' and \
                        sdsres.get('message', None) == \
                        'path not contained in any matching subdataset':
                    target_path = Path(sdsres['path'])
                    if refds.pathobj != target_path and \
                            refds.pathobj not in target_path.parents:
                        yield dict(
                            action='get',
                            path=str(target_path),
                            status='error',
                            message=('path not associated with dataset',
                                     refds),
                        )
                        continue
                    # check if we need to obtain anything underneath this path
                    # the subdataset() call above will only look _until_ it
                    # hits the targetpath
                    for res in _install_targetpath(
                            refds,
                            Path(sdsres['path']),
                            recursive,
                            recursion_limit,
                            reckless,
                            refds_path,
                            description):
                        # fish out the datasets that 'contains' a targetpath
                        # and store them for later
                        if res.get('status', None) in ('ok', 'notneeded') and \
                                'contains' in res:
                            dsrec = content_by_ds.get(res['path'], set())
                            dsrec.update(res['contains'])
                            content_by_ds[res['path']] = dsrec
                        if res.get('status', None) != 'notneeded':
                            # all those messages on not having installed anything
                            # are a bit pointless
                            # "notneeded" for annex get comes below
                            yield res
                else:
                    # dunno what this is, send upstairs
                    yield sdsres
                # must continue for both conditional branches above
                # the rest is about stuff in real subdatasets
                continue
            # instance of the closest existing dataset for this result
            ds = Dataset(sdsres['parentds']
                         if sdsres.get('state', None) == 'absent'
                         else sdsres['path'])
            assert 'contains' in sdsres
            # explore the unknown
            for target_path in sdsres.get('contains', []):
                # essentially the same as done above for paths in the root
                # dataset, but here we are starting from the closest
                # discovered subdataset
                for res in _install_targetpath(
                        ds,
                        Path(target_path),
                        recursive,
                        recursion_limit,
                        reckless,
                        refds_path,
                        description):
                    if res.get('status', None) in ('ok', 'notneeded') and \
                            'contains' in res:
                        dsrec = content_by_ds.get(res['path'], set())
                        dsrec.update(res['contains'])
                        content_by_ds[res['path']] = dsrec
                    if res.get('status', None) != 'notneeded':
                        # all those messages on not having installed anything
                        # are a bit pointless
                        # "notneeded" for annex get comes below
                        yield res

        if not get_data:
            # done already
            return

        # and now annex-get, this could all be done in parallel now
        for ds, content in content_by_ds.items():
            for res in _get_targetpaths(
                    Dataset(ds),
                    content,
                    refds.path,
                    source,
                    jobs):
                yield res

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
