# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import warnings
from itertools import chain

from datalad.core.local.status import get_paths_by_ds
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import (
    annexjson2result,
    results_from_annex_noinfo,
    success_status_map,
)
from datalad.runner.exception import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CapturedException
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    rmtree,
)

lgr = logging.getLogger('datalad.distributed.drop')


@build_doc
class Drop(Interface):
    """Drop content of individual files or entire (sub)datasets

    This command is the antagonist of 'get'. It can undo the retrieval of file
    content, and the installation of subdatasets.

    Dropping is a safe-by-default operation. Before dropping any information,
    the command confirms the continued availability of file-content (see e.g.,
    configuration 'annex.numcopies'), and the state of all dataset branches
    from at least one known dataset sibling. Moreover, prior removal of an
    entire dataset annex, that it is confirmed that it is no longer marked
    as existing in the network of dataset siblings.

    Importantly, all checks regarding version history availability and local
    annex availability are performed using the current state of remote
    siblings as known to the local dataset. This is done for performance
    reasons and for resilience in case of absent network connectivity. To
    ensure decision making based on up-to-date information, it is advised to
    execute a dataset update before dropping dataset components.
    """
    _examples_ = [
        {'text': "Drop single file content",
         'code_py': "drop('path/to/file')",
         'code_cmd': "datalad drop <path/to/file>"},
        {'text': "Drop all file content in the current dataset",
         'code_py': "drop('.')",
         'code_cmd': "datalad drop"},
        {'text': "Drop all file content in a dataset and all its subdatasets",
         'code_py': "drop(dataset='.', recursive=True)",
         'code_cmd': "datalad drop -d <path/to/dataset> -r"},
        {'text': "Disable check to ensure the configured minimum number of "
                 "remote sources for dropped data",
         'code_py': "drop(path='path/to/content', reckless='availability')",
         'code_cmd': "datalad drop <path/to/content> --reckless availability"},
        {'text': 'Drop (uninstall) an entire dataset '
                 '(will fail with subdatasets present)',
         'code_py': "drop(what='all')",
         'code_cmd': "datalad drop --what all"},
        {'text': 'Kill a dataset recklessly with any existing subdatasets too'
                 '(this will be fast, but will disable any and all safety '
                 'checks)',
         'code_py': "drop(what='all', reckless='kill', recursive=True)",
         'code_cmd': "datalad drop --what all, --reckless kill --recursive"},
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar="DATASET",
            doc="""specify the dataset to perform drop from.
            If no dataset is given, the current working directory is used
            as operation context""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path of a dataset or dataset component to be dropped",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        reckless=Parameter(
            args=("--reckless",),
            doc="""disable individual or all data safety measures that would
            normally prevent potentially irreversible data-loss.
            With 'modification', unsaved modifications in a dataset will not be
            detected. This improves performance at the cost of permitting
            potential loss of unsaved or untracked dataset components.
            With 'availability', detection of dataset/branch-states that are
            only available in the local dataset, and detection of an
            insufficient number of file-content copies will be disabled.
            Especially the latter is a potentially expensive check which might
            involve numerous network transactions.
            With 'undead', detection of whether a to-be-removed local annex is
            still known to exist in the network of dataset-clones is disabled.
            This could cause zombie-records of invalid file availability.
            With 'kill', all safety-checks are disabled.""",
            constraints=EnsureChoice(
                'modification', 'availability', 'undead', 'kill', None)),
        what=Parameter(
            args=("--what",),
            doc="""select what type of items shall be dropped.
            With 'filecontent', only the file content (git-annex keys) of files
            in a dataset's worktree will be dropped.
            With 'allkeys', content of any version of any file in any branch
            (including, but not limited to the worktree) will be dropped. This
            effectively empties the annex of a local dataset.
            With 'datasets', only complete datasets will be dropped (implies
            'allkeys' mode for each such dataset), but no filecontent will be
            dropped for any files in datasets that are not dropped entirely.
            With 'all', content for any matching file or dataset will be dropped
            entirely.
            """,
            # TODO add 'unwanted'
            constraints=EnsureChoice('filecontent', 'allkeys', 'datasets', 'all')),
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
            doc="""DEPRECATED and IGNORED: use --reckless instead""",),
    )

    @staticmethod
    @datasetmethod(name='drop')
    @eval_results
    def __call__(
            path=None,
            *,
            what='filecontent',
            reckless=None,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            jobs=None,
            # deprecated
            check=None,
            if_dirty=None):

        # TODO if reckless is None, initialize from a potential config setting
        # left behind by a reckless clone

        # proper spelling of mode switches is critical for implementation
        # below. double-check, also in Python API usage
        # TODO consider making a generic helper
        for label, value in (('what', what), ('reckless', reckless)):
            try:
                Drop._params_[label].constraints(value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid '{label}' parameter value of: "
                    f"{repr(value)} [{str(e)}]") from e

        if check is not None:
            warnings.warn(
                "The `check` argument of `datalad drop` is deprecated, "
                "use the `reckless` argument instead.",
                DeprecationWarning)
        if if_dirty is not None:
            warnings.warn(
                "The `if_dirty` argument of `datalad drop` is ignored, "
                "it can be removed for a safe-by-default behavior. For "
                "other cases consider the `reckless` argument.",
                DeprecationWarning)

        if check is False:
            if reckless is not None:
                raise ValueError(
                    'Must not use deprecated `check` argument, and new '
                    '`reckless` argument together with `datalad drop`.')
            reckless = 'availability'

        if what in ('all', 'datasets') and reckless == 'kill' and not recursive:
            raise ValueError(
                'A reckless kill is requested but no recursion flag is set. '
                "With 'kill' no checks for subdatasets will be made, "
                'acknowledge by setting the recursive flag')

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
            # XXX this needs more thought!! Maybe this is what the mode should be
            # in general?!
            # when we want to drop entire datasets, it is much more useful
            # to have subdatasets be their own record
            subdsroot_mode='sub'
            if what in ('all', 'datasets')
            else 'rsync',
        )
        for e in errors:
            yield dict(
                action='drop',
                path=str(e),
                status='error',
                message=('path not underneath the reference dataset %s', ds),
                **res_props)
            # we are not returning, a caller could decide on failure mode

        if what in ('all', 'datasets') and _paths_atunder_dir(
                paths_by_ds, ds.pathobj.cwd()):
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


def _paths_atunder_dir(pbd, dirpath):
    """Whether any of the paths is at or under a reference path

    Parameters
    ----------
    pbd: dict
      Dataset path dict is produced by get_paths_by_ds()
    dirpath: Path
      Reference path

    Returns
    -------
    bool
    """
    for dpath, paths in pbd.items():
        for p in ([dpath] if paths is None else paths):
            if p == dirpath or p in dirpath.parents:
                return True
    return False


def _drop_dataset(ds, paths, what, reckless, recursive, recursion_limit, jobs):
    lgr.debug('Start dropping for %s', ds)
    # we know that any given path is part of `ds` and not any of its
    # subdatasets!

    # by-passing this completely with reckless=kill
    if recursive and not reckless == 'kill':
        # process subdatasets first with recursion
        for sub in ds.subdatasets(
                # must be resolved!
                path=paths or None,
                # nothing to drop with unavailable subdatasets
                state='present',
                # we can use the full recursion depth, only the first layer
                # of calls to _drop_dataset() must/can have recursive=True
                recursive=recursive,
                recursion_limit=recursion_limit,
                # start reporting with the leaves
                bottomup=True,
                result_xfm='datasets',
                on_failure='ignore',
                return_type='generator',
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

    if not ds.pathobj.exists():
        # basic protection against something having wiped it out already.
        # should not happen, but better than a crash, if it does
        yield dict(
            action='drop',
            path=ds.path,
            status='notneeded',
            message="does not exist",
            type='dataset',
        )
        return

    if paths is not None and paths != [ds.pathobj] and what == 'all':
        if recursive and reckless == 'kill':
            # check if any paths contains a subdataset, and if so, drop it to
            # ensure its not left behind
            for sub in ds.subdatasets(
                    # just check for subds at the provided path
                    path=paths,
                    state='present',
                    recursive=recursive,
                    recursion_limit=recursion_limit,
                    result_xfm='datasets',
                    on_failure='ignore',
                    return_type='generator',
                    result_renderer='disabled'):
                if sub is not None:
                    # there is a subdataset underneath the given path
                    yield from _drop_dataset(
                        ds=sub,
                        # everything underneath the subds can go
                        paths=None,
                        what=what,
                        reckless=reckless,
                        recursive=False,
                        recursion_limit=None,
                        jobs=jobs)
        # so we have paths constraints that prevent dropping the full dataset
        lgr.debug('Only dropping file content for given paths in %s, '
                  'allthough instruction was to drop %s', ds, what)
        what = 'filecontent'

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

    # next check must come AFTER the modification checks above, otherwise
    # remove() could not rely on the modification detection above
    if paths is not None and paths != [ds.pathobj] and what == 'datasets':
        # so we have paths constraints that prevent dropping the full dataset
        # there is nothing to do here, but to drop keys, which we must not
        # done
        return

    # now conditional/informative checks
    yield from _pre_drop_checks(ds, repo, paths, what, reckless, is_annex)

    if is_annex and what == 'filecontent':
        yield from _drop_files(
            ds,
            repo,
            # give paths or '.' with no constraint
            paths=[str(p.relative_to(ds.pathobj))
                   for p in paths] if paths else '.',
            force=reckless in ('availability', 'kill'),
            jobs=jobs,
        )
        # end it here for safety, the rest of the function deals with
        # dropping more and more fundamentally
        return

    drop_all_errored = False
    if is_annex and what in ('allkeys', 'datasets', 'all') \
            and not reckless == 'kill':
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
            message = r.get('note', '').replace(
                '--force',
                '--reckless availability')
            if message:
                res['message'] = message
            error_messages = r.get('error-messages')
            if error_messages:
                res['error_message'] = '\n'.join(
                    m.strip() for m in error_messages
                )
            # play safe, if there is no status, assume error
            if res.get('status', 'error') != 'ok':
                drop_all_errored = True
            yield res

    if drop_all_errored:
        # end it here, if there is any indication that wiping out the
        # repo is unsafe
        return

    if what in ('all', 'datasets'):
        yield from _kill_dataset(ds)
    lgr.debug('Done dropping for %s', ds)
    return


def _fatal_pre_drop_checks(ds, repo, paths, what, reckless, is_annex):
    if what == 'allkeys' and paths is not None \
            and paths != [ds.pathobj]:
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

    if what in ('all', 'datasets') and not reckless == 'kill':
        # we must not have subdatasets anymore
        # if we do, --recursive was forgotten
        subdatasets = ds.subdatasets(
            path=paths,
            # we only care about the present ones
            state='present',
            # first-level is enough, if that has none, there will be none
            recursive=False,
            result_xfm='paths',
            result_renderer='disabled')
        if subdatasets:
            yield dict(
                action='uninstall',
                path=ds.path,
                type='dataset',
                status='error',
                message=('cannot drop dataset, subdataset(s) still present '
                         '(forgot --recursive?): %s', subdatasets)
            )
            # this is fatal
            return

    if what in ('all', 'datasets') \
            and reckless not in ('availability', 'kill') \
            and (paths is None or paths == [ds.pathobj]):
        unpushed = _detect_unpushed_revs(repo, is_annex)
        if unpushed:
            yield dict(
                action='uninstall',
                path=ds.path,
                type='dataset',
                status='error',
                message=(
                    "to-be-dropped dataset has revisions that "
                    "are not available at any known sibling. Use "
                    "`datalad push --to ...` to push "
                    "these before dropping the local dataset, "
                    "or ignore via `--reckless availability`. "
                    "Unique revisions: %s",
                    unpushed)
            )
            # this is fatal
            return

    if is_annex and what in ('all', 'datasets') \
            and reckless not in ('undead', 'kill'):
        # this annex is about to die, test if it is still considered
        # not-dead. if so, complain to avoid generation of zombies
        # (annexed that are floating around, but are actually dead).
        # if repo.uuid is None, git annex init never ran, and we can skip this
        remotes_that_know_this_annex = None if repo.uuid is None else [
            r
            for r in _detect_nondead_annex_at_remotes(repo, repo.uuid)
            # filter out "here"
            if r is not None
        ]
        if remotes_that_know_this_annex:
            yield dict(
                action='uninstall',
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

    if reckless not in ('modification', 'kill'):
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
                eval_subdataset_state='commit'
                if what in ('all', 'datasets') else 'no',
                # recursion is handled outside this function
                recursive=False,
                result_renderer='disabled',
                return_type='generator',
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
    if not is_annex and reckless not in ('datasets', 'kill'):
        # we cannot drop content in non-annex repos, issue same
        # 'notneeded' as for git-file in annex repo
        for p in paths or [ds.path]:
            yield dict(
                action='drop',
                path=str(p),
                status='notneeded',
                message="no annex'ed content",
            )
        # continue, this is nothing fatal

    if not is_annex and what in ('allkeys', 'unwanted') \
            and not reckless == 'kill':
        # these drop modes are meaningless without an annex
        yield dict(
            action='drop',
            path=ds.path,
            status='notneeded',
            message="dataset with no annex",
            type='dataset',
        )
        # continue, this is nothing fatal


def _detect_unpushed_revs(repo, consider_managed_branches):
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
    consider_managed_branches: bool
      Whether to enable handling of managed branches.

    Returns
    -------
    list
      Names of local states/refs that are no available at a remote.
    """
    if consider_managed_branches:
        # consolidate corresponding branches to get reliable detection
        repo.localsync(managed_only=True)
    # we do not want to check this for any managed branches
    # that are not meant to be pushed without consolidation
    # or even at all (incl. git-annex, it can behave in complex ways)
    local_refs = [
        lb for lb in repo.get_branches()
        if not (not consider_managed_branches
            or lb == 'git-annex' or repo.is_managed_branch(lb))]
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


def _kill_dataset(ds):
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
        # keep uninstall to please the gods of a distant past
        #action='drop',
        action='uninstall',
        path=ds.path,
        type='dataset',
        status='ok',
    )


def _drop_allkeys(ds, repo, force=False, jobs=None):
    """
    """
    assert not (repo.dot_git / 'annex').is_symlink(), \
        "Dropping from a symlinked annex is unsupported to prevent data-loss"

    cmd = ['drop', '--all']
    if force:
        cmd.append('--force')
    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    try:
        yield from repo._call_annex_records_items_(cmd)
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
    assert not (repo.dot_git / 'annex').is_symlink(), \
        "Dropping from a symlinked annex is unsupported to prevent data-loss"
    cmd = ['drop']
    if force:
        cmd.append('--force')
    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    respath_by_status = {}
    try:
        yield from (
            _postproc_annexdrop_result(res, respath_by_status, ds)
            for res in repo._call_annex_records_items_(cmd, files=paths)
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
    res = annexjson2result(
        # annex reports are always about files
        res, ds, type='file', **kwargs)
    success = success_status_map[res['status']]
    respath_by_status[success] = \
        respath_by_status.get(success, []) + [res['path']]
    if res["status"] == "error" and res["action"] == "drop":
        msg = res.get("message", None)
        if isinstance(msg, str) and "Use --force to" in msg:
            # Avoid confusing datalad-drop callers with git-annex-drop's
            # suggestion to use --force.
            # Just mention reckless itself, do not go into the details
            # of which mode. This is likely changing over time and
            # adjusting this replacement will be forgotten.
            res["message"] = msg.replace(
                "--force",
                "--reckless availability")
    return res
