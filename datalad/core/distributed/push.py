# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
import re
from itertools import chain

from datalad.core.local.diff import diff_dataset
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
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
from datalad.interface.results import annexjson2result
from datalad.interface.utils import render_action_summary
from datalad.log import log_progress
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    ensure_list,
    todo_interface_for_extensions,
)

lgr = logging.getLogger('datalad.core.distributed.push')


@build_doc
class Push(Interface):
    """Push a dataset to a known :term:`sibling`.

    This makes a saved state of a dataset available to a sibling or special
    remote data store of a dataset. Any target sibling must already exist and
    be known to the dataset.

    || REFLOW >>
    By default, all files tracked in the last saved state (of the current
    branch) will be copied to the target location. Optionally, it is possible
    to limit a push to changes relative to a particular point in the version
    history of a dataset (e.g. a release tag) using the
    [CMD: --since CMD][PY: since PY] option in conjunction with the
    specification of a reference dataset. In recursive mode subdatasets will also be
    evaluated, and only those subdatasets are pushed where a change was
    recorded that is reflected in the current state of the top-level reference
    dataset.
    << REFLOW ||

    .. note::
      Power-user info: This command uses :command:`git push`, and :command:`git
      annex copy` to push a dataset. Publication targets are either configured
      remote Git repositories, or git-annex special remotes (if they support
      data upload).
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
            If '^' is given, the last state of the current branch at the sibling
            is taken as a starting point."""),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path to constrain a push to. If given, only
            data or changes for those paths are considered for a push.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        data=Parameter(
            args=("--data",),
            doc="""what to do with (annex'ed) data. 'anything' would cause
            transfer of all annexed content, 'nothing' would avoid call to
            `git annex copy` altogether. 'auto' would use 'git annex copy' with
            '--auto' thus transferring only data which would satisfy "wanted"
            or "numcopies" settings for the remote (thus "nothing" otherwise).
            'auto-if-wanted' would enable '--auto' mode only if there is a
            "wanted" setting for the remote, and transfer 'anything' otherwise.
            """,
            constraints=EnsureChoice(
                'anything', 'nothing', 'auto', 'auto-if-wanted')),
        force=Parameter(
            # multi-mode option https://github.com/datalad/datalad/issues/3414
            args=("-f", "--force",),
            doc="""force particular operations, possibly overruling safety
            protections or optimizations: use --force with git-push ('gitpush');
            do not use --fast with git-annex copy ('checkdatapresent');
            combine all force modes ('all').""",
            constraints=EnsureChoice(
                'all', 'gitpush', 'checkdatapresent', None)),
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
            *,
            dataset=None,
            to=None,
            since=None,
            data='auto-if-wanted',
            force=None,
            recursive=False,
            recursion_limit=None,
            jobs=None):
        # push uses '^' to annotate the previous pushed committish, and None for default
        # behavior. '' was/is (to be deprecated) used in `publish`. Alert user about the mistake
        if since == '':
            raise ValueError("'since' should point to commitish or use '^'.")
        # we resolve here, because we need to perform inspection on what was given
        # as an input argument further down
        paths = [resolve_path(p, dataset) for p in ensure_list(path)]

        ds = require_dataset(
            dataset, check_installed=True, purpose='push')
        ds_repo = ds.repo

        res_kwargs = dict(
            action='publish',
            refds=ds.path,
            logger=lgr,
        )

        get_remote_kwargs = {'exclude_special_remotes': False} \
            if isinstance(ds_repo, AnnexRepo) else {}
        if to and to not in ds_repo.get_remotes(**get_remote_kwargs):
            # get again for proper error:
            sr = ds_repo.get_remotes(**get_remote_kwargs)
            # yield an error result instead of raising a ValueError,
            # to enable the use case of pushing to a target that
            # a superdataset doesn't know, but some subdatasets to
            # (in combination with '--on-failure ignore')
            yield dict(
                res_kwargs,
                status='error',
                path=ds.path,
                message="Unknown push target '{}'. {}".format(
                    to,
                    'Known targets: {}.'.format(', '.join(repr(s) for s in sr))
                    if sr
                    else 'No targets configured in dataset.'))
            return
        if since == '^':
            # figure out state of remote branch and set `since`
            since = _get_corresponding_remote_state(ds_repo, to)
            if not since:
                lgr.info(
                    "No tracked remote for active branch, "
                    "detection of last pushed state not in effect.")
        elif since:
            # will blow with ValueError if unusable
            ds_repo.get_hexsha(since)


        # obtain a generator for information on the datasets to process
        # idea is to turn the `paths` argument into per-dataset
        # content listings that can be acted upon
        ds_spec = _datasets_since_(
            # important to pass unchanged dataset arg
            dataset,
            since,
            paths,
            recursive,
            recursion_limit)

        # instead of a loop, this could all be done in parallel
        matched_anything = False
        for dspath, dsrecords in ds_spec:
            matched_anything = True
            lgr.debug('Pushing Dataset at %s', dspath)
            pbars = {}
            yield from _push(
                dspath, dsrecords, to, data, force, jobs, res_kwargs.copy(), pbars,
                got_path_arg=True if path else False)
            # take down progress bars for this dataset
            for i, ds in pbars.items():
                log_progress(lgr.info, i, 'Finished push of %s', ds)
        if not matched_anything:
            potential_remote = False
            if not to and len(paths) == 1:
                # if we get a remote name without --to, provide a hint
                sr = ds_repo.get_remotes(**get_remote_kwargs)
                potential_remote = [
                    p for p in ensure_list(path) if p in sr
                ]
            if potential_remote:
                if len(potential_remote) == 1:
                    # present as a single value to make hint even more human
                    # friendly
                    potential_remote = potential_remote[0]
                hint = "{} matches a sibling name and not a path. " \
                      "Forgot --to?".format(potential_remote)
                yield dict(
                    res_kwargs,
                    status='notneeded',
                    message=hint,
                    hints=hint,
                    type='dataset',
                    path=ds.path,
                )
                # there's no matching path and we have generated a hint on
                # fixing the call - we can return now
                return
            yield dict(
                res_kwargs,
                status='notneeded',
                message='Given constraints did not match any changes to publish',
                type='dataset',
                path=ds.path,
            )

    custom_result_summary_renderer_pass_summary = True

    @staticmethod
    def custom_result_summary_renderer(results, action_summary):  # pragma: more cover
        render_action_summary(action_summary)
        # report on any hints at the end
        # get all unique hints
        hints = set([r.get('hints', None) for r in results])
        hints = [hint for hint in hints if hint is not None]
        if hints:
            from datalad.support import ansi_colors
            from datalad.ui import ui
            intro = ansi_colors.color_word(
                "Hints: ",
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
            # but could not, because we don't have a copy.
            # however, getting this info here is needlessly
            # expensive, we will do it at the latest possible stage
            # in _push_data()
            annex=None,
            recursive=recursive,
            recursion_limit=recursion_limit,
            # TODO?: expose order as an option for diff and push
            # since in some cases breadth-first would be sufficient
            # and result in "taking action faster"
            reporting_order='bottom-up'
    ):
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
            # a subdataset record in another dataset
            # this could be here, because
            # - this dataset was explicitly requested by path
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
                'path')
        })

    # if we have something left to report, do it
    # importantly do not test for ds_res, even if we had only seen subdataset
    # records to be changes, we would still want to push the git branches
    if cur_ds:
        yield (cur_ds, ds_res)


@todo_interface_for_extensions
def _transfer_data(repo, ds, target, content, data, force, jobs, res_kwargs,
                   got_path_arg):
    yield from _push_data(
        ds,
        target,
        content,
        data,
        force,
        jobs,
        res_kwargs.copy(),
        got_path_arg=got_path_arg,
    )


def _push(dspath, content, target, data, force, jobs, res_kwargs, pbars,
          got_path_arg=False):
    force_git_push = force in ('all', 'gitpush')

    # nothing recursive in here, we only need a repo to work with
    ds = Dataset(dspath)
    repo = ds.repo

    res_kwargs.update(type='dataset', path=dspath)

    # content will be unique for every push (even on the same dataset)
    pbar_id = 'push-{}-{}'.format(target, id(content))
    # register for final orderly take down
    pbars[pbar_id] = ds
    log_progress(
        lgr.info, pbar_id,
        'Determine push target',
        unit=' Steps',
        label='Push',
        total=4,
    )
    # pristine input arg
    _target = target
    # verified or auto-detected
    target = None
    if not _target:
        try:
            try:
                # let Git figure out what needs doing
                # we will reuse the result further down again, so nothing is wasted
                wannabe_gitpush = repo.push(remote=None, git_options=['--dry-run'])
                # we did not get an explicit push target, get it from Git
                target = set(p.get('remote', None) for p in wannabe_gitpush)
                # handle case where a pushinfo record did not have a 'remote'
                # property -- should not happen, but be robust
                target.discard(None)
            except CommandError as e:
                if 'Please make sure you have the correct access rights' in e.stderr:
                    # there is a default push target but we have no permission
                    yield dict(
                        res_kwargs,
                        status='impossible',
                        message='Attempt to push to default target resulted in following '
                                'error.  Address the error or specify different target with --to: '
                                + e.stderr,
                    )
                    return
                raise
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
                        'auto-detected, please specify via --to',
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

    if not target:
        if _target not in repo.get_remotes():
            yield dict(
                res_kwargs,
                status='error',
                message=(
                    "Unknown target sibling '%s'.", _target))
            return
        target = _target

    log_progress(
        lgr.info, pbar_id, "Push refspecs",
        label="Push to '{}'".format(target), update=1, total=4)

    # define config var name for potential publication dependencies
    depvar = 'remote.{}.datalad-publish-depends'.format(target)
    # list of remotes that are publication dependencies for the
    # target remote
    publish_depends = ensure_list(ds.config.get(depvar, [], get_all=True))
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
        if _target:
            # only do it when an explicit target was given, otherwise
            # we can reuse the result from the auto-probing above
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
    # TODO this is not right with managed branches
    active_branch = repo.get_active_branch()
    if active_branch and is_annex_repo:
        # we could face a managed branch, in which case we need to
        # determine the actual one and make sure it is sync'ed with the
        # managed one, and push that one instead. following methods can
        # be called unconditionally
        repo.localsync(managed_only=True)
        active_branch = repo.get_corresponding_branch(
            active_branch) or active_branch

    if not refspecs2push and not active_branch:
        # nothing was set up for push, and we have no active branch
        # this is a weird one, let's confess and stop here
        # I don't think we need to support such a scenario
        if not active_branch:
            yield dict(
                res_kwargs,
                status='impossible',
                message=
                'There is no active branch, cannot determine remote '
                'branch'
            )
            return

    # make sure that we always push the active branch (the context for the
    # potential path arguments) and the annex branch -- because we claim
    # to know better than any git config
    must_have_branches = [active_branch] if active_branch else []
    if is_annex_repo:
        must_have_branches.append('git-annex')
    for branch in must_have_branches:
        _append_branch_to_refspec_if_needed(ds, refspecs2push, branch)

    # we know what to push and where, now dependency processing first
    for r in publish_depends:
        # simply make a call to this function again, all the same, but
        # target is different
        yield from _push(
            dspath,
            content,
            # to this particular dependency
            r,
            data,
            force,
            jobs,
            res_kwargs.copy(),
            pbars,
            got_path_arg=got_path_arg,
        )

    # and lastly the primary push target
    target_is_git_remote = repo.config.get(
        'remote.{}.url'.format(target), None) is not None

    # git-annex data copy
    #
    if is_annex_repo:
        if data != "nothing":
            log_progress(
                lgr.info, pbar_id, "Transfer data",
                label="Transfer data to '{}'".format(target), update=2, total=4)
            yield from _transfer_data(
                repo,
                ds,
                target,
                content,
                data,
                force,
                jobs,
                res_kwargs.copy(),
                got_path_arg=got_path_arg,
            )
        else:
            lgr.debug("Data transfer to '%s' disabled by argument", target)
    else:
        lgr.debug("No data transfer: %s is not a git annex repository", repo)

    if not target_is_git_remote:
        # there is nothing that we need to push or sync with on the git-side
        # of things with this remote
        return

    log_progress(
        lgr.info, pbar_id, "Update availability information",
        label="Update availability for '{}'".format(target), update=3, total=4)

    # TODO fetch is only needed if anything was actually transferred. Collect this
    # info and make the following conditional on it

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
        lgr.debug("Fetching 'git-annex' branch updates from '%s'", target)
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
        # If no CommandError was raised, it means that remote has git-annex
        # but local repo might not be an annex yet. Since there is nothing to "sync"
        # from us, we just skip localsync without mutating repo into an AnnexRepo
        if is_annex_repo:
            repo.localsync(target)
    except CommandError as e:
        # it is OK if the remote doesn't have a git-annex branch yet
        # (e.g. fresh repo)
        # TODO is this possible? we just copied? Maybe check if anything
        # was actually copied?
        if "fatal: couldn't find remote ref git-annex" not in e.stderr.lower():
            raise
        lgr.debug('Remote does not have a git-annex branch: %s', e)

    if not refspecs2push:
        lgr.debug('No refspecs found that need to be pushed')
        return

    # and push all relevant branches, plus the git-annex branch to announce
    # local availability info too
    yield from _push_refspecs(
        repo,
        target,
        refspecs2push,
        force_git_push,
        res_kwargs.copy(),
    )


def _append_branch_to_refspec_if_needed(ds, refspecs, branch):
    # try to anticipate any flavor of an idea of a branch ending up in a refspec
    looks_like_that_branch = re.compile(
        r'((^|.*:)refs/heads/|.*:|^){}$'.format(branch))
    if all(not looks_like_that_branch.match(r) for r in refspecs):
        refspecs.append(
            branch
            if ds.config.get('branch.{}.merge'.format(branch), None)
            else '{branch}:{branch}'.format(branch=branch)
        )


def _push_refspecs(repo, target, refspecs, force_git_push, res_kwargs):
    push_res = repo.push(
        remote=target,
        refspec=refspecs,
        git_options=['--force'] if force_git_push else None,
    )
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


def _push_data(ds, target, content, data, force, jobs, res_kwargs,
               got_path_arg=False):
    if ds.config.getbool('remote.{}'.format(target), 'annex-ignore', False):
        lgr.debug(
            "Target '%s' is set to annex-ignore, exclude from data-push.",
            target,
        )
        return

    ds_repo = ds.repo

    res_kwargs['target'] = target
    if not ds.config.get('.'.join(('remote', target, 'annex-uuid')), None):
        # this remote either isn't an annex,
        # or hasn't been properly initialized
        # given that there was no annex-ignore, let's try to init it
        # see https://github.com/datalad/datalad/issues/5143 for the story
        ds_repo.localsync(target)

        if not ds.config.get('.'.join(('remote', target, 'annex-uuid')), None):
            # still nothing
            # rather than barfing tons of messages for each file, do one
            # for the entire dataset
            yield dict(
                res_kwargs,
                action='copy',
                status='impossible'
                if force in ('all', 'checkdatapresent')
                else 'notneeded',
                message=(
                    "Target '%s' does not appear to be an annex remote",
                    target)
            )
            return

    # it really looks like we will transfer files, get info on what annex
    # has in store
    # paths must be recoded to a dataset REPO root (in case of a symlinked
    # location
    annex_info_init = \
        {ds_repo.pathobj / Path(c['path']).relative_to(ds.pathobj): c
         for c in content} if ds.pathobj != ds_repo.pathobj else \
        {Path(c['path']): c for c in content}
    content = ds.repo.get_content_annexinfo(
        # paths are taken from `annex_info_init`
        paths=None,
        init=annex_info_init,
        ref='HEAD',
        # this is an expensive operation that is only needed
        # to perform a warning below, and for more accurate
        # progress reporting (exclude unavailable content).
        # limit to cases with explicit paths provided
        eval_availability=True if got_path_arg else False,
    )
    # figure out which of the reported content (after evaluating
    # `since` and `path` arguments needs transport
    to_transfer = [
        c
        for c in content.values()
        # by force
        if ((force in ('all', 'checkdatapresent') or
             # or by modification report
             c.get('state', None) not in ('clean', 'deleted'))
            # only consider annex'ed files
            and 'key' in c
        )
    ]
    if got_path_arg:
        for c in [c for c in to_transfer if not c.get('has_content', False)]:
            yield dict(
                res_kwargs,
                type=c['type'],
                path=c['path'],
                action='copy',
                status='impossible',
                message='Slated for transport, but no content present',
            )

    cmd = ['copy', '--batch', '-z', '--to', target]

    if jobs:
        cmd.extend(['--jobs', str(jobs)])

    # Since we got here - we already have some  data != "nothing"
    if (data == 'auto') or \
        (
            (data == 'auto-if-wanted') and
            ds_repo.get_preferred_content('wanted', target)
        ):
        lgr.debug("Invoking copy --auto")
        cmd.append('--auto')

    if force not in ('all', 'checkdatapresent'):
        # if we force, we do not trust local knowledge and do the checks
        cmd.append('--fast')

    lgr.debug("Pushing data from %s to '%s'", ds, target)

    # input has type=dataset, but now it is about files
    res_kwargs.pop('type', None)

    # A set and a dict is used to track files pointing to the
    # same key.  The set could be dropped, using a single dictionary
    # that has an entry for every seen key and a (likely empty) list
    # of redundant files, but that would mean looping over potentially
    # many keys to yield likely few if any notneeded results.
    seen_keys = set()
    repkey_paths = dict()

    # produce final path list. use knowledge that annex command will
    # run in the root of the dataset and compact paths to be relative
    # to this location
    file_list = b''
    nbytes = 0
    for c in to_transfer:
        key = c['key']
        if key in seen_keys:
            repkey_paths.setdefault(key, []).append(c['path'])
        else:
            file_list += bytes(Path(c['path']).relative_to(ds.pathobj))
            file_list += b'\0'
            nbytes += c.get('bytesize', 0)
            seen_keys.add(key)
    lgr.debug('Counted %d bytes of annex data to transfer',
              nbytes)

    # and go
    res = ds_repo._call_annex_records(
        cmd,
        git_options=[
            "-c",
            "annex.retry={}".format(
                ds_repo.config.obtain("datalad.annex.retry"))]
            if ds_repo.config.get("annex.retry") else None,
        stdin=file_list,
        progress=True,
        # tailor the progress protocol with the total number of files
        # to be transferred
        total_nbytes=nbytes)
    for j in res:
        yield annexjson2result(j, ds, type='file', **res_kwargs)

    for annex_key, paths in repkey_paths.items():
        for path in paths:
            yield dict(
                res_kwargs, action='copy', type='file', status='notneeded',
                path=path, annexkey=annex_key,
                message='Another file points to the same key')
    return


def _get_corresponding_remote_state(repo, to):
    since = None
    # for managed branches we cannot assume a matching one at the remote end
    # instead we target the corresponding branch
    active_branch = repo.get_corresponding_branch() or repo.get_active_branch()

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
