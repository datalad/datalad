# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dropping dataset content

"""

__docformat__ = 'restructuredtext'

import logging
from itertools import chain

from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import (
    annexjson2result,
    success_status_map,
    results_from_annex_noinfo,
)
from datalad.interface.utils import (
    eval_results,
)
from datalad.utils import (
    ensure_list,
    rmtree,
)
from datalad.core.local.status import get_paths_by_ds
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CapturedException
from datalad.runner.exception import CommandError

lgr = logging.getLogger('datalad.distributed.drop')


@build_doc
class Drop(Interface):
    """DOCUMENT ME
    """
    _examples_ = [
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform the drop on.
            If no dataset is given, the current working directory is used
            as operation context""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path of the component to be dropped",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        reckless=Parameter(
            args=("--reckless",),
            doc="""""",
            constraints=EnsureChoice(
                'modification', 'availability', 'undead', None)),
        what=Parameter(
            args=("--what",),
            doc="""""",
            # add 'unwanted'
            constraints=EnsureChoice('filecontent', 'allkeys', 'all')),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        jobs=jobs_opt,
        check=Parameter(
            args=("--nocheck",),
            doc="""DEPRECATED: use '--reckless availability'""",
            action="store_false",
            dest='check'),
        if_dirty=Parameter(
            args=("--if-dirty",),
            doc="""DEPRECATED: use --reckless instead""",
            constraints=EnsureChoice('fail', 'save-before', 'ignore', None)),
    )

    @staticmethod
    @datasetmethod(name='drop')
    @eval_results
    def __call__(
            path=None,
            what='filecontent',
            reckless=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            jobs=None,
            # deprecated
            check=None,
            # TODO deal with deprecation
            if_dirty=None):

        # TODO deprecation warning on `check`
        if check is False:
            # TODO check for conflict with new reckless parameter
            reckless = 'availability'

        # we cannot test for what=='allkeys' and path==None here,
        # on per each dataset. otherwise we will not be able to drop
        # from a subdataset, by given its path -- desirable MIH thinks

        ds = require_dataset(dataset, check_installed=True, purpose='drop')

        res_props = dict(
            logger=lgr,
            refds=ds.path,
        )
        # if not paths are given, there will still be a single dataset record
        # with paths==None
        paths_by_ds, errors = get_paths_by_ds(
            ds,
            dataset,
            ensure_list(path),
            # XXX this needs more though!! Maybe this is what the mode should be
            # in general?!
            # when we want to drop entire datasets, it is much more useful
            # to have subdatasets be their own record
            subdsroot_mode='sub' if what == 'all' else 'rsync',
        )
        for e in errors:
            yield dict(
                action='drop',
                path=str(e),
                status='error',
                message=('path not underneath the reference dataset %s', ds),
                **res_props)
            # we are not returning, a caller could decide on failure mode

        if what == 'all':
            cwd = ds.pathobj.cwd()
            if any(d == cwd or d in cwd.parents for d in paths_by_ds.keys()):
                raise RuntimeError(
                    'refuse to perform actions that would remove the current '
                    'working directory')

        lgr.debug('Discovered %i datasets to drop (from)', len(paths_by_ds))

        # a dataset paths are normalized and guaranteed to be under the same
        # root dataset
        # we want to start from the leave datasets, such that all discovered
        # dataset can be processed independently
        for dpath in sorted(paths_by_ds.keys(), reverse=True):
            d = Dataset(dpath)
            lgr.debug('Starting to drop %s at %s', what, d)
            for res in _drop_dataset(
                    d,
                    paths_by_ds[dpath],
                    what=what,
                    reckless=reckless,
                    # recursion from any of the given paths!
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    jobs=jobs):
                yield dict(res, **res_props)
            lgr.debug('Finished dropping %s at %s', what, d)
        return


def _drop_dataset(ds, paths, what, reckless, recursive, recursion_limit, jobs):
    # we know that any given path is part of `ds` and not any of its
    # subdatasets!

    if recursive:
        # process subdatasets first with recursion
        for sub in ds.subdatasets(
                # must be resolved!
                path=paths or None,
                # nothing to drop with unavailable subdatasets
                fulfilled=True,
                # we can use the full recursion depth, only the first layer
                # of calls to _drop_dataset() must/can have recursive=True
                recursive=recursive,
                recursion_limit=recursion_limit,
                # start reporting with the leaves
                bottomup=True,
                result_xfm='datasets',
                on_failure='ignore',
                result_renderer='disabled'):
            yield from _drop_dataset(
                ds=sub,
                # everything, the entire subdataset is matching a given path
                paths=None,
                what=what,
                reckless=reckless,
                recursive=False,
                recursion_limit=None,
                jobs=jobs)

    repo = ds.repo
    is_annex = isinstance(repo, AnnexRepo)

    # first critical checks that might prevent further operation
    had_fatality = False
    for res in _fatal_pre_drop_checks(
            ds, repo, paths, what, reckless, is_annex):
        had_fatality = True
        yield res
    if had_fatality:
        return

    # now conditional/informative checks
    yield from _pre_drop_checks(ds, repo, paths, what, reckless, is_annex)

    if is_annex and what == 'filecontent':
        # XXX should we only drop filecontent with particular paths
        # specified? e.g. '.'
        # MIH: right now I don't think so, because running drop without
        # should be safe by default in the end
        yield from _drop_files(
            ds,
            repo,
            # give paths or '.' with no constraint
            paths=[str(p.relative_to(ds.pathobj))
                   for p in paths] if paths else '.',
            force=reckless in ('availability',),
            jobs=jobs,
        )
        # end it here for safety, the rest of the function deals with
        # dropping more and more fundamentally
        return

    drop_all_errored = False
    if is_annex and what in ('allkeys', 'all'):
        # XXX maybe conditional on a reckless mode, i.e. kill
        for r in _drop_allkeys(
                ds,
                repo,
                force=reckless in ('availability',),
                jobs=jobs):
            res = dict(
                action='drop',
                type='key',
                # use the path of the containing dataset
                # using the location of the key does not add any
                # practical value, and is expensive to obtain
                path=ds.path,
                status='ok' if r.get('success') else 'error',
                key=r.get('key'),
            )
            # pull any note, and rename recommended parameter to
            # avoid confusion
            message = r.get('note', '').replace('--force', '--reckless')
            if message:
                res['message'] = message
            error_messages = r.get('error-messages')
            if error_messages:
                res['error_messages'] = error_messages
            # play safe, if there is no status, assume error
            if res.get('status', 'error') != 'ok':
                drop_all_errored = True
            yield res

    if drop_all_errored:
        # end it here, if there is any indication that wiping out the
        # repo is unsafe
        return

    if what == 'all':
        if reckless == 'noavailability':
            # wipe out dataset
            return
        # kill repository
        yield from _uninstall_dataset(ds)
    return


def _fatal_pre_drop_checks(ds, repo, paths, what, reckless, is_annex):
    if what in ('allkeys', 'all') and paths is not None and paths != [ds.pathobj]:
        yield dict(
            action='drop',
            path=ds.path,
            type='dataset',
            status='impossible',
            message=(
                'cannot drop %s, with path constraints given: %s',
                what, paths),
        )
        return

    if what == 'all':
        # we must not have subdatasets anymore
        # if we do, --recursive was forgotton
        subdatasets = ds.subdatasets(
            # we only care about the present ones
            fulfilled=True,
            # first-level is enough, if that has none, there will be none
            recursive=False,
            result_xfm='paths',
            result_renderer='disabled')
        if subdatasets:
            yield dict(
                action='drop',
                path=ds.path,
                type='dataset',
                status='error',
                message=('cannot drop dataset, subdataset(s) still present '
                         '(forgot --recursive?): %s', subdatasets)
            )
            # this is fatal
            return

    if what == 'all' and reckless != 'availability':
        unpushed = _detect_unpushed_revs(repo)
        if unpushed:
            yield dict(
                action='drop',
                path=ds.path,
                type='dataset',
                status='error',
                message=(
                    "to-be-dropped dataset has the following revisions that "
                    "are not available at any known sibling. Use "
                    "`datalad push --to ...` to push "
                    "these before dropping the local dataset, "
                    "or ignore via `--reckless availability`: %s",
                    unpushed)
            )
            # this is fatal
            return

    if is_annex and what == 'all' and reckless != 'undead':
        # this annex is about to die, test if it is still considered
        # not-dead. if so, complain to avoid generation of zombies
        # (annexed that are floating around, but are actually dead).
        remotes_that_know_this_annex = [
            r
            for r in _detect_nondead_annex_at_remotes(repo, repo.uuid)
            # filter out "here"
            if r is not None
        ]
        if remotes_that_know_this_annex:
            yield dict(
                action='drop',
                path=ds.path,
                type='dataset',
                status='error',
                message=(
                    "to-be-deleted local annex not declared 'dead' at the "
                    "following siblings. Announce death "
                    "(`git annex dead here` + `datalad push --to ...`), "
                    "or ignore via `--reckless undead`: %s",
                    remotes_that_know_this_annex)
            )
            # this is fatal
            return

    if reckless not in ('modification',):
        # do a cheaper status run to discover any kind of modification and
        # generate results based on the `what` mode of operation
        for res in ds.status(
                path=paths,
                # untracked content will not be reported on further down
                # must catch it here
                untracked='normal',
                # downstream code can handle non-annex/annex distinction
                # avoid expensive evaluation here
                annex=False,
                # we only need to inspect a subdataset's state in case
                # we want to drop it completely
                eval_subdataset_state='commit' if what in ('all',) else 'no',
                # recursion is handled outside this function
                recursive=False,
                result_renderer='disabled',
                on_failure='ignore'):
            state = res.get('state')
            if state == 'clean':
                # nothing to worry about, nothing to communicate
                continue
            elif state in ('modified', 'untracked'):
                yield dict(
                    res,
                    status='impossible',
                    action='drop',
                    message=f'cannot drop {state} content, save first',
                )
                # we are not aborting nevetheless. in normal conditions
                # the above result will stop processing, but if desired
                # we could go on
            else:
                lgr.debug(
                    'Status record not considered for drop '
                    'state inspection: %s', res)


def _pre_drop_checks(ds, repo, paths, what, reckless, is_annex):
    if not is_annex and paths:
        # we cannot drop content in non-annex repos, issue same
        # 'notneeded' as for git-file in annex repo
        for p in paths:
            yield dict(
                action='drop',
                path=str(p),
                status='notneeded',
                message="no annex'ed content",
            )
        # continue, this is nothing fatal

    if not is_annex and what in ('allkeys', 'unwanted'):
        # these drop modes are meaningless without an annex
        yield dict(
            action='drop',
            path=ds.path,
            status='notneeded',
            message="dataset with no annex",
            type='dataset',
        )
        # continue, this is nothing fatal


def _detect_unpushed_revs(repo):
    """Check if all local branch states (and HEAD) are available at a remote

    There need not be a 1:1 correspondence. What is tested is whether
    each commit corresponding to a local branch tip (or HEAD), is also an
    ancestor of any remote branch. It is not required that there is a single
    remote that has all commits.

    This only uses the state of remotes known to the local remote state.
    No remote synchronization is performed.

    Parameters
    ----------
    repo: GitRepo
      Repository to evaluated

    Returns
    -------
    list
      Names of local states/refs that are no available at a remote.
    """
    # we do not want to check this for the managed git-annex branch
    # it can behave in complex ways
    local_refs = [lb for lb in repo.get_branches() if lb != 'git-annex']
    if not repo.get_active_branch():
        # check for HEAD, in case we are on a detached HEAD
        local_refs.append('HEAD')
    # extend to tags?
    remote_refs = repo.get_remote_branches()

    unpushed_refs = [
        local_ref
        for local_ref in local_refs
        if not any(repo.is_ancestor(local_ref, remote_ref)
                   for remote_ref in remote_refs)
    ]
    return unpushed_refs


def _detect_nondead_annex_at_remotes(repo, annex_uuid):
    """Return list of remote names that know about a given (not-dead) annex

    This only uses the state of remotes known to the local remote state.
    No remote synchronization is performed.

    Parameters
    ----------
    repo: AnnexRepo or GitRepo
      Repository to evaluated
    annex_uuid: str
      UUID string of a particular annex

    Returns
    -------
    list
      Names of any matching remote, the local repository is indicated using
      a `None` label.
    """
    # build the refs for all remotes and local
    remotes_w_registration = []
    for remote in chain([''], repo.get_remotes()):
        refprefix = '{}{}git-annex:'.format(
            remote,
            '/' if remote else '',
        )
        uuid_known = False
        try:
            for line in repo.call_git_items_(
                    ['cat-file', '-p', refprefix + 'uuid.log']):
                if line.startswith(annex_uuid):
                    # use None to label the local repo
                    uuid_known = True
                    break
        except CommandError as e:
            CapturedException(e)
            # this is not a problem per-se, logged above, just continue
            continue
        if not uuid_known:
            # if an annex id is not even in the uuid.log, we can stop here
            # (for this remote)
            continue

        # annex is known, but maybe is declared dead already, must check
        # trust.log in addition
        try:
            for line in repo.call_git_items_(
                    ['cat-file', '-p', refprefix + 'trust.log']):
                columns = line.split()
                if columns[0] == annex_uuid:
                    # not known if dead
                    uuid_known = False if columns[1] == 'X' else True
                    break
        except CommandError as e:
            CapturedException(e)
            # this is not a problem per-se, logged above, just continue
            continue
        finally:
            if uuid_known:
                remotes_w_registration.append(remote or None)
    return(remotes_w_registration)


def _uninstall_dataset(ds):
    """This is a harsh internal helper: it will wipe out a dataset, no checks
    """
    # figure out whether we should be nice to a superdataset later on
    has_super = ds.get_superdataset(topmost=False, registered_only=True)
    # Close any possibly associated process etc with underlying repo.
    # Otherwise - rmtree could fail to remove e.g. under NFS which would
    # still have some files opened by them (thus having .nfs00000xxxx
    # files) forbidding rmdir to work in rmtree
    ds.close()
    rmtree(ds.path)
    # invalidate loaded ConfigManager -- datasets are singletons!!
    ds._cfg = None
    if has_super:
        # recreate an empty mountpoint to make Git happier
        ds.pathobj.mkdir(exist_ok=True)
    yield dict(
        action='drop',
        path=ds.path,
        type='dataset',
        status='ok',
    )


def _drop_allkeys(ds, repo, force=False, jobs=None):
    """
    """
    cmd = ['drop', '--all']
    if force:
        cmd.append('--force')
    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    try:
        yield from repo._call_annex_records(cmd)
    except CommandError as e:
        # pick up the results captured so far and yield them
        # the error will be amongst them
        yield from e.kwargs.get('stdout_json', [])


def _drop_files(ds, repo, paths, force=False, jobs=None):
    """Helper to drop content in datasets.

    Parameters
    ----------
    repo : AnnexRepo
    paths : list
      for which files to drop content
    check : bool
      whether to instruct annex to perform minimum copy availability
      checks

    Yields
    ------
    dict
    """
    cmd = ['drop']
    if force:
        cmd.append('--force')
    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    respath_by_status = {}
    try:
        yield from (
            _postproc_annexdrop_result(res, respath_by_status, ds)
            for res in repo._call_annex_records(cmd, files=paths)
        )
    except CommandError as e:
        # pick up the results captured so far and yield them
        # the error will be amongst them
        yield from (
            _postproc_annexdrop_result(res, respath_by_status, ds)
            for res in e.kwargs.get('stdout_json', [])
        )
    # report on things requested that annex was silent about
    for r in results_from_annex_noinfo(
            ds, paths, respath_by_status,
            dir_fail_msg='could not drop some content in %s %s',
            noinfo_dir_msg='nothing to drop from %s',
            noinfo_file_msg="no annex'ed content"):
        r['action'] = 'drop'
        yield r


def _postproc_annexdrop_result(res, respath_by_status, ds, **kwargs):
    # TODO this should extract any error messages and report them!
    res = annexjson2result(
        # annex reports are always about files
        res, ds, type='file', **kwargs)
    success = success_status_map[res['status']]
    respath_by_status[success] = \
        respath_by_status.get(success, []) + [res['path']]
    if res["status"] == "error" and res["action"] == "drop":
        msg = res["message"]
        if isinstance(msg, str) and "Use --force to" in msg:
            # Avoid confusing datalad-drop callers with git-annex-drop's
            # suggestion to use --force.
            # Just mention reckless itself, do not go into the details
            # of which mode. This is likely changing over time and
            # adjusting this replacement will be forgotten.
            res["message"] = msg.replace("--force", "--reckless")
    return res


