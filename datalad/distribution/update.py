# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for updating a dataset

"""

__docformat__ = 'restructuredtext'


import logging
from os.path import lexists, join as opj
import itertools

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit,
)
from datalad.distribution.dataset import require_dataset

from .dataset import (
    EnsureDataset,
    datasetmethod,
)

lgr = logging.getLogger('datalad.distribution.update')


@build_doc
class Update(Interface):
    """Update a dataset from a sibling.

    """
    # TODO: adjust docs to say:
    # - update from just one sibling at a time

    _examples_ = [
        dict(text="Update from a particular sibling",
             code_py="update(sibling='siblingname')",
             code_cmd="datalad update -s <siblingname>"),
        dict(text="Update from a particular sibling and merge the obtained changes",
             code_py="update(sibling='siblingname', merge=True)",
             code_cmd="datalad update --merge -s <siblingname>"),
    ]

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="""constrain to-be-updated subdatasets to the given path for recursive
            operation.""",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        sibling=Parameter(
            args=("-s", "--sibling",),
            doc="""name of the sibling to update from. If no sibling
            is given, updates from all siblings are obtained.""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        merge=Parameter(
            args=("--merge",),
            action="store_true",
            doc="""merge obtained changes from the given or the
            default sibling""", ),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        fetch_all=Parameter(
            args=("--fetch-all",),
            action="store_true",
            doc="""this option has no effect and will be removed in a future version.
            When no siblings are given, an all-sibling update will be performed.""", ),
        reobtain_data=Parameter(
            args=("--reobtain-data",),
            action="store_true",
            doc="""if enabled, file content that was present before an update
            will be re-obtained in case a file was changed by the update."""), )

    @staticmethod
    @datasetmethod(name='update')
    @eval_results
    def __call__(
            path=None,
            sibling=None,
            merge=False,
            dataset=None,
            recursive=False,
            recursion_limit=None,
            fetch_all=None,
            reobtain_data=False):
        """
        """
        if fetch_all is not None:
            lgr.warning('update(fetch_all=...) called. Option has no effect, and will be removed')
        if path and not recursive:
            lgr.warning('path constraints for subdataset updates ignored, '
                        'because `recursive` option was not given')

        refds = require_dataset(dataset, check_installed=True, purpose='updating')

        save_paths = []

        saw_subds = False
        for ds in itertools.chain([refds], refds.subdatasets(
                path=path,
                fulfilled=True,
                recursive=recursive,
                recursion_limit=recursion_limit,
                return_type='generator',
                result_renderer='disabled',
                result_xfm='datasets') if recursive else []):
            if ds != refds:
                saw_subds = True
            repo = ds.repo
            # prepare return value
            res = get_status_dict('update', ds=ds, logger=lgr, refds=refds.path)
            # get all remotes which have references (would exclude
            # special remotes)
            remotes = repo.get_remotes(
                **({'exclude_special_remotes': True} if isinstance(repo, AnnexRepo) else {}))
            if not remotes and not sibling:
                res['message'] = ("No siblings known to dataset at %s\nSkipping",
                                  repo.path)
                res['status'] = 'notneeded'
                yield res
                continue
            if not sibling and len(remotes) == 1:
                # there is only one remote, must be this one
                sibling_ = remotes[0]
            elif not sibling:
                # nothing given, look for tracking branch
                sibling_ = repo.get_tracking_branch(remote_only=True)[0]
            else:
                sibling_ = sibling
            if sibling_ and sibling_ not in remotes:
                res['message'] = ("'%s' not known to dataset %s\nSkipping",
                                  sibling_, repo.path)
                res['status'] = 'impossible'
                yield res
                continue
            if not sibling_ and len(remotes) > 1 and merge:
                lgr.debug("Found multiple siblings:\n%s" % remotes)
                res['status'] = 'impossible'
                res['message'] = "Multiple siblings, please specify from which to update."
                yield res
                continue
            lgr.info("Fetching updates for %s", ds)
            # fetch remote
            fetch_kwargs = dict(
                # test against user-provided value!
                remote=None if sibling is None else sibling_,
                all_=sibling is None,
                # required to not trip over submodules that
                # were removed in the origin clone
                recurse_submodules="no",
                prune=True)  # prune to not accumulate a mess over time
            repo.fetch(**fetch_kwargs)
            # NOTE if any further acces to `repo` is needed, reevaluate
            # ds.repo again, as it might have be converted from an GitRepo
            # to an AnnexRepo
            if merge:
                for fr in _update_repo(ds, sibling_, reobtain_data):
                    yield fr
            res['status'] = 'ok'
            yield res
            save_paths.append(ds.path)
        # we need to save updated states only if merge was requested -- otherwise
        # it was a pure fetch
        if merge and recursive:
            if path and not saw_subds:
                lgr.warning(
                    'path constraints did not match an installed subdataset: %s',
                    path)
            save_paths = [p for p in save_paths if p != refds.path]
            if not save_paths:
                return
            lgr.debug(
                'Subdatasets where updated state may need to be '
                'saved in the parent dataset: %s', save_paths)
            for r in refds.save(
                    path=save_paths,
                    recursive=False,
                    message='[DATALAD] Save updated subdatasets'):
                yield r


def _update_repo(ds, remote, reobtain_data):
    repo = ds.repo

    lgr.info("Applying updates to %s", ds)
    if isinstance(repo, AnnexRepo):
        if reobtain_data:
            # get all annexed files that have data present
            lgr.info('Recording file content availability '
                     'to re-obtain updated files later on')
            present_files = [
                opj(ds.path, p)
                for p in repo.get_annexed_files(with_content_only=True)]
        # this runs 'annex sync' and should deal with anything
        repo.sync(remotes=remote, push=False, pull=True, commit=False)
        if reobtain_data:
            present_files = [p for p in present_files if lexists(p)]
            if present_files:
                lgr.info('Ensuring content availability for %i '
                         'previously available files',
                         len(present_files))
                yield from ds.get(present_files, recursive=False,
                                  return_type='generator')
    else:
        # handle merge in plain git
        active_branch = repo.get_active_branch()
        if active_branch is None:
            # I guess we need to fetch, and then let super-dataset to update
            # into the state it points to for this submodule, but for now let's
            # just blow I guess :-/
            lgr.warning(
                "No active branch in %s - we just fetched and not changing state",
                repo
            )
        else:
            if repo.config.get('branch.{}.remote'.format(active_branch)) == remote:
                # the branch love this remote already, let git pull do its thing
                repo.pull(remote=remote)
            else:
                # no marriage yet, be specific
                repo.pull(remote=remote, refspec=active_branch)
