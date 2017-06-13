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

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.interface.annotate_paths import AnnotatePaths
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.distribution.dataset import require_dataset

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.update')


@build_doc
class Update(Interface):
    """Update a dataset from a sibling.

    """
    # TODO: adjust docs to say:
    # - update from just one sibling at a time

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar="PATH",
            doc="path to be updated",
            nargs="*",
            constraints=EnsureStr() | EnsureNone()),
        sibling=Parameter(
            args=("-s", "--sibling",),
            doc="""name of the sibling to update from""",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
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
            doc="fetch updates from all known siblings", ),
        reobtain_data=Parameter(
            args=("--reobtain-data",),
            action="store_true",
            doc="TODO"), )

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
            fetch_all=False,
            reobtain_data=False):
        """
        """

        if not dataset and not path:
            # try to find a dataset in PWD
            dataset = require_dataset(
                None, check_installed=True, purpose='updating')
        refds_path = Interface.get_refds_path(dataset)
        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = refds_path

        for ap in AnnotatePaths.__call__(
                dataset=refds_path,
                path=path,
                recursive=recursive,
                recursion_limit=recursion_limit,
                action='update',
                unavailable_path_status='impossible',
                nondataset_path_status='error',
                return_type='generator',
                on_failure='ignore'):
            if ap.get('status', None):
                # this is done
                yield ap
                continue
            if not ap.get('type', None) == 'dataset':
                ap.update(
                    status='impossible',
                    message="can only update datasets")
                yield ap
                continue
            # this is definitely as dataset from here on
            ds = Dataset(ap['path'])
            repo = ds.repo
            # prepare return value
            # TODO reuse AP for return props
            res = get_status_dict('update', ds=ds, logger=lgr, refds=refds_path)
            # get all remotes which have references (would exclude
            # special remotes)
            remotes = repo.get_remotes(
                **({'exclude_special_remotes': True} if isinstance(repo, AnnexRepo) else {}))
            if not remotes:
                res['message'] = ("No siblings known to dataset at %s\nSkipping",
                                  repo.path)
                res['status'] = 'notneeded'
                yield res
                continue
            if not sibling:
                # nothing given, look for tracking branch
                sibling_ = repo.get_tracking_branch()[0]
            else:
                sibling_ = sibling
            if sibling_ and sibling_ not in remotes:
                res['message'] = ("'%s' not known to dataset %s\nSkipping",
                                  sibling_, repo.path)
                res['status'] = 'impossible'
                yield res
                continue
            if not sibling_ and len(remotes) == 1:
                # there is only one remote, must be this one
                sibling_ = remotes[0]
            if not sibling_ and len(remotes) > 1 and merge:
                lgr.debug("Found multiple siblings:\n%s" % remotes)
                res['status'] = 'impossible'
                res['error'] = NotImplementedError(
                    "Multiple siblings, please specify from which to update.")
                yield res
                continue
            lgr.info("Updating dataset '%s' ..." % repo.path)
            # fetch remote
            repo.fetch(
                remote=None if fetch_all else sibling_,
                all_=fetch_all,
                prune=True)  # prune to not accumulate a mess over time
            # NOTE if any further acces to `repo` is needed, reevaluate
            # ds.repo again, as it might have be converted from an GitRepo
            # to an AnnexRepo
            if merge:
                for fr in _update_repo(ds, sibling_, reobtain_data):
                    yield fr
            res['status'] = 'ok'
            yield res


def _update_repo(ds, remote, reobtain_data):
    repo = ds.repo

    lgr.info("Merging updates...")
    if isinstance(repo, AnnexRepo):
        if reobtain_data:
            # get all annexed files that have data present
            lgr.info('Recording file content availability to re-obtain update files later on')
            reobtain_data = \
                [opj(ds.path, p)
                 for p in repo.get_annexed_files(with_content_only=True)]
        # this runs 'annex sync' and should deal with anything
        repo.sync(remotes=remote, push=False, pull=True, commit=False)
        if reobtain_data:
            reobtain_data = [p for p in reobtain_data if lexists(p)]
        if reobtain_data:
            lgr.info('Ensure content availability for %i previously available files', len(reobtain_data))
            for res in ds.get(
                    reobtain_data, recursive=False, return_type='generator'):
                yield res
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
            if repo.config.get('branch.{}.remote'.format(remote), None) == remote:
                # the branch love this remote already, let git pull do its thing
                repo.pull(remote=remote)
            else:
                # no marriage yet, be specific
                repo.pull(remote=remote, refspec=active_branch)
