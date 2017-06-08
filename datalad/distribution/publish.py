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

from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.annotate_paths import annotated2content_by_ds
from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import annex_copy_opts, recursion_flag, \
    recursion_limit, git_opts, annex_opts
from datalad.interface.common_opts import missing_sibling_opt
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import InsufficientArgumentsError

from datalad.utils import assure_list

from .dataset import EnsureDataset
from .dataset import Dataset
from .dataset import datasetmethod
from .dataset import require_dataset

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.distribution.publish')


def _log_push_info(pi_list, log_nothing=True):
    from git.remote import PushInfo as PI

    error = False
    if pi_list:
        for push_info in pi_list:
            if (push_info.flags & PI.ERROR) == PI.ERROR:
                lgr.debug('Push failed: %s', push_info.summary)
                error = True
            else:
                lgr.debug('Pushed: %s', push_info.summary)
    else:
        if log_nothing:
            lgr.debug("Pushed: nothing")
    return error


def _publish_dataset(ds, remote, refspec, paths, annex_copy_options, force=False,
                     **kwargs):
    # TODO: this setup is now quite ugly. The only way `refspec` can come
    # in, is when there is a tracking branch, and we get its state via
    # `refspec`

    def _publish_data():
        remote_wanted = ds.repo.get_preferred_content('wanted', remote)
        if (paths or annex_copy_options or remote_wanted) and \
            isinstance(ds.repo, AnnexRepo) and not \
            ds.config.getbool(
                'remote.{}'.format(remote),
                'annex-ignore',
                False):
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
            for r in ds.repo.copy_to(
                    files=[ap['path'] for ap in paths],
                    remote=remote,
                    options=annex_copy_options_):
                # TODO RF to have copy_to() yield JSON and convert that one
                # at present only the "good" results come out
                yield get_status_dict(status='ok', path=opj(ds.path, r),
                                      type='file', parentds=ds.path, **kwargs)
            # if ds.submodules:
            #     # NOTE: we might need to init them on the remote, but needs to
            #     #  be done only if remote is sshurl and it is not bare there
            #     #  (which I think we do not even support ATM)...
            #     #  or we could do that in the hook, as it is done for now
            #     #  (see create_sibling.py)
            #     #
            #     pass

            # if ds.repo.get_hexsha('git-annex') != git_annex_hexsha:
            #     # there were changes which should be pushed
            #     lgr.debug(
            #         "We have progressed git-annex branch should fetch/merge/push it to %s again",
            #         remote)
            #     ds.repo.fetch(remote=remote, refspec='git-annex')
            #     ds.repo.merge_annex(remote)
            #     _log_push_info(ds.repo.push(remote=remote, refspec=['git-annex']))

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
    # TODO RF diff detection into a standalone helper
    if force:
        # if forced -- we push regardless if there are differences or not
        diff = True
    # check if there are any differences wrt the to-be-published paths,
    # and if not skip this dataset
    else:
        if refspec:
            remote_branch_name = refspec[11:] \
                if refspec.startswith('refs/heads/') \
                else refspec
        else:
            # there was no tracking branch, check the push target
            remote_branch_name = ds.repo.get_active_branch()

        if remote_branch_name in ds.repo.repo.remotes[remote].refs:
            lgr.debug("Testing for changes with respect to '%s' of remote '%s'",
                      remote_branch_name, remote)
            current_commit = ds.repo.repo.commit()
            remote_ref = ds.repo.repo.remotes[remote].refs[remote_branch_name]
            within_ds_paths = [p['path'] for p in paths if p['path'] != ds.path]
            if within_ds_paths:
                # only if any paths is different from just the parentds root
                # in which case we can do the same muuuch cheaper (see below)
                # if there were custom paths, we will look at the diff
                lgr.debug("Since paths provided, looking at diff")
                diff = current_commit.diff(
                    remote_ref,
                    paths=within_ds_paths
                )
            else:
                # if commits differ at all
                lgr.debug("Since no paths provided, comparing commits")
                diff = current_commit != remote_ref.commit
        else:
            lgr.debug("Remote '%s' has no branch matching %r. Will publish",
                      remote, remote_branch_name)
            # we don't have any remote state, need to push for sure
            diff = True

    # # remote might be set to be ignored by annex, or we might not even know yet its uuid
    # annex_ignore = ds.config.getbool('remote.{}.annex-ignore'.format(remote), None)
    # annex_uuid = ds.config.get('remote.{}.annex-uuid'.format(remote), None)
    # if not annex_ignore:
    #     if annex_uuid is None:
    #         # most probably not yet 'known' and might require some annex
    knew_remote_uuid = True
    if isinstance(ds.repo, AnnexRepo) and \
            ds.config.get('.'.join(('remote', remote, 'annex-uuid')), None):
        # we can try publishing right away
        for r in _publish_data():
            yield r
    else:
        knew_remote_uuid = False

    if not diff:
        lgr.debug("No changes detected with respect to state of '%s'", remote)
        yield get_status_dict(ds=ds, status='notneeded', **kwargs)
        # there could still be paths to be copied
    else:
        # publishing of `remote` might depend on publishing other
        # remote(s) first:
        # define config var name for potential publication dependencies
        depvar = 'remote.{}.datalad-publish-depends'.format(remote)
        for d in assure_list(ds.config.get(depvar, [])):
            lgr.info("Dependency detected: '%s'" % d)
            # call this again to take care of the dependency first,
            # but keep the paths the same, as the goal is to publish those
            # to the primary remote, and not anything elase to a dependency
            for r in _publish_dataset(
                    ds,
                    d,
                    None,
                    paths,
                    annex_copy_options,
                    force=force,
                    **kwargs):
                yield r

        lgr.info("Publishing {0} to {1}".format(ds, remote))

        # in order to be able to use git's config to determine what to push,
        # we need to annex merge first. Otherwise a git push might be
        # rejected if involving all matching branches for example.
        # Once at it, also push the annex branch right here.
        if isinstance(ds.repo, AnnexRepo):
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
            if isinstance(ds.repo, AnnexRepo):
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
        if isinstance(ds.repo, AnnexRepo):
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
        lgr.debug("Attempt to push '%s' to sibling '%s'", things2push, remote)
        _log_push_info(ds.repo.push(remote=remote, refspec=things2push))
        if things2push and ds.config.get('remote.{}.push'.format(remote)):
            # since current state of ideas is to push both auto-detected and the
            # possibly prescribed, if anything was, let's push again to possibly
            # push left-over prescribed ones.
            lgr.debug("Secondary push since custom push targets provided")
            _log_push_info(ds.repo.push(remote=remote), log_nothing=False)

        yield get_status_dict(ds=ds, status='ok', **kwargs)

    if isinstance(ds.repo, AnnexRepo) and knew_remote_uuid is False:
        # publish only after we tried to sync/push and if it was annex repo
        for r in _publish_data():
            yield r


def _get_remote_info(ds_path, ds_remote_info, to, missing):
    """Returns None if desired info was obtained, or a tuple (status, message)
    if not"""
    ds = Dataset(ds_path)
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
                    ("Unkown target sibling '%s', skipping publication", to))
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
      Git repositories, or git-annex special remotes (if their support data
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
            to decide either updated publishing is necessary for this and which children.
            If empty argument is provided, then we will always run publish command.
            By default, would take from the previously published to that remote/sibling
            state (for the current branch)"""),
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
        #transfer_data=Parameter(
        #    args=("--transfer-data",),
        #    doc="""ADDME""",
        #    constraints=EnsureChoice('auto', 'none', 'all')),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_copy_opts=annex_copy_opts,
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
            #transfer_data='auto',
            recursive=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_copy_opts=None,
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
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            remote_info_result = None
            if ap.get('type', 'dataset') != 'dataset':
                # for everything that is not a dataset get the remote info
                # for the parent
                parentds = ap.get('parentds', None)
                if parentds and parentds not in ds_remote_info:
                    remote_info_result = _get_remote_info(
                        parentds, ds_remote_info, to, missing)
            else:
                # this is a dataset
                if ap.get('state', None) == 'absent':
                    ap['status'] = 'impossible'
                    ap['message'] = 'subdataset is not installed'
                    yield ap
                    continue
                # if this is a dataset, get the remote info for itself
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
                refds_path=refds_path,
                path_only=False)
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
                    # RF to take APs
                    paths=content_by_ds[ds_path],
                    annex_copy_options=annex_copy_opts,
                    force=force,
                    **res_kwargs):
                yield r
