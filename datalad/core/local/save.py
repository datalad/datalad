# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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
from six import iteritems
from six import text_type

from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    recursion_limit,
    recursion_flag,
    save_message_opt,
)
from datalad.interface.utils import (
    eval_results,
    get_tree_roots,
    discover_dataset_trace_to_targets,
)
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.support.exceptions import CommandError
from datalad.utils import (
    assure_list,
)
import datalad.utils as ut

from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from .status import (
    Status,
)

lgr = logging.getLogger('datalad.core.local.save')


@build_doc
class Save(Interface):
    """Save the current state of a dataset

    Saving the state of a dataset records changes that have been made to it.
    This change record is annotated with a user-provided description.
    Optionally, an additional tag, such as a version, can be assigned to the
    saved state. Such tag enables straightforward retrieval of past versions at
    a later point in time.

    Examples:

      Save any content underneath the current directory, without altering
      any potential subdataset (use --recursive for that)::

        % datalad save .

      Save any modification of known dataset content, but leave untracked
      files (e.g. temporary files) untouched::

        % dataset save -u -d <path_to_dataset>

      Tag the most recent saved state of a dataset::

        % dataset save -d <path_to_dataset> --version-tag bestyet

    .. note::
      For performance reasons, any Git repository without an initial commit
      located inside a Dataset is ignored, and content underneath it will be
      saved to the respective superdataset. DataLad datasets always have an
      initial commit, hence are not affected by this behavior.
    """
    # note above documents that out behavior is like that of `git add`, but
    # does not explicitly mention the connection to keep it simple.

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
            tracking data identity only.  Usually this is not desired,
            as it inflates dataset sizes and impacts flexibility of data
            transport. If not specified - it will be up to git-annex to
            decide, possibly on .gitattributes options. Use this flag
            with a simultaneous selection of paths to save. In general,
            it is better to pre-configure a dataset to track particular paths,
            file types, or file sizes with either Git or git-annex.
            See https://git-annex.branchable.com/tips/largefiles/"""),
    )

    @staticmethod
    @datasetmethod(name='save')
    @eval_results
    def __call__(path=None, message=None, dataset=None,
                 version_tag=None,
                 recursive=False, recursion_limit=None,
                 updated=False,
                 message_file=None,
                 to_git=None,
                 ):
        if message and message_file:
            raise ValueError(
                "Both a message and message file were specified for save()")

        path = assure_list(path)

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

        ds = require_dataset(dataset, check_installed=True, purpose='saving')

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
                result_renderer='disabled'):
            # fish out status dict for this parent dataset
            ds_status = paths_by_ds.get(s['parentds'], {})
            # reassemble path status info as repo.status() would have made it
            ds_status[ut.Path(s['path'])] = \
                {k: v for k, v in iteritems(s)
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
        for rootds, children in iteritems(dataset_hierarchies):
            edges = {}
            discover_dataset_trace_to_targets(
                rootds, children, [], edges, includeds=children)
            for superds, subdss in iteritems(edges):
                superds_status = paths_by_ds.get(superds, {})
                for subds in subdss:
                    # TODO actually start from an entry that may already
                    # exist in the status record
                    superds_status[ut.Path(subds)] = dict(
                        # shot from the hip, some status config
                        # to trigger this specific super/sub
                        # relation to be saved
                        state='untracked',
                        type='dataset')
                paths_by_ds[superds] = superds_status

        # TODO parallelize, whenever we have multiple subdataset of a single
        # dataset they can all be processed simultaneously
        # sort list of dataset to handle, starting with the ones deep down
        for pdspath in sorted(paths_by_ds, reverse=True):
            pds = Dataset(pdspath)
            # pop status for this dataset, we are not coming back to it
            pds_status = {
                # for handing over to the low-level code, we recode any
                # path relative to the real repo location, this avoid
                # cumbersome symlink handling without context in the
                # lower levels
                pds.repo.pathobj / p.relative_to(pdspath): props
                for p, props in iteritems(paths_by_ds.pop(pdspath))}
            start_commit = pds.repo.get_hexsha()
            if not all(p['state'] == 'clean' for p in pds_status.values()):
                for res in pds.repo.save_(
                        message=message,
                        # make sure to have the `path` arg be None, as we want
                        # to prevent and bypass any additional repo.status()
                        # calls
                        paths=None,
                        # prevent whining of GitRepo
                        git=True if not hasattr(ds.repo, 'annexstatus')
                        else to_git,
                        # we are supplying the full status already, do not
                        # detect anything else
                        untracked='no',
                        _status=pds_status):
                    # TODO remove stringification when datalad-core can handle
                    # path objects, or when PY3.6 is the lowest supported
                    # version
                    for k in ('path', 'refds'):
                        if k in res:
                            res[k] = text_type(
                                # recode path back to dataset path anchor
                                pds.pathobj / res[k].relative_to(
                                    pds.repo.pathobj)
                            )
                    yield res
            # report on the dataset itself
            dsres = dict(
                action='save',
                type='dataset',
                path=pds.path,
                refds=ds.path,
                status='ok'
                if start_commit != pds.repo.get_hexsha()
                else 'notneeded',
                logger=lgr,
            )
            if not version_tag:
                yield dsres
                continue
            try:
                pds.repo.tag(version_tag)
                dsres.update(
                    status='ok',
                    version_tag=version_tag)
                yield dsres
            except CommandError as e:
                if dsres['status'] == 'ok':
                    # first we yield the result for the actual save
                    yield dsres.copy()
                # and now complain that tagging didn't work
                dsres.update(
                    status='error',
                    message=('cannot tag this version: %s', e.stderr.strip()))
                yield dsres
