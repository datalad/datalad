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
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
    EnsureChoice,
)
from datalad.utils import (
    assure_list,
)

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.core.local.diff import Diff


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
    reflected in to current state of the top-level reference dataset.
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
            doc=""""specify the dataset to push""",
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
            doc="""specifies commit (treeish, tag, etc.) from which to look for
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
            making: ...""",
            constraints=EnsureChoice('no-datatransfer', 'datatransfer', None)),
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
        paths = assure_list(path)

        ds = require_dataset(
            dataset, check_installed=True, purpose='pushing')

        if not since and since is not None:
            # TODO figure out state of remote branch and set `since`
            pass

        # obtain a generator for information on the datasets to process
        if since:
            ds_spec = _datasets_since_(
                dataset, since, paths, recursive, recursion_limit)
        else:
            ds_spec = _datasets_no_since_(
                dataset, paths, recursive, recursion_limit)

        res_kwargs = dict(
            action='publish',
            refds=ds.path,
            logger=lgr,
        )
        # instead of a loop, this could all be done in parallel
        for dspath, dsrecords in ds_spec:
            yield from _push(
                dspath, dsrecords, to, force, jobs, res_kwargs.copy())


def _datasets_since_(dataset, since, paths, recursive, recursion_limit):
    """Generator"""
    # rely on diff() reporting sequentially across datasets
    cur_ds = None
    ds_res = None
    for res in Diff.__call__(
            dataset=dataset,
            fr=since,
            # we never touch unsaved content
            to='HEAD',
            # we need to know what is around locally to be able
            # to report something that should have been pushed
            # but could not, because we don't have a copy
            annex='availability',
            recursive=recursive,
            recursion_limit=recursion_limit,
            result_renderer=None):
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
    if ds_res:
        yield (cur_ds, ds_res)


def _datasets_no_since_(dataset, paths, recursive, recursion_limit):
    """Generator"""
    # TODO
    pass


def _push(dspath, content, target, force, jobs, res_kwargs,
          done_fetch=None):
    if not done_fetch:
        done_fetch = set()
    # nothing recursive in here, we only need a repo to work with
    ds = Dataset(dspath)
    repo = ds.repo

    res_kwargs.update(type='dataset', path=dspath)

    if not target:
        # let Git figure out what needs doing
        wannabe_gitpush = repo.push(remote=None, git_options=['--dry-run'])
        # we did not get an explicit push target, get it from Git
        target = set(p.get('remote', None) for p in wannabe_gitpush)
        # handle case where a pushinfo record did not have a 'remote'
        # property -- should not happen, but be robust
        target.discard(None)
        if not len(target):
            yield dict(
                res_kwargs,
                status='error',
                message='No push target given, and none could be '
                        'auto-detected',
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
    lgr.debug("Attempt to push to '%s'", target)

    # define config var name for potential publication dependencies
    depvar = 'remote.{}.datalad-publish-depends'.format(target)
    # list of remotes that are publication dependencies for the
    # target remote
    publish_depends = assure_list(ds.config.get(depvar, []))
    if publish_depends:
        lgr.debug("Discovered publication dependencies for '%s': %s'",
                  target, publish_depends)

    # remote might be set to be ignored by annex, or we might not even know its
    # uuid yet. make sure we are up-to-date on this topic on all affected
    # remotes, before we start making decisions
    need_config_reload = False
    for r in publish_depends + [target]:
        if r in done_fetch:
            # saw this in another life already
            continue
        need_config_reload = True
        if not ds.config.get('.'.join(('remote', r, 'annex-uuid')), None):
            lgr.debug("Obtain remote annex info from '%s'", r)
            # TODO should we somehow report on the result, maybe at
            # least a debug message
            repo.fetch(remote=r)
            # prevent refetch in dependency processing
            done_fetch.add(r)
            # in order to be able to use git's config to determine what to push,
            # we need to annex merge first. Otherwise a git push might be
            # rejected if involving all matching branches for example.
            # NOTE we should not use a precomputed 'is_annex' test here, as
            # each fetch could give evidence that there is an annex
            # somewhere and replace the repo class...
            if isinstance(ds.repo, AnnexRepo):
                repo.merge_annex(r)
    if need_config_reload:
        ds.config.reload()

    # anything that follows will not change the repo type anymore, cache
    # (but the fetch and merge_annex() above could have, so do not move
    # upwards
    is_annex_repo = isinstance(ds.repo, AnnexRepo)

    # TODO prevent this when `target` is a special remote
    # (possibly redo) a push attempt to figure out what needs pushing
    # do this on the main target only, and apply the result to all
    # dependencies
    wannabe_gitpush = repo.push(remote=target, git_options=['--dry-run'])
    refspecs2push = [
        # ignore the "to" mapping here, might be different for a
        # publication dependency
        #'{}:{}'.format(p['from_ref'], p['to_ref'])
        p['from_ref']
        for p in wannabe_gitpush
        # TODO: what if a publication dependency doesn't have it yet
        # should be not attempt to push, because the main target has it?
        if 'uptodate' not in p['operations']
    ]
    if is_annex_repo:
        # always attempt to push the annex branch
        refspecs2push.append('git-annex')

    # we know what to push and where, now dependency processing first
    for r in publish_depends:
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

    #
    # TODO git-annex data move handling first
    #

    # TODO inefficient, but push only takes a single refspec at a time
    # at the moment, enhance GitRepo.push() to do all at once
    push_res = []
    for refspec in refspecs2push:
        push_res.extend(repo.push(
            remote=target,
            refspec=refspec,
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
