# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Interface to add content, and save modifications to a dataset

"""

__docformat__ = 'restructuredtext'

import logging
from functools import partial
from pathlib import Path

import datalad.utils as ut
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
    save_message_opt,
)
from datalad.interface.utils import (
    discover_dataset_trace_to_targets,
    get_tree_roots,
)
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CommandError
from datalad.support.parallel import (
    ProducerConsumerProgressLog,
    no_subds_in_futures,
)
from datalad.support.param import Parameter
from datalad.utils import ensure_list

from .status import Status

lgr = logging.getLogger('datalad.core.local.save')


@build_doc
class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records changes that have been made to it.
    This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions at
    a later point in time.

    .. note::
      Before Git v2.22, any Git repository without an initial commit located
      inside a Dataset is ignored, and content underneath it will be saved to
      the respective superdataset. DataLad datasets always have an initial
      commit, hence are not affected by this behavior.
    """
    # note above documents that out behavior is like that of `git add`, but
    # does not explicitly mention the connection to keep it simple.

    _examples_ = [
        dict(text="""Save any content underneath the current directory, without
             altering any potential subdataset""",
             code_py="save(path='.')",
             code_cmd="datalad save ."),
        dict(text="""Save specific content in the dataset""",
             code_py="save(path='myfile.txt')",
             code_cmd="datalad save myfile.txt"),
        dict(text="""Attach a commit message to save""",
             code_py="save(path='myfile.txt', message='add file')",
             code_cmd="datalad save -m 'add file' myfile.txt"),
        dict(text="""Save any content underneath the current directory, and
             recurse into any potential subdatasets""",
             code_py="save(path='.', recursive=True)",
             code_cmd="datalad save . -r"),
        dict(text="Save any modification of known dataset content in the "
                  "current directory, but leave untracked files (e.g. temporary files) "
                  "untouched",
             code_py="""save(path='.', updated=True)""",
             code_cmd="""datalad save -u ."""),
        dict(text="Tag the most recent saved state of a dataset",
             code_py="save(version_tag='bestyet')",
             code_cmd="datalad save --version-tag 'bestyet'"),
        dict(text="Save a specific change but integrate into last commit keeping "
                  "the already recorded commit message",
             code_py="save(path='myfile.txt', amend=True)",
             code_cmd="datalad save myfile.txt --amend")
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to save""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""path/name of the dataset component to save. If given, only
            changes made to those components are recorded in the new state.""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        message=save_message_opt,
        message_file=Parameter(
            args=("-F", "--message-file"),
            doc="""take the commit message from this file. This flag is
            mutually exclusive with -m.""",
            constraints=EnsureStr() | EnsureNone()),
        version_tag=Parameter(
            args=("-t", "--version-tag",),
            metavar='ID',
            doc="""an additional marker for that state. Every dataset that
            is touched will receive the tag.""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        updated=Parameter(
            args=('-u', '--updated',),
            action='store_true',
            doc="""if given, only saves previously tracked paths."""),
        to_git=Parameter(
            args=("--to-git",),
            action='store_true',
            doc="""flag whether to add data directly to Git, instead of
            tracking data identity only.  Use with caution, there is no
            guarantee that a file put directly into Git like this will
            not be annexed in a subsequent save operation.
            If not specified, it will be up to git-annex to decide how
            a file is tracked, based on a dataset's configuration
            to track particular paths,
            file types, or file sizes with either Git or git-annex.
            (see https://git-annex.branchable.com/tips/largefiles).
            """),
        jobs=jobs_opt,
        amend=Parameter(
            args=('--amend',),
            action='store_true',
            doc="""if set, changes are not recorded in a new, separate
            commit, but are integrated with the changeset of the previous
            commit, and both together are recorded by replacing that
            previous commit. This is mutually exclusive with recursive
            operation.
            """),
    )

    @staticmethod
    @datasetmethod(name='save')
    @eval_results
    def __call__(path=None,
                 *,
                 message=None, dataset=None,
                 version_tag=None,
                 recursive=False, recursion_limit=None,
                 updated=False,
                 message_file=None,
                 to_git=None,
                 jobs=None,
                 amend=False,
                 ):
        if message and message_file:
            raise ValueError(
                "Both a message and message file were specified for save()")

        if amend and recursive:
            raise ValueError("Cannot amend a commit recursively.")

        path = ensure_list(path)

        if message_file:
            with open(message_file) as mfh:
                message = mfh.read()

        # we want 'normal' to achieve the most compact argument list
        # for git calls
        # untracked_mode = 'no' if updated else 'normal'
        # TODO however, Repo.add() would refuse to add any dotfiles
        # in a directory that is itself untracked, hence the only
        # choice is to go with potentially crazy long lists
        # until https://github.com/datalad/datalad/issues/1454
        # has a resolution
        untracked_mode = 'no' if updated else 'all'

        # there are three basic scenarios:
        # 1. save modifications to any already tracked content
        # 2. save any content (including removal of deleted content)
        #    to bring things to a clean state
        # 3. like (2), but only operate on a given subset of content
        #    identified by paths
        # - all three have to work in conjunction with --recursive
        # - the difference between (1) and (2) should be no more
        #   that a switch from --untracked=no to --untracked=all
        #   in Repo.save()

        # we do not support
        # - simultaneous operations on multiple datasets from disjoint
        #   dataset hierarchies, hence a single reference dataset must be
        #   identifiable from the either
        #   - curdir or
        #   - the `dataset` argument.
        #   This avoids complex annotation loops and hierarchy tracking.
        # - any modification upwards from the root dataset

        ds = require_dataset(dataset, check_installed=True, purpose='save')

        # use status() to do all discovery and annotation of paths
        paths_by_ds = {}
        for s in Status()(
                # ATTN: it is vital to pass the `dataset` argument as it,
                # and not a dataset instance in order to maintain the path
                # semantics between here and the status() call
                dataset=dataset,
                path=path,
                untracked=untracked_mode,
                recursive=recursive,
                recursion_limit=recursion_limit,
                on_failure='ignore',
                # for save without recursion only commit matters
                eval_subdataset_state='full' if recursive else 'commit',
                return_type='generator',
                # this could be, but for now only 'error' results are handled
                # below
                #on_failure='ignore',
                result_renderer='disabled'):
            if s['status'] == 'error':
                # Downstream code can't do anything with these. Let the caller
                # decide their fate.
                yield s
                continue

            # fish out status dict for this parent dataset
            ds_status = paths_by_ds.get(s['parentds'], {})
            # reassemble path status info as repo.status() would have made it
            ds_status[ut.Path(s['path'])] = \
                {k: v for k, v in s.items()
                 if k not in (
                     'path', 'parentds', 'refds', 'status', 'action',
                     'logger')}
            paths_by_ds[s['parentds']] = ds_status

        lgr.debug('Determined %i datasets for saving from input arguments',
                  len(paths_by_ds))
        # figure out what datasets to process, start with the ones containing
        # the paths that were given as arguments
        discovered_datasets = list(paths_by_ds.keys())
        if dataset:
            # if a reference dataset was given we want to save all the way up
            # to it, so let's throw it into the mix
            discovered_datasets.append(ds.path)
        # sort the datasets into (potentially) disjoint hierarchies,
        # or a single one, if a reference dataset was given
        dataset_hierarchies = get_tree_roots(discovered_datasets)
        for rootds, children in dataset_hierarchies.items():
            edges = {}
            discover_dataset_trace_to_targets(
                rootds, children, [], edges, includeds=children)
            for superds, subdss in edges.items():
                superds_status = paths_by_ds.get(superds, {})
                for subds in subdss:
                    subds_path = ut.Path(subds)
                    sub_status = superds_status.get(subds_path, {})
                    if not (sub_status.get("state") == "clean" and
                            sub_status.get("type") == "dataset"):
                        # start from an entry that may already exist in the
                        # status record
                        superds_status[subds_path] = superds_status.get(
                            subds_path,
                            # if we got nothing yet:
                            # shot from the hip, some status config
                            # to trigger this specific super/sub
                            # relation to be saved
                            dict(state='untracked', type='dataset')
                        )
                paths_by_ds[superds] = superds_status

        def save_ds(args, version_tag=None):
            pdspath, paths = args

            pds = Dataset(pdspath)
            pds_repo = pds.repo
            # pop status for this dataset, we are not coming back to it
            pds_status = {
                # for handing over to the low-level code, we recode any
                # path relative to the real repo location, this avoid
                # cumbersome symlink handling without context in the
                # lower levels
                pds_repo.pathobj / p.relative_to(pdspath): props
                for p, props in paths.items()}
            start_commit = pds_repo.get_hexsha()
            if not all(p['state'] == 'clean' for p in pds_status.values()) or \
                    (amend and message):
                for res in pds_repo.save_(
                        message=message,
                        # make sure to have the `path` arg be None, as we want
                        # to prevent and bypass any additional repo.status()
                        # calls
                        paths=None,
                        # prevent whining of GitRepo
                        git=True if not hasattr(pds_repo, 'uuid')
                        else to_git,
                        # we are supplying the full status already, do not
                        # detect anything else
                        untracked='no',
                        _status=pds_status,
                        amend=amend):
                    # TODO remove stringification when datalad-core can handle
                    # path objects, or when PY3.6 is the lowest supported
                    # version
                    for k in ('path', 'refds'):
                        if k in res:
                            res[k] = str(
                                # recode path back to dataset path anchor
                                pds.pathobj / Path(res[k]).relative_to(
                                    pds_repo.pathobj)
                            )
                    yield res
            # report on the dataset itself
            dsres = dict(
                action='save',
                type='dataset',
                path=pds.path,
                refds=ds.path,
                status='ok'
                if start_commit != pds_repo.get_hexsha()
                else 'notneeded',
                logger=lgr,
            )
            if not version_tag:
                yield dsres
                return
            try:
                # method requires str
                version_tag = str(version_tag)
                pds_repo.tag(version_tag)
                dsres.update(
                    status='ok',
                    version_tag=version_tag)
                yield dsres
            except CommandError as e:
                if dsres['status'] == 'ok':
                    # first we yield the result for the actual save
                    # TODO: we will get duplicate dataset/save record obscuring
                    # progress reporting.  yoh thought to decouple "tag" from "save"
                    # messages but was worrying that original authors would disagree
                    yield dsres.copy()
                # and now complain that tagging didn't work
                dsres.update(
                    status='error',
                    message=('cannot tag this version: %s', e.stderr.strip()))
                yield dsres

        if not paths_by_ds:
            # Special case: empty repo. There's either an empty commit only or
            # none at all. An empty one we can amend otherwise there's nothing
            # to do.
            if amend and ds.repo.get_hexsha():
                yield from save_ds((ds.pathobj, dict()), version_tag=version_tag)

            else:
                yield dict(action='save',
                           type='dataset',
                           path=ds.path,
                           refds=ds.path,
                           status='notneeded',
                           logger=lgr)
            return

        # TODO: in principle logging could be improved to go not by a dataset
        # but by path(s) within subdatasets. That should provide a bit better ETA
        # and more "dynamic" feedback than jumpy datasets count.
        # See addurls where it is implemented that way by providing agg and another
        # log_filter
        yield from ProducerConsumerProgressLog(
            sorted(paths_by_ds.items(), key=lambda v: v[0], reverse=True),
            partial(save_ds, version_tag=version_tag),
            safe_to_consume=no_subds_in_futures,
            producer_future_key=lambda ds_items: ds_items[0],
            jobs=jobs,
            log_filter=_log_filter_save_dataset,
            unit="datasets",
            lgr=lgr,
        )


def _log_filter_save_dataset(res):
    return res.get('type') == 'dataset' and res.get('action') == 'save'
