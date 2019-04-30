# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for dataset (component) publishing

"""

import logging
import re
from collections import OrderedDict
from os.path import join as opj

from git.remote import PushInfo as PI

from datalad import ssh_manager
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.base import build_doc
from datalad.interface.utils import eval_results
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import annex_copy_opts, recursion_flag, \
    recursion_limit, git_opts, annex_opts, jobs_opt
from datalad.interface.common_opts import missing_sibling_opt
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.annexrepo import AnnexRepo
from datalad.support.sshconnector import sh_quote
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.network import URL, RI, SSHRI, is_ssh

from datalad.utils import assure_list
from datalad.dochelpers import exc_str

from .dataset import EnsureDataset
from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import require_dataset

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.publish')


def _push(ds, remote, things2push, force=False):
    lgr.debug("Attempt to push '%s' to sibling '%s'", things2push, remote)
    push_res = ds.repo.push(remote=remote, refspec=things2push, force=force)
    if things2push and ds.config.get('remote.{}.push'.format(remote)):
        # we aim to push both auto-detected and possibly configured once
        # above we pushed the result of auto-detection, now push the
        # configured ones
        lgr.debug("Secondary push since custom push targets provided")
        push_res.extend(
            ds.repo.push(remote=remote, force=force))
    if not push_res:
        return 'notneeded', 'Git reported nothing was pushed'
    errors = ['{} -> {} {}'.format(
        pi.local_ref,
        pi.remote_ref,
        pi.summary.strip()) for pi in push_res if (pi.flags & PI.ERROR) == PI.ERROR]
    successes = [pi.summary.strip() for pi in push_res if (pi.flags & PI.ERROR) != PI.ERROR]
    if errors:
        return 'error', \
               ('failed to push to %s: %s;%s',
                remote,
                '; '.join(errors),
                ' pushed: {}'.format(successes) if successes else '')
    else:
        return 'ok', ('pushed to %s: %s', remote, successes)


def has_diff(ds, refspec, remote, paths):
    """Return bool if a dataset was modified wrt to a given remote state"""
    if refspec:
        remote_branch_name = refspec[11:] \
            if refspec.startswith('refs/heads/') \
            else refspec
    else:
        # there was no tracking branch, check the push target
        remote_branch_name = ds.repo.get_active_branch()

    remote_ref = '/'.join((remote, remote_branch_name))
    if remote_ref not in ds.repo.get_remote_branches():
        lgr.debug("Remote '%s' has no branch matching %r. Will publish",
                  remote, remote_branch_name)
        # we don't have any remote state, need to push for sure
        return True

    lgr.debug("Testing for changes with respect to '%s' of remote '%s'",
              remote_branch_name, remote)
    current_commit = ds.repo.get_hexsha()
    within_ds_paths = [p['path'] for p in paths if p['path'] != ds.path]
    commit_differ = current_commit != ds.repo.get_hexsha(remote_ref)
    # yoh: not sure what "logic" was intended here for comparing only
    # some files.  By now we get a list of files, if any were changed,
    # from the commit on remote, and somehow diff says below that they didn't differ...
    # but if commit is different -- there must be differences and we
    # should publish. otherwise now skips publishing root dataset
    # although its master is behind by 1 commit.  Moreover there could
    # be an empty commit -- shouldn't we publish then???
    if not commit_differ and within_ds_paths:
        # only if any paths is different from just the parentds root
        # in which case we can do the same muuuch cheaper (see below)
        # if there were custom paths, we will look at the diff
        lgr.debug("Since paths provided, looking at diff")
        return any(r["state"] != "clean"
                   for r in ds.diff(path=within_ds_paths,
                                    fr="HEAD",
                                    to=remote_ref,
                                    untracked="no"))
    else:
        # if commits differ at all
        lgr.debug("Since no paths provided, comparing commits")
        return commit_differ


def _publish_data(ds, remote, paths, annex_copy_options, force, transfer_data, **kwargs):
    # paths are annotated paths for now, changes below
    if not isinstance(ds.repo, AnnexRepo):
        # impossible to publish annex'ed data
        return

    if ds.config.getbool('remote.{}'.format(remote), 'annex-ignore', False):
        # configuration says: don't do it
        return

    if not ds.config.get('.'.join(('remote', remote, 'annex-uuid')), None):
        # this remote either isn't an annex, or hasn't been properly initialized
        for ap in paths:
            # this is only a problem if this path
            ap['status'] = 'impossible' \
                           if transfer_data == 'all' or ap.get('raw_input', False) \
                           else 'notneeded'
            ap['message'] = \
                ("annex for remote '%s' not available, or not properly configured",
                 remote)
            yield ap
        return

    # what data to transfer?
    if transfer_data == 'all':
        paths = ['.']
    elif transfer_data == 'auto':
        # keep only paths that were requested and are not the base path of the dataset
        # if the resulting list is empty, the "auto" mode of _publish_data() will
        # kick in and consult "wanted"
        paths = [p['path'] for p in paths
                 if p.get('raw_input', False) and
                 not p['path'] == ds.path]
    else:
        raise ValueError(
            "unknown label '{}' for `transfer_data` option".format(
                transfer_data))

    # TODO do we really have to call annex for that, or can we take it from
    # the config instead?
    remote_wanted = ds.repo.get_preferred_content('wanted', remote)
    if not (paths or annex_copy_options or remote_wanted):
        # nothing that we could tell git annex
        return

    # we should now know what needs doing
    lgr.info("Publishing {0} data to {1}".format(ds, remote))
    # overwrite URL with pushurl if any, reason:
    # https://git-annex.branchable.com/bugs/annex_ignores_pushurl_and_uses_only_url_upon___34__copy_--to__34__/
    # Note: This shouldn't happen anymore with newly added siblings.
    #       But for now check for it, until we agree on how to fix existing
    #       ones.
    pushurl = ds.config.get('remote.{}.pushurl'.format(remote), None)
    annexurl = ds.config.get('remote.{}.annexurl'.format(remote), None)
    annex_copy_options_ = annex_copy_options or ''
    if pushurl and not annexurl:
        annex_copy_options_ += ' -c "remote.{}.annexurl={}"'.format(remote, pushurl)
    if not paths and remote_wanted:
        lgr.debug("Invoking copy --auto")
        annex_copy_options_ += ' --auto'
    # TODO:  we might need additional logic comparing the state of git-annex
    # branch locally and on remote to see if information about the 'copy'
    # was also reflected on the remote end
    #git_annex_hexsha = ds.repo.get_hexsha('git-annex')
    # TODO: must be the same if we merged/pushed before, if not -- skip
    # special logic may be with a warning
    if not force:
        # if we force, we do not trust local knowledge and do the checks
        annex_copy_options_ += ' --fast'
    # TODO this things needs to return JSON
    ncopied = 0
    for r in ds.repo.copy_to(
            files=[p for p in paths
                   # TODO we may have to check for any file in Git, but this one can
                   # easily happen with --since
                   if not p == opj(ds.path, '.gitmodules')],
            remote=remote,
            options=annex_copy_options_):
        ncopied += 1
        # TODO RF to have copy_to() yield JSON and convert that one
        # at present only the "good" results come out
        yield get_status_dict(status='ok', path=opj(ds.path, r),
                              type='file', parentds=ds.path, **kwargs)

    if ncopied:
        _check_and_update_remote_server_info(ds, remote)

    # if ds.submodules:
    #     # NOTE: we might need to init them on the remote, but needs to
    #     #  be done only if remote is sshurl and it is not bare there
    #     #  (which I think we do not even support ATM)...
    #     #  or we could do that in the hook, as it is done for now
    #     #  (see create_sibling.py)
    #     #
    #     pass

    # TODO unclear why this was commented out
    # if ds.repo.get_hexsha('git-annex') != git_annex_hexsha:
    #     # there were changes which should be pushed
    #     lgr.debug(
    #         "We have progressed git-annex branch should fetch/merge/push it to %s again",
    #         remote)
    #     ds.repo.fetch(remote=remote, refspec='git-annex')
    #     ds.repo.merge_annex(remote)
    #     _log_push_info(ds.repo.push(remote=remote, refspec=['git-annex']))


def _check_and_update_remote_server_info(ds, remote):
    # if we managed to copy to "http" url  we should should try to trigger git
    # update-server-info hook on the remote if there was ssh annexurl defined
    # for it. Apparently we do that already in create_sibling ones, but here
    # we need more checks and preparation
    remote_url = ds.repo.config.get('remote.%s.url' % remote, None)
    if remote_url:
        remote_url = RI(remote_url)
        if isinstance(remote_url, URL) and remote_url.scheme in (
        'http', 'https'):
            remote_annexurl = ds.repo.config.get('remote.%s.annexurl' % remote,
                                                 None)
            if remote_annexurl:
                remote_annexurl_ri = RI(remote_annexurl)
                if is_ssh(remote_annexurl_ri):
                    ssh = ssh_manager.get_connection(remote_annexurl_ri)
                    ssh('git -C {} update-server-info'.format(
                        sh_quote(remote_annexurl_ri.path)))
                    return True
                else:
                    lgr.debug(
                        "There is no annexurl defined but not ssh: %s, "
                        "dunno if "
                        "we could/should do anything", remote_annexurl
                    )
    return False


def _publish_dataset(ds, remote, refspec, paths, annex_copy_options, force=False, jobs=None,
                     transfer_data='auto', **kwargs):
    # TODO: this setup is now quite ugly. The only way `refspec` can come
    # in, is when there is a tracking branch, and we get its state via
    # `refspec`

    # define config var name for potential publication dependencies
    depvar = 'remote.{}.datalad-publish-depends'.format(remote)
    # list of remotes that are publication dependencies for the
    # target remote
    publish_depends = assure_list(ds.config.get(depvar, []))

    # remote might be set to be ignored by annex, or we might not even know yet its uuid
    # make sure we are up-to-date on this topic on all affected remotes, before
    # we start making decisions
    for r in publish_depends + [remote]:
        if not ds.config.get('.'.join(('remote', remote, 'annex-uuid')), None):
            lgr.debug("Obtain remote annex info from '%s'", r)
            ds.repo.fetch(remote=r)
            # in order to be able to use git's config to determine what to push,
            # we need to annex merge first. Otherwise a git push might be
            # rejected if involving all matching branches for example.
            # NOTE we should not use a precomputed 'is_annex' test here, as
            # each fetch could give evidence that there is an annex
            # somewhere and replace the repo class...
            if isinstance(ds.repo, AnnexRepo):
                ds.repo.merge_annex(r)
    ds.config.reload()

    # anything that follows will not change the repo type anymore, cache
    is_annex_repo = isinstance(ds.repo, AnnexRepo)

    # Plan:
    # 1. Check if there is anything to push, and if so
    #    2. process push dependencies
    #    3. fetch and merge annex branch
    #    4. push non-annex branch(es)
    # 5. copy data to the remote if paths are provided or it wants something generally

    # upstream refspec needed for update (merge) and subsequent push,
    # in case there is no.
    # no tracking refspec yet?

    # TODO: i think this whole modification detection could be done by path
    # annotation at the very beginning -- keeping it for now to not get too
    # dizzy in the forehead....

    # if forced -- we push regardless if there are differences or not
    diff = True if force else has_diff(ds, refspec, remote, paths)

    # We might have got new information in git-annex branch although no other
    # changes
    if not diff and is_annex_repo:
        try:
            git_annex_commit = next(ds.repo.get_branch_commits('git-annex'))
        except StopIteration:
            git_annex_commit = None
        #diff = _get_remote_diff(ds, [], git_annex_commit, remote, 'git-annex')
        diff = _get_remote_diff(ds, git_annex_commit, remote, 'git-annex')
        if diff:
            lgr.info("Will publish updated git-annex")

    #
    # publish data (annex copy --to)
    #
    # # remote might be set to be ignored by annex, or we might not even know yet its uuid
    # annex_ignore = ds.config.getbool('remote.{}.annex-ignore'.format(remote), None)
    # annex_uuid = ds.config.get('remote.{}.annex-uuid'.format(remote), None)
    # if not annex_ignore:
    #     if annex_uuid is None:
    #         # most probably not yet 'known' and might require some annex

    copied_data = False
    # skip right away if data transfer is not desired
    if transfer_data != 'none' and isinstance(ds.repo, AnnexRepo):
        # publishing of `remote` might depend on publishing other
        # remote(s) first, so they need to receive the data first:
        for d in publish_depends:
            lgr.info("Transferring data to configured publication dependency: '%s'" % d)
            # properly initialized remote annex -> publish data
            for r in _publish_data(
                    ds,
                    d,
                    paths,
                    annex_copy_options,
                    force,
                    transfer_data,
                    **kwargs):
                # note if we published any data, notify to sync annex branch below
                if r['status'] == 'ok' and r['action'] == 'publish' and \
                        r.get('type', None) == 'file':
                    copied_data = True
                yield r
        # and for the main target
        for r in _publish_data(
                ds,
                remote,
                paths,
                annex_copy_options,
                force,
                transfer_data,
                **kwargs):
            # note if we published any data, notify to sync annex branch below
            if r['status'] == 'ok' and r['action'] == 'publish' and \
                    r.get('type', None) == 'file':
                copied_data = True
            yield r

    #
    # publish dataset (git push)
    #
    if not diff and not copied_data:
        lgr.debug("No changes detected with respect to state of '%s'", remote)
        yield get_status_dict(ds=ds, status='notneeded', **kwargs)
    else:
        # publishing of `remote` might depend on publishing other
        # remote(s) first:
        for d in publish_depends:
            lgr.info("Publishing to configured dependency: '%s'" % d)
            # call this again to take care of the dependency first,
            # but keep the paths the same, as the goal is to publish those
            # to the primary remote, and not anything elase to a dependency
            for r in _publish_dataset(
                    ds,
                    d,
                    # should get the same as the base dataset
                    refspec,
                    paths,
                    annex_copy_options,
                    force=force,
                    jobs=jobs,
                    transfer_data=transfer_data,
                    **kwargs):
                yield r

        if is_annex_repo and \
                ds.repo.is_special_annex_remote(remote):
            # There is nothing else to "publish"
            lgr.debug(
                "{0} is a special annex remote, no git push is needed".format(remote)
            )
            return

        lgr.info("Publishing {0} to {1}".format(ds, remote))
        # in order to be able to use git's config to determine what to push,
        # we need to annex merge first. Otherwise a git push might be
        # rejected if involving all matching branches for example
        # even if we already fetched above we need to do it again
        if is_annex_repo:
            lgr.debug("Obtain remote annex info from '%s'", remote)
            ds.repo.fetch(remote=remote)
            ds.repo.merge_annex(remote)

        # Note: git's push.default is 'matching', which doesn't work for first
        # time publication (a branch, that doesn't exist on remote yet)
        # But if we want to respect remote.*.push entries, etc. we need to
        # not pass a specific refspec (like active branch) to `git push`
        # by default.
        # hence we amend any existing config on the fly
        # TODO: what else to push by default?
        # consider also: --follow-tags, --tags, --atomic
        # make sure we push
        things2push = []
        current_branch = ds.repo.get_active_branch()
        if current_branch:  # possibly make this conditional on a switch
            # TODO: this should become it own helper
            if is_annex_repo:
                # annex could manage this branch
                if current_branch.startswith('annex/direct') \
                        and ds.config.getbool('annex', 'direct', default=False):
                    # this is a "fake" annex direct mode branch
                    # we want to publish the underlying branch
                    current_branch = current_branch[12:]
                match_adjusted = re.match(
                    'adjusted/(.*)\([a-z]*\)',
                    current_branch)
                if match_adjusted:
                    # adjusted/master(...)
                    # TODO:  this code is not tested
                    # see https://codecov.io/gh/datalad/datalad/src/17e67045a088ae0372b38aa4d8d46ecf7c821cb7/datalad/distribution/publish.py#L156
                    # and thus probably broken -- test me!
                    current_branch = match_adjusted.group(1)
            things2push.append(current_branch)
        if is_annex_repo:
            things2push.append('git-annex')
        # check that all our magic found valid branches
        things2push = [t for t in things2push if t in ds.repo.get_branches()]
        # check that we don't ask to push things that are already configured
        # -> would cause error
        # TODO need to find a way to properly do this, when wildcards are used
        # in the push configuration variable
        things2push = [t for t in things2push
                       if t not in ds.config.get('remote.{}.push'.format(remote), [])]
        # now we know what to push where
        status, msg = _push(ds, remote, things2push, force)
        yield get_status_dict(ds=ds, status=status, message=msg, **kwargs)


def _get_remote_info(ds_path, ds_remote_info, to, missing):
    """Returns None if desired info was obtained, or a tuple (status, message)
    if not"""
    ds = Dataset(ds_path)
    if ds.repo is None:
        # There is no repository, nothing could be done
        return ('impossible',
                'No repository found for %s' % ds)
    if to is None:
        # we need an upstream remote, if there's none given. We could
        # wait for git push to complain, but we need to explicitly
        # figure it out for pushing annex branch anyway and we might as
        # well fail right here.
        track_remote, track_refspec = ds.repo.get_tracking_branch()
        if not track_remote:
            # no tracking remote configured, but let try one more
            # if we only have one remote, and it has a push target
            # configured that is "good enough" for us
            cand_remotes = [r for r in ds.repo.get_remotes()
                            if 'remote.{}.push'.format(r) in ds.config]
            if len(cand_remotes) > 1:
                lgr.warning('Target sibling ambiguous, please specific via --to')
            elif len(cand_remotes) == 1:
                track_remote = cand_remotes[0]
            else:
                return ('impossible',
                        'No target sibling configured for default publication, '
                        'please specific via --to')
        if track_remote:
            ds_remote_info[ds_path] = dict(zip(
                ('remote', 'refspec'),
                (track_remote, track_refspec)))
        elif missing == 'skip':
            ds_remote_info[ds_path] = None
            return ('notneeded',
                    'Cannot determine target sibling, skipping publication')
        else:
            # we have no remote given and no upstream
            return 'error', 'Cannot determine a default target sibling for publication'
    elif to not in ds.repo.get_remotes():
        # unknown given remote
        if missing == 'skip':
            ds_remote_info[ds_path] = None
            return ('notneeded',
                    ("Unknown target sibling '%s', skipping publication", to))
        elif missing == 'inherit':
            superds = ds.get_superdataset()
            if not superds:
                return ('error',
                        ("No super-dataset to inherit settings for remote %s", to))
            # XXX due to difference between create-sibling and create-sibling-github
            # would not be as transparent to inherit for -github
            lgr.info("Will try to create a sibling inheriting settings from %s", superds)
            # XXX explicit None as sshurl for now
            # TODO this is not good: e.g. #1344
            ds.create_sibling(None, name=to, inherit=True)
            ds_remote_info[ds_path] = {'remote': to}
        else:
            return ('error',
                    ("Unknown target sibling '%s' for publication", to))
    else:
        # all good: remote given and is known
        ds_remote_info[ds_path] = {'remote': to}



def _get_remote_diff(ds, current_commit, remote, remote_branch_name):
#def _get_remote_diff(ds, paths, current_commit, remote, remote_branch_name):
    """Helper to check if remote has different state of the branch"""
    if remote_branch_name in ds.repo.repo.remotes[remote].refs:
        lgr.debug("Testing for changes with respect to '%s' of remote '%s'",
                  remote_branch_name, remote)
        if current_commit is None:
            current_commit = ds.repo.repo.commit()
        remote_ref = ds.repo.repo.remotes[remote].refs[remote_branch_name]
        # XXX: ATM nothing calls this function with a non-empty `paths` arg
        #if paths:
        #    # if there were custom paths, we will look at the diff
        #    lgr.debug("Since paths provided, looking at diff")
        #    diff = current_commit.diff(
        #        remote_ref,
        #        paths=paths
        #    )
        #else:
        # if commits differ at all
        lgr.debug("Since no paths provided, comparing commits")
        diff = current_commit != remote_ref.commit
    else:
        lgr.debug("Remote '%s' has no branch matching %r. Will publish",
                  remote, remote_branch_name)
        # we don't have any remote state, need to push for sure
        diff = True

    return diff


@build_doc
class Publish(Interface):
    """Publish a dataset to a known :term:`sibling`.

    This makes the last saved state of a dataset available to a sibling
    or special remote data store of a dataset. Any target sibling must already
    exist and be known to the dataset.

    Optionally, it is possible to limit publication to change sets relative
    to a particular point in the version history of a dataset (e.g. a release
    tag). By default, the state of the local dataset is evaluated against the
    last known state of the target sibling. Actual publication is only attempted
    if there was a change compared to the reference state, in order to speed up
    processing of large collections of datasets. Evaluation with respect to
    a particular "historic" state is only supported in conjunction with a
    specified reference dataset. Change sets are also evaluated recursively, i.e.
    only those subdatasets are published where a change was recorded that is
    reflected in to current state of the top-level reference dataset.
    See "since" option for more information.

    Only publication of saved changes is supported. Any unsaved changes in a
    dataset (hierarchy) have to be saved before publication.

    .. note::
      Power-user info: This command uses :command:`git push`, and :command:`git annex copy`
      to publish a dataset. Publication targets are either configured remote
      Git repositories, or git-annex special remotes (if they support data
      upload).
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True
    # TODO: Figure out, how to tell about tracking branch/upstream
    #      (and the respective remote)
    #      - it is used, when no destination is given
    #      - it is configured to be the given destination, if there was no
    #        upstream set up before, so you can use just "datalad publish" next
    #        time.

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            metavar='DATASET',
            doc="""specify the (top-level) dataset to be published. If no dataset
            is given, the datasets are determined based on the input arguments""",
            constraints=EnsureDataset() | EnsureNone()),
        to=Parameter(
            args=("--to",),
            metavar='LABEL',
            doc="""name of the target sibling. If no name is given an attempt is
            made to identify the target based on the dataset's configuration
            (i.e. a configured tracking branch, or a single sibling that is
            configured for publication)""",
            # TODO: See TODO at top of class!
            constraints=EnsureStr() | EnsureNone()),
        since=Parameter(
            args=("--since",),
            constraints=EnsureStr() | EnsureNone(),
            doc="""When publishing dataset(s), specifies commit (treeish, tag, etc)
            from which to look for changes
            to decide whether updated publishing is necessary for this and which children.
            If empty argument is provided, then we would take from the previously 
            published to that remote/sibling state (for the current branch)"""),
        # since: commit => .gitmodules diff to head => submodules to publish
        missing=missing_sibling_opt,
        path=Parameter(
            args=("path",),
            metavar='PATH',
            # TODO this description is no longer correct
            doc="path(s), that may point to file handle(s) to publish including "
                "their actual content or to subdataset(s) to be published. If a "
                "file handle is published with its data, this implicitly means "
                "to also publish the (sub)dataset it belongs to. '.' as a path "
                "is treated in a special way in the sense, that it is passed "
                "to subdatasets in case `recursive` is also given.",
            constraints=EnsureStr() | EnsureNone(),
            nargs='*'),
        force=Parameter(
            args=("-f", "--force",),
            doc="""enforce doing publish activities (git push etc) regardless of
            the analysis if they seemed needed""",
            action='store_true'),
        # TODO add option to decide what branch/repo to push
        transfer_data=Parameter(
            args=("--transfer-data",),
            doc="""ADDME""",
            constraints=EnsureChoice('auto', 'none', 'all')),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_copy_opts=annex_copy_opts,
        jobs=jobs_opt,
    )

    @staticmethod
    @datasetmethod(name='publish')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            to=None,
            since=None,
            missing='fail',
            force=False,
            transfer_data='auto',
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_copy_opts=None,
            jobs=None
    ):

        # if ever we get a mode, for "with-data" we would need this
        #if dataset and not path:
        #    # act on the whole dataset if nothing else was specified
        #    path = dataset.path if isinstance(dataset, Dataset) else dataset

        if not dataset and not path:
            # try to find a dataset in PWD
            dataset = require_dataset(
                None, check_installed=True, purpose='publishing')

        if since and not dataset:
            raise InsufficientArgumentsError(
                'Modification detection (--since) without a base dataset '
                'is not supported')

        if dataset and since == '':
            # only update since last update so we figure out what was the last update
            active_branch = dataset.repo.get_active_branch()
            if to:
                # XXX here we assume one to one mapping of names from local branches
                # to the remote
                since = '%s/%s' % (to, active_branch)
            else:
                # take tracking remote for the active branch
                tracked_remote, tracked_refspec = dataset.repo.get_tracking_branch()
                if tracked_remote:
                    if tracked_refspec.startswith('refs/heads/'):
                        tracked_refspec = tracked_refspec[len('refs/heads/'):]
                    #to = tracked_remote
                    since = '%s/%s' % (tracked_remote, tracked_refspec)
                else:
                    lgr.info(
                        "No tracked remote for %s. since option is of no effect",
                        active_branch
                    )
                    since = None

        # here is the plan
        # 1. figure out remote to publish to
        # 2. figure out which content needs to be published to this remote
        # 3. look for any pre-publication dependencies of that remote
        #    (i.e. remotes that need to be published to before)
        # 4. publish the content needed to go to the primary remote to
        #    the dependencies first, and to the primary afterwards
        ds_remote_info = {}

        refds_path = Interface.get_refds_path(dataset)
        res_kwargs = dict(refds=refds_path, logger=lgr, action='publish')

        to_process = []
        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='publish',
                unavailable_path_status='impossible',
                nondataset_path_status='error',
                modified=since,
                return_type='generator',
                on_failure='ignore',
                force_no_revision_change_discovery=False, # we cannot publish what was not committed
                force_untracked_discovery=False  # we cannot publish untracked
        ):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            remote_info_result = None
            if ap.get('type', ap.get('type_src', 'dataset')) != 'dataset':
                # for everything that is not a dataset get the remote info
                # for the parent
                parentds = ap.get('parentds', None)
                if parentds and parentds not in ds_remote_info:
                    remote_info_result = _get_remote_info(
                        parentds, ds_remote_info, to, missing)
            else:
                # this is a dataset
                if ap.get('state', None) == 'absent':
                    continue
                # get the remote info for itself
                remote_info_result = _get_remote_info(
                    ap['path'], ds_remote_info, to, missing)
                ap['process_content'] = True
            if remote_info_result is not None:
                ap['status'] = remote_info_result[0]
                ap['message'] = remote_info_result[1]
                yield ap
                continue
            to_process.append(ap)

        content_by_ds, ds_props, completed, nondataset_paths = \
            annotated2content_by_ds(
                to_process,
                refds_path=refds_path)
        assert(not completed)

        lgr.debug(
            "Evaluating %i dataset publication candidate(s)",
            len(content_by_ds))
        # TODO: fancier sorting, so we still follow somewhat the hierarchy
        #       in sorted order, e.g.
        #  d1/sub1/sub1
        #  d1/sub1
        #  d1
        #  d2/sub1
        #  d2
        content_by_ds = OrderedDict(
            (d, content_by_ds[d]) for d in sorted(content_by_ds, reverse=True)
        )

        lgr.debug("Attempt to publish %i datasets", len(content_by_ds))
        for ds_path in content_by_ds:
            remote_info = ds_remote_info.get(ds_path, None)
            if remote_info is None:
                # maybe this dataset wasn't annotated above, try to get info
                # MIH: I think this entire if-branch is practically impossible
                # to reach. It is certainly untested, but I think this is due
                # to mutually exclusive conditions during remote_info detection
                remote_info_result = _get_remote_info(
                    ds_path, ds_remote_info, to, missing)
                if remote_info_result is not None:
                    yield get_status_dict(
                        type='dataset',
                        path=ds_path,
                        status=remote_info_result[0],
                        message=remote_info_result[1],
                        **res_kwargs)
                    continue
                # continue with freshly obtained info
                remote_info = ds_remote_info[ds_path]
                # condition above must catch all other cases
                assert remote_info
            # and publish
            ds = Dataset(ds_path)
            for r in _publish_dataset(
                    ds,
                    remote=remote_info['remote'],
                    refspec=remote_info.get('refspec', None),
                    # only send paths that were explicitly requested
                    paths=[p for p in content_by_ds[ds_path]
                           # do not feed (sub)dataset paths into the beast
                           # makes no sense to try to annex copy them
                           # for the base dataset itself let `transfer_data`
                           # decide
                           if p.get('type', None) != 'dataset'],
                    annex_copy_options=annex_copy_opts,
                    force=force,
                    jobs=jobs,
                    transfer_data=transfer_data,
                    **res_kwargs):
                yield r
