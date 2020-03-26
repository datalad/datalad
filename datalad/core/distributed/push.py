# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface for dataset (component) pushing

"""

__docformat__ = 'restructuredtext'

import logging
from tempfile import TemporaryFile

from datalad.consts import PRE_INIT_COMMIT_SHA
from datalad.cmd import GitWitlessRunner
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    jobs_opt,
    recursion_limit,
    recursion_flag,
)
from datalad.interface.utils import (
    eval_results,
)
from datalad.interface.results import annexjson2result
from datalad.support.annexrepo import (
    AnnexJsonProtocol,
    AnnexRepo,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
    EnsureChoice,
)
from datalad.support.exceptions import CommandError
from datalad.utils import (
    Path,
    assure_list,
)

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.core.local.diff import diff_dataset


lgr = logging.getLogger('datalad.core.distributed.push')


@build_doc
class Push(Interface):
    """Push a dataset to a known :term:`sibling`.

    This makes the last saved state of a dataset available to a sibling
    or special remote data store of a dataset. Any target sibling must already
    exist and be known to the dataset.

    Optionally, it is possible to limit a push to change sets relative
    to a particular point in the version history of a dataset (e.g. a release
    tag). By default, the state of the local dataset is evaluated against the
    last known state of the target sibling. An actual push is only attempted
    if there was a change compared to the reference state, in order to speed up
    processing of large collections of datasets. Evaluation with respect to
    a particular "historic" state is only supported in conjunction with a
    specified reference dataset. Change sets are also evaluated recursively, i.e.
    only those subdatasets are pushed where a change was recorded that is
    reflected in the current state of the top-level reference dataset.
    See "since" option for more information.

    Only a push of saved changes is supported.

    .. note::
      Power-user info: This command uses :command:`git push`, and :command:`git annex copy`
      to push a dataset. Publication targets are either configured remote
      Git repositories, or git-annex special remotes (if they support data
      upload).
    """

    # TODO add examples

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to push""",
            constraints=EnsureDataset() | EnsureNone()),
        to=Parameter(
            args=("--to",),
            metavar='SIBLING',
            doc="""name of the target sibling. If no name is given an attempt is
            made to identify the target based on the dataset's configuration
            (i.e. a configured tracking branch, or a single sibling that is
            configured for push)""",
            constraints=EnsureStr() | EnsureNone()),
        since=Parameter(
            args=("--since",),
            constraints=EnsureStr() | EnsureNone(),
            doc="""specifies commit-ish (tag, shasum, etc.) from which to look for
            changes to decide whether pushing is necessary.
            If an empty string is given, the last state of the current branch
            at the sibling is taken as a starting point."""),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path to contrain a push to. If given, only
            data or changes for those paths are considered for a push.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        force=Parameter(
            # multi-mode option https://github.com/datalad/datalad/issues/3414
            args=("-f", "--force",),
            doc="""force particular operations, overruling automatic decision
            making: use --force with git-push ('gitpush'); do not use --fast
            with git-annex copy ('datatransfer'); do not attempt to copy
            annex'ed file content ('no-datatransfer'); combine force modes
            'gitpush' and 'datatransfer' ('all').""",
            constraints=EnsureChoice(
                'all', 'gitpush', 'no-datatransfer', 'datatransfer', None)),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        jobs=jobs_opt,
    )

    # Desired features:
    # - let Git do it's thing (push multiple configured refs without the need
    #                          to specific anything on the command line
    #   - compilication: we need publication dependencies (i.e. publish what
    #     would be published by Git to a different remote first, hence we
    #     cannot simply watch Git do it, and later act on it.)
    #   - https://github.com/datalad/datalad/issues/1284
    #   - https://github.com/datalad/datalad/issues/4006
    # - make differences between remotes and various types of special remotes
    #   opaque
    #   - https://github.com/datalad/datalad/issues/3127
    # - informative and comprehensive (error) reporting
    #   - https://github.com/datalad/datalad/issues/2000
    #   - https://github.com/datalad/datalad/issues/1682
    #   - https://github.com/datalad/datalad/issues/2029
    #   - https://github.com/datalad/datalad/issues/2855
    #   - https://github.com/datalad/datalad/issues/3412
    #   - https://github.com/datalad/datalad/issues/3424
    # - ensure robust behavior in multi-lateral push scenarios (updating
    #   a dataset that was updated by a 3rd-party after the last known
    #   fetched change
    #   - https://github.com/datalad/datalad/issues/2636
    # - should NOT mimic `publish` and that it mixes `create-sibling` and
    #   `push` into a single operation. This would fold the complexity
    #   of all possible ways a local dataset hierarchy could possibly
    #   connected to remote ends into this command. It would be lost battle
    #   from the start.
    #   - not tackle: https://github.com/datalad/datalad/issues/2186
    # - maintain standard setup, and not reflect procedural aspects
    #   onto the resulting outcomes
    #   - https://github.com/datalad/datalad/issues/2001
    # - do a straight push, nothing like 'sync'. If a remote has something that
    #   needs merging first, fail and let users update. Any diff we are missing
    #   locally can impact decision making via --since and friends.

    @staticmethod
    @datasetmethod(name='push')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            to=None,
            since=None,
            force=None,
            recursive=False,
            recursion_limit=None,
            jobs=None):
        # we resolve here, because we need to perform inspection on what was given
        # as an input argument further down
        paths = [resolve_path(p, dataset) for p in assure_list(path)]

        ds = require_dataset(
            dataset, check_installed=True, purpose='pushing')
        ds_repo = ds.repo

        if since:
            # will blow with ValueError if unusable
            ds_repo.get_hexsha(since)

        if not since and since is not None:
            # special case: --since=''
            # figure out state of remote branch and set `since`
            since = _get_corresponding_remote_state(ds_repo, to)
            if not since:
                lgr.info(
                    "No tracked remote for active branch, "
                    "detection of last pushed state not in effect.")

        # obtain a generator for information on the datasets to process
        # idea is to turn the `paths` argument into per-dataset
        # content listings that can be acted upon
        ds_spec = _datasets_since_(
            # important to pass unchanged dataset arg
            dataset,
            # use the diff "since before time"
            since if since else PRE_INIT_COMMIT_SHA,
            paths,
            recursive,
            recursion_limit)

        res_kwargs = dict(
            action='publish',
            refds=ds.path,
            logger=lgr,
        )
        # instead of a loop, this could all be done in parallel
        matched_anything = False
        for dspath, dsrecords in ds_spec:
            matched_anything = True
            lgr.debug('Attempt push of Dataset at %s', dspath)
            yield from _push(
                dspath, dsrecords, to, force, jobs, res_kwargs.copy())
        if not matched_anything:
            yield dict(
                res_kwargs,
                status='notneeded',
                message='Given constraints did not match any changes to publish',
                type='dataset',
                path=ds.path,
            )

    @staticmethod
    def custom_result_summary_renderer(results):  # pragma: more cover
        # report on any hints at the end
        # get all unique hints
        hints = set([r.get('hints', None) for r in results])
        hints = [hint for hint in hints if hint is not None]
        if hints:
            from datalad.ui import ui
            from datalad.support import ansi_colors
            intro = ansi_colors.color_word(
                "Potential hints to solve encountered errors: ",
                ansi_colors.YELLOW)
            ui.message(intro)
            [ui.message("{}: {}".format(
                ansi_colors.color_word(id + 1, ansi_colors.YELLOW), hint))
                for id, hint in enumerate(hints)]


def _datasets_since_(dataset, since, paths, recursive, recursion_limit):
    """Generator"""
    # rely on diff() reporting sequentially across datasets
    cur_ds = None
    ds_res = None
    for res in diff_dataset(
            dataset=dataset,
            fr=since,
            # we never touch unsaved content
            to='HEAD',
            constant_refs=False,
            path=paths,
            # we need to know what is around locally to be able
            # to report something that should have been pushed
            # but could not, because we don't have a copy
            annex='availability',
            recursive=recursive,
            recursion_limit=recursion_limit,
            # make it as fast as possible
            eval_file_type=False,
            # we relay on all records of a dataset coming out
            # in succession, with no interuption by records
            # concerning subdataset content
            reporting_order='breadth-first'):
        if res.get('action', None) != 'diff':
            # we don't care right now
            continue
        if res.get('status', None) != 'ok':
            # we cannot handle this situation, report it in panic
            raise RuntimeError(
                'Cannot handle non-OK diff result: {}'.format(res))
        parentds = res.get('parentds', None)
        if not parentds:
            raise RuntimeError(
                'Cannot handle diff result without a parent dataset '
                'property: {}'.format(res))
        if res.get('type', None) == 'dataset':
            # a subdataset record in another data
            # this could be here, because
            # - this dataset with explicitely requested by path
            #   -> should get a dedicated dataset record -- even without recursion
            # - a path within an existing subdataset was given
            # - a path within an non-existing subdataset was given
            #   locally or not)
            #   -> it should be ignored, but should not cause the branch in the
            #   superdataset not to be pushed, if this was the only change
            p = Path(res['path'])
            # was given as an explicit path argument
            if any(arg == p for arg in paths) and \
                    not GitRepo.is_valid_repo(res['path']):
                raise ValueError(
                    'Cannot publish subdataset, not present: {}'.format(res['path']))

        if parentds != cur_ds:
            if ds_res:
                # we switch to another dataset, yield this one so outside
                # code can start processing immediately
                yield (cur_ds, ds_res)
            # clean start
            ds_res = []
            cur_ds = parentds
        ds_res.append({
            k: v for k, v in res.items()
            if k in (
                # let's keep 'state' in for now, it would make it possible
                # to implement a "sync"-type push downstream that actually
                # pulls 'deleted' files
                'state',
                # 'file' to copy-to, and subdataset records to possibly
                # act on
                'type',
                # essential
                'path',
                # maybe do a key-based copy-to?
                'key',
                # progress reporting?
                'bytesize',
                # 'impossible' result when we should have copy-to'ed, but
                # could not, because content isn't present
                'has_content')
        })

    # if we have something left to report, do it
    # importantly do not test for ds_res, even if we had only seen subdataset
    # records to be changes, we would still want to push the git branches
    if cur_ds:
        yield (cur_ds, ds_res)


def _push(dspath, content, target, force, jobs, res_kwargs,
          done_fetch=None):
    if not done_fetch:
        done_fetch = set()
    # nothing recursive in here, we only need a repo to work with
    ds = Dataset(dspath)
    repo = ds.repo

    res_kwargs.update(type='dataset', path=dspath)

    if not target:
        try:
            # let Git figure out what needs doing
            wannabe_gitpush = repo.push(remote=None, git_options=['--dry-run'])
            # we did not get an explicit push target, get it from Git
            target = set(p.get('remote', None) for p in wannabe_gitpush)
            # handle case where a pushinfo record did not have a 'remote'
            # property -- should not happen, but be robust
            target.discard(None)
        except Exception as e:
            lgr.debug(
                'Dry-run push to determine default push target failed, '
                'assume no configuration: %s', e)
            target = set()
        if not len(target):
            yield dict(
                res_kwargs,
                status='impossible',
                message='No push target given, and none could be '
                        'auto-detected, please specific via --to',
            )
            return
        elif len(target) > 1:
            # dunno if this can ever happen, but if it does, report
            # nicely
            yield dict(
                res_kwargs,
                status='error',
                message=(
                    'No push target given, '
                    'multiple candidates auto-detected: %s',
                    list(target),
                )
            )
            return
        else:
            # can only be a single one at this point
            target = target.pop()

    if target not in repo.get_remotes():
        yield dict(
            res_kwargs,
            status='error',
            message=(
                "Unknown target sibling '%s'.", target))
        return

    lgr.debug("Attempt to push to '%s'", target)

    # define config var name for potential publication dependencies
    depvar = 'remote.{}.datalad-publish-depends'.format(target)
    # list of remotes that are publication dependencies for the
    # target remote
    publish_depends = assure_list(ds.config.get(depvar, []))
    if publish_depends:
        lgr.debug("Discovered publication dependencies for '%s': %s'",
                  target, publish_depends)

    # cache repo type
    is_annex_repo = isinstance(ds.repo, AnnexRepo)

    # TODO prevent this when `target` is a special remote
    # (possibly redo) a push attempt to figure out what needs pushing
    # do this on the main target only, and apply the result to all
    # dependencies
    try:
        wannabe_gitpush = repo.push(
            remote=target,
            git_options=['--dry-run'])
    except Exception as e:
        lgr.debug(
            'Dry-run push to check push configuration failed, '
            'assume no configuration: %s', e)
        wannabe_gitpush = []
    refspecs2push = [
        # if an upstream branch is set, go with it
        p['from_ref']
        if ds.config.get(
            # refs come in as refs/heads/<branchname>
            # need to cut the prefix
            'branch.{}.remote'.format(p['from_ref'][11:]),
            None) == target and ds.config.get(
                'branch.{}.merge'.format(p['from_ref'][11:]),
                None)
        # if not, define target refspec explicitly to avoid having to
        # set an upstream branch, which would happen implicitly from
        # a users POV, and may also be hard to decide when publication
        # dependencies are present
        else '{}:{}'.format(p['from_ref'], p['to_ref'])
        for p in wannabe_gitpush
        # TODO: what if a publication dependency doesn't have it yet
        # should we not attempt to push, because the main target has it?
        if 'uptodate' not in p['operations'] and (
            # cannot think of a scenario where we would want to push a
            # managed branch directly, instead of the corresponding branch
            'refs/heads/adjusted' not in p['from_ref'])
    ]
    if not refspecs2push:
        lgr.debug(
            'No refspecs configured for push, attempting to use active branch')
        # nothing was set up for push, push the current branch at minimum
        # TODO this is not right with managed branches
        active_branch = repo.get_active_branch()
        if not active_branch:
            yield dict(
                res_kwargs,
                status='impossible',
                message=
                'There is no active branch, cannot determine remote '
                'branch'
            )
            return
        if is_annex_repo:
            # we could face a managed branch, in which case we need to
            # determine the actual one and make sure it is sync'ed with the
            # managed one, and push that one instead. following methods can
            # be called unconditionally
            repo.localsync(managed_only=True)
            active_branch = repo.get_corresponding_branch(
                active_branch) or active_branch
        refspecs2push.append(
            # same dance as above
            active_branch
            if ds.config.get('branch.{}.merge'.format(active_branch), None)
            else '{ab}:{ab}'.format(ab=active_branch)
        )

    # we know what to push and where, now dependency processing first
    for r in publish_depends:
        # simply make a call to this function again, all the same, but
        # target is different, pass done_fetch to avoid duplicate
        # and expensive calls to git-fetch
        yield from _push(
            dspath,
            content,
            # to this particular dependency
            r,
            force,
            jobs,
            res_kwargs.copy(),
            done_fetch=None
        )

    # and lastly the primary push target
    target_is_git_remote = repo.config.get(
        'remote.{}.url'.format(target), None) is not None
    # only attempt, if Git knows about a URL, otherwise this is
    # a pure special remote that doesn't deal with the git repo
    if target_is_git_remote:
        # push the main branches of interest first, but not yet (necessarily)
        # the git-annex branch. We ant to push first in order to hit any
        # conflicts or unknown history before we move data. Otherwise out
        # decision making done above (--since ...) might have been
        # inappropriate.
        push_ok = True
        for p in _push_refspecs(
                repo,
                target,
                refspecs2push,
                force,
                res_kwargs.copy()):
            if p['status'] not in ('ok', 'notneeded'):
                push_ok = False
            yield p
        if not push_ok:
            # error-type results have been yielded, the local status quo is
            # outdated/invalid, stop to let user decide how to proceed.
            # TODO final global error result for the dataset?!
            return

    # git-annex data move
    #
    if not is_annex_repo:
        return

    if force == 'no-datatransfer':
        lgr.debug("Data transfer to '%s' disabled by argument", target)
        return

    yield from _push_data(
        ds,
        target,
        content,
        force,
        jobs,
        res_kwargs.copy(),
    )

    if not target_is_git_remote:
        # there is nothing that we need to push or sync with on the git-side
        # of things with this remote
        return

    # after file transfer the remote might have different commits to
    # the annex branch. They have to be merged locally, otherwise a
    # push of it further down will fail
    try:
        # fetch remote, let annex sync them locally, so that the push
        # later on works.
        # We have to fetch via the push url (if there is any),
        # not a pull url.
        # The latter might be dumb and without the execution of a
        # post-update hook we might not be able to retrieve the
        # server-side git-annex branch updates (and git-annex does
        # not trigger the hook on copy), but we know we have
        # full access via the push url -- we have just used it to copy.
        lgr.debug("Fetch 'git-annex' branch updates from '%s'", target)
        fetch_cmd = ['fetch', target, 'git-annex']
        pushurl = repo.config.get(
            'remote.{}.pushurl'.format(target), None)
        if pushurl:
            # for some reason overwriting remote.{target}.url
            # does not have any effect...
            fetch_cmd = [
                '-c',
                'url.{}.insteadof={}'.format(
                    pushurl,
                    repo.config.get(
                        'remote.{}.url'.format(target), None)
                )
            ] + fetch_cmd
            lgr.debug(
                "Sync local annex branch from pushurl after remote "
                'availability update.')
        repo.call_git(fetch_cmd)
        repo.localsync(target)
    except CommandError as e:
        # it is OK if the remote doesn't have a git-annex branch yet
        # (e.g. fresh repo)
        # TODO is this possible? we just copied? Maybe check if anything
        # was actually copied?
        if "fatal: couldn't find remote ref git-annex" not in e.stderr.lower():
            raise
        lgr.debug('Remote does not have a git-annex branch: %s', e)
    # and push the annex branch to announce local availability info
    # too
    yield from _push_refspecs(
        repo,
        target,
        ['git-annex'
         if ds.config.get('branch.git-annex.merge', None)
         else 'git-annex:git-annex'],
        force,
        res_kwargs.copy(),
    )


def _push_refspecs(repo, target, refspecs, force, res_kwargs):
    # TODO inefficient, but push only takes a single refspec at a time
    # at the moment, enhance GitRepo.push() to do all at once
    push_res = []
    for refspec in refspecs:
        push_res.extend(repo.push(
            remote=target,
            refspec=refspec,
            git_options=['--force'] if force in ('all', 'gitpush') else None,
        ))
    # TODO maybe compress into a single message whenever everything is
    # OK?
    for pr in push_res:
        ops = pr['operations']
        status = (
            'error'
            if any(o in ops for o in (
                'error', 'no-match', 'rejected', 'remote-rejected',
                'remote-failure'))
            else 'notneeded'
            if 'uptodate' in pr['operations']
            else 'ok'
            if any(o in ops for o in (
                'new-tag', 'new-branch', 'forced-update', 'fast-forward'))
            # no really a good fit, but we have tested all relevant
            # operations above, so in some sense this condition should be
            # impossible to achieve
            else 'impossible'
        )
        refspec = '{}:{}'.format(pr['from_ref'], pr['to_ref'])
        yield dict(
            res_kwargs,
            status=status,
            target=pr['remote'],
            refspec=refspec,
            operations=ops,
            hints=pr.get('hints', None),
            # seems like a good idea to pass on Git's native message
            # TODO maybe implement a dedicated result renderer, instead
            # of duplicating information only so that the default one
            # can make sense at all
            message='{}->{}:{} {}'.format(
                pr['from_ref'],
                pr['remote'],
                pr['to_ref'],
                pr['note']),
        )


def _push_data(ds, target, content, force, jobs, res_kwargs):
    if ds.config.getbool('remote.{}'.format(target), 'annex-ignore', False):
        lgr.debug(
            "Target '%s' is set to annex-ignore, exclude from data-push.",
            target,
        )
        return
    res_kwargs['target'] = target
    if not ds.config.get('.'.join(('remote', target, 'annex-uuid')), None):
        # this remote either isn't an annex,
        # or hasn't been properly initialized
        # rather than barfing tons of messages for each file, do one
        # for the entire dataset
        yield dict(
            res_kwargs,
            action='copy',
            status='impossible'
            if force in ('all', 'datatransfer')
            else 'notneeded',
            message=(
                "Target '%s' does not appear to be an annex remote",
                target)
        )
        return
    # figure out which of the reported content (after evaluating
    # `since` and `path` arguments needs transport
    to_transfer = [
        c
        for c in content
        # by force
        if ((force in ('all', 'datatransfer') or
             # or by modification report
             c.get('state', None) not in ('clean', 'deleted'))
            # only consider annex'ed files
            and 'key' in c
        )
    ]
    for c in [c for c in to_transfer if not c.get('has_content', False)]:
        yield dict(
            res_kwargs,
            type=c['type'],
            path=c['path'],
            action='copy',
            status='impossible',
            message='Slated for transport, but no content present',
        )

    cmd = ['git', 'annex', 'copy', '--batch', '-z', '--to', target,
           '--json', '--json-error-messages', '--json-progress']

    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    if not to_transfer and force not in ('all', 'datatransfer'):
        lgr.debug("Invoking copy --auto")
        cmd.append('--auto')

    if force not in ('all', 'datatransfer'):
        # if we force, we do not trust local knowledge and do the checks
        cmd.append('--fast')

    lgr.debug("Push data from %s to '%s'", ds, target)

    # input has type=dataset, but now it is about files
    res_kwargs.pop('type', None)

    # produce final path list. use knowledge that annex command will
    # run in the root of the dataset and compact paths to be relative
    # to this location
    # XXX must not be a SpooledTemporaryFile -- dunno why, but doesn't work
    # otherwise
    with TemporaryFile() as file_list:
        for c in to_transfer:
            if not c.get('has_content', False):
                # warned about above, now just skip
                continue
            file_list.write(
                bytes(Path(c['path']).relative_to(ds.pathobj)))
            file_list.write(b'\0')

        # rewind stdin buffer
        file_list.seek(0)
        # and go
        # TODO try-except and yield what was captured before the crash
        #res = GitWitlessRunner(
        res = GitWitlessRunner(
            cwd=ds.path,
        ).run(
            cmd,
            # TODO report how many in total, and give global progress too
            protocol=AnnexJsonProtocol,
            stdin=file_list)
        for c in ('stdout', 'stderr'):
            if res[c]:
                lgr.debug('Received unexpected %s from `annex copy`: %s',
                          c, res[c])
        for j in res['stdout_json']:
            yield annexjson2result(j, ds, type='file', **res_kwargs)
    return


def _get_corresponding_remote_state(repo, to):
    since = None
    active_branch = repo.get_active_branch()
    if to:
        # XXX here we assume one to one mapping of names from local branches
        # to the remote
        since = '%s/%s' % (to, active_branch)
    else:
        # take tracking remote for the active branch
        tracked_remote, tracked_refspec = repo.get_tracking_branch()
        if tracked_remote:
            if tracked_refspec.startswith('refs/heads/'):
                tracked_refspec = tracked_refspec[len('refs/heads/'):]
            #to = tracked_remote
            since = '%s/%s' % (tracked_remote, tracked_refspec)
    return since
