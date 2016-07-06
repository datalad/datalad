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
from datalad.interface.common_opts import annex_copy_opts, recursion_flag, \
    recursion_limit, git_opts, annex_opts
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureNone
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import knows_annex
from datalad.utils import getpwd

from .dataset import Dataset
from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.update')


class Update(Interface):
    """Update a dataset from a known :term:`sibling`.

    This command obtains saved states of either one or all known dataset
    sibling(s) and makes them available locally. Optionally, subdatasets
    can be updated recursively.

    By default, the current state of the local dataset is not altered, but
    an automatic merge of obtained updates can be requested. In this case,
    it is also possible, to obtain data content updates for all files with
    available content prior to the update.

    .. note::
      Power-user info: This command uses :command:`git fetch`, :command:`git merge`, and
      :command:`git annex copy` to update a dataset. Update source locations
      are either configured remote Git repositories, or git-annex special
      remotes.
    """

    _params_ = dict(
        sibling=Parameter(
            args=("sibling",),
            metavar="SIBLING NAME",
            doc="""name of a known sibling to update from. If none is provided,
            an attempt is made to identify one based on the dataset's
            configuration (i.e. a set up tracking branch)""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to update.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        merge=Parameter(
            args=("--merge",),
            action="store_true",
            doc="merge changes from sibling `name` or the remote branch, "
                "configured to be the tracking branch if no sibling was "
                "given", ),
        fetch_all=Parameter(
            args=("--fetch-all",),
            action="store_true",
            doc="fetch updates from all siblings", ),
        reobtain_data=Parameter(
            args=("--reobtain-data",),
            action="store_true",
            doc="TODO"),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        git_opts=git_opts,
        annex_opts=annex_opts,
        annex_copy_opts=annex_copy_opts)

    @staticmethod
    @datasetmethod(name='update')
    def __call__(
            sibling=None,
            dataset=None,
            merge=False,
            recursive=False,
            fetch_all=False,
            reobtain_data=False,
            recursion_limit=None,
            git_opts=None,
            annex_opts=None,
            annex_copy_opts=None):
        """
        """
        # TODO: Is there an 'update filehandle' similar to install and publish?
        # What does it mean?

        if reobtain_data:
            # TODO: properly define, what to do
            raise NotImplementedError("TODO: Option '--reobtain-data' not "
                                      "implemented yet.")

        # shortcut
        ds = dataset

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)

        # if we have no dataset given, figure out which one we need to operate
        # on, based on the current working directory of the process:
        if ds is None:
            # try to find a dataset at or above PWD:
            dspath = GitRepo.get_toppath(getpwd())
            if dspath is None:
                raise ValueError("No dataset found at %s." % getpwd())
            ds = Dataset(dspath)
        assert (ds is not None)

        if not ds.is_installed():
            raise ValueError("No installed dataset found at "
                             "{0}.".format(ds.path))
        assert (ds.repo is not None)

        repos_to_update = [ds.repo]
        if recursive:
            repos_to_update += [GitRepo(opj(ds.path, sub_path))
                                for sub_path in
                                ds.get_subdatasets(recursive=True)]

        for repo in repos_to_update:
            # get all remotes:
            remotes = repo.get_remotes()
            if name and name not in remotes:
                lgr.warning("'%s' not known to dataset %s.\nSkipping" %
                            (name, repo.path))
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

            # fetch remote(s):
            repo.fetch(remote=name, all_=fetch_all)

            # if `repo` is an annex and we didn't fetch the entire remote
            # anyway, explicitly fetch git-annex branch:

            # TODO: This isn't correct. `fetch_all` fetches all remotes.
            # Apparently, we currently fetch an entire remote anyway. Is this
            # what we want? Do we want to specify a refspec instead?

            if knows_annex(repo.path) and not fetch_all:
                if name:
                    # we are updating from a certain remote, so git-annex branch
                    # should be updated from there as well:
                    repo.fetch(remote=name, refspec="git-annex")
                    # TODO: what does failing here look like?
                else:
                    # we have no remote given, therefore
                    # check for tracking branch's remote:

                    track_remote, track_branch = repo.get_tracking_branch()
                    if track_remote:
                        # we have a "tracking remote"
                        repo.fetch(remote=track_remote, refspec="git-annex")

            # merge:
            if merge:
                lgr.info("Applying changes from tracking branch...")
                # TODO: Adapt.
                # TODO: Rethink default remote/tracking branch. See above.
                # We need a "tracking remote" but custom refspec to fetch from
                # that remote
                cmd_list = ["git", "pull"]
                if name:
                    cmd_list.append(name)
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
