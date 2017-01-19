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
from os.path import join as opj

from datalad.interface.base import Interface
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.gitrepo import GitRepo
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
        name=Parameter(
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
            doc="""merge obtained changes from either the sibling `name` or the
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
            name=None,
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
            remotes = repo.get_remotes(with_refs_only=True)
            if not remotes:
                lgr.debug("No siblings known to dataset at %s\nSkipping",
                          repo.path)
                continue
            if name and name not in remotes:
                lgr.warning("'%s' not known to dataset %s\nSkipping",
                            name, repo.path)
                continue

            # Currently '--merge' works for single remote only:
            # TODO: - condition still incomplete
            #       - We can merge if a remote was given or there is a
            #         tracking branch
            #       - we also can fetch all remotes independently on whether or
            #         not we merge a certain remote
            if not name and len(remotes) > 1 and merge:
                lgr.debug("Found multiple remotes:\n%s" % remotes)
                raise NotImplementedError("No merge strategy for multiple "
                                          "remotes implemented yet.")
            lgr.info("Updating dataset '%s' ..." % repo.path)
            _update_repo(repo, name, merge, fetch_all)


def _update_repo(repo, remote, merge, fetch_all):
            # fetch remote(s):
            repo.fetch(remote=remote, all_=fetch_all)

            # if `repo` is an annex and we didn't fetch the entire remote
            # anyway, explicitly fetch git-annex branch:

            # TODO: This isn't correct. `fetch_all` fetches all remotes.
            # Apparently, we currently fetch an entire remote anyway. Is this
            # what we want? Do we want to specify a refspec instead?
            # yoh: we should leave it to git and its configuration.
            # So imho we should just extract to fetch everything git would fetch
            if knows_annex(repo.path) and not fetch_all:
                if remote:
                    # we are updating from a certain remote, so git-annex branch
                    # should be updated from there as well:
                    repo.fetch(remote=remote)
                    # TODO: what does failing here look like?
                else:
                    # we have no remote given, therefore
                    # check for tracking branch's remote:

                    track_remote, track_branch = repo.get_tracking_branch()
                    if track_remote:
                        # we have a "tracking remote"
                        repo.fetch(remote=track_remote)

            # merge:
            if merge:
                lgr.info("Applying changes from tracking branch...")
                # TODO: Adapt.
                # TODO: Rethink default remote/tracking branch. See above.
                # We need a "tracking remote" but custom refspec to fetch from
                # that remote
                cmd_list = ["git", "pull"]
                if remote:
                    cmd_list.append(remote)
                    # branch needed, if not default remote
                    # => TODO: use default remote/tracking branch to compare
                    #          (see above, where git-annex is fetched)
                    # => TODO: allow for passing a branch
                    # (or more general refspec?)
                    # For now, just use the same name
                    cmd_list.append(repo.get_active_branch())

                std_out, std_err = repo._git_custom_command('', cmd_list)
                lgr.info(std_out)
                if knows_annex(repo.path):
                    # annex-apply:
                    lgr.info("Updating annex ...")
                    std_out, std_err = repo._git_custom_command(
                        '', ["git", "annex", "merge"])
                    lgr.info(std_out)

                    # TODO: return value?
