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

from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.utils import knows_annex
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.update')


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
        if reobtain_data:
            # TODO: properly define, what to do
            raise NotImplementedError("TODO: Option '--reobtain-data' not "
                                      "implemented yet.")

        if dataset and not path:
            # act on the whole dataset if nothing else was specified
            path = dataset.path if isinstance(dataset, Dataset) else dataset
        content_by_ds, unavailable_paths = Interface._prep(
            path=path,
            dataset=dataset,
            recursive=recursive,
            recursion_limit=recursion_limit)

        # TODO: check parsed inputs if any paths within a dataset were given
        # and issue a message that we will update the associate dataset as a whole
        # or fail -- see #1185 for a potential discussion
        results = []

        for ds_path in content_by_ds:
            ds = Dataset(ds_path)
            repo = ds.repo
            # get all remotes which have references (would exclude
            # special remotes)
            remotes = repo.get_remotes(
                **({'exclude_special_remotes': True} if isinstance(repo, AnnexRepo) else {}))
            if not remotes:
                lgr.debug("No siblings known to dataset at %s\nSkipping",
                          repo.path)
                continue
            if not sibling:
                # nothing given, look for tracking branch
                sibling_ = repo.get_tracking_branch()[0]
            else:
                sibling_ = sibling
            if sibling_ and sibling_ not in remotes:
                lgr.warning("'%s' not known to dataset %s\nSkipping",
                            sibling_, repo.path)
                continue
            if not sibling_ and len(remotes) == 1:
                # there is only one remote, must be this one
                sibling_ = remotes[0]
            if not sibling_ and len(remotes) > 1 and merge:
                lgr.debug("Found multiple siblings:\n%s" % remotes)
                raise NotImplementedError(
                    "Multiple siblings, please specify from which to update.")
            lgr.info("Updating dataset '%s' ..." % repo.path)
            _update_repo(repo, sibling_, merge, fetch_all)


def _update_repo(repo, remote, merge, fetch_all):
    # fetch remote
    repo.fetch(
        remote=None if fetch_all else remote,
        all_=fetch_all,
        prune=True)  # prune to not accumulate a mess over time

    # merge:
    if merge:
        # we need to check whether we need to convert this dataset to
        # annex, would would be the case when we presently have a git repo
        # and the recent fetch brought evidence for a remote annex
        if isinstance(repo, GitRepo) and knows_annex(repo.path):
            lgr.info("Init annex at '%s' prior merge.", repo.path)
            repo = AnnexRepo(repo.path, create=False)
        lgr.info("Merging updates...")
        if isinstance(repo, AnnexRepo):
            # this runs 'annex sync' and should deal with anything
            repo.sync(remotes=remote, push=False, pull=True, commit=False)
        else:
            # handle merge in plain git
            active_branch = repo.get_active_branch()
            if repo.cfg.get('branch.{}.remote'.format(remote), None) == remote:
                # the branch love this remote already, let git pull do its thing
                repo.pull(remote=remote)
            else:
                # no marriage yet, be specific
                repo.pull(remote=remote, refspec=active_branch)
