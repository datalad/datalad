# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for updating a handle

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, \
    EnsureHandleAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import CommandError
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_list, is_annex, get_remotes

lgr = logging.getLogger('datalad.interface.POC_update')


class POCUpdate(Interface):
    """Update a handle."""

    _params_ = dict(
        remote=Parameter(
            args=("remote",),
            doc="",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        handle=Parameter(
            args=('--handle',),
            doc="name of or path to the handle to be updated",
            constraints=EnsureHandleAbsolutePath()),
        merge=Parameter(
            args=("--merge",),
            action="store_true",
            doc="Merge changes from remote branch, configured to be the "
                "tracking branch.",),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""If set this updates all possibly existing subhandles,
             too."""),
        all=Parameter(
            args=("--all",),
            action="store_true",
            doc="Fetch updates from all remotes.",),
        reobtain_data=Parameter(
            args=("--reobtain-data",),
            action="store_true",
            doc="TODO"),)

    # TODO: For cmdline handle=curdir works. But How about Python API?
    # Should this be abspath(getpwd()) or is there a way to invoke the
    # constraints when using python API?
    def __call__(self, remote=None, handle=curdir,
                 merge=False, recursive=False, all=False, reobtain_data=False):
        """
        """

        if reobtain_data:
            raise NotImplementedError("Option '--reobtain-data' not implemented yet.")

        # TODO: Exception handling:
        top_handle_repo = GitRepo(handle, create=False)

        handles_to_update = [top_handle_repo]
        if recursive:
            handles_to_update += [GitRepo(opj(top_handle_repo.path, sub_path))
                                  for sub_path in
                                  get_submodules_list(top_handle_repo)]

        for handle_repo in handles_to_update:
            # get all remotes:
            handle_remotes = get_remotes(handle_repo)

            # Currently '--apply' works for single remote only:
            if len(handle_remotes) > 1 and merge:
                lgr.debug("Found multiple remotes:\n%s" % handle_remotes)
                raise NotImplementedError("No merge strategy for multiple remotes "
                                          "implemented yet.")

            lgr.info("Updating handle '%s' ..." % handle_repo.path)

            # fetch remote(s):
            lgr.info("Fetching remote(s) ...")
            handle_repo.git_fetch(remote if remote else '', "--all" if all else '')

            # if it is an annex and there is a tracking branch, and we didn't fetch
            # the entire remote anyway, fetch explicitly git-annex branch:
            if is_annex(handle_repo.path) and not all:
                # check for tracking branch's remote:
                try:
                    std_out, std_err = \
                        handle_repo._git_custom_command('',
                                                        ["git", "config", "--get", "branch.{active_branch}.remote".format(active_branch=handle_repo.git_get_active_branch())])
                except CommandError as e:
                    if e.code == 1 and e.stdout == "":
                        std_out = None
                    else:
                        raise

                if std_out:  # we have a "tracking remote"
                    handle_repo.git_fetch("%s git-annex" % std_out.strip())

            # merge:
            if merge:
                lgr.info("Applying changes from tracking branch...")
                cmd_list = ["git", "pull"]
                if remote:
                    cmd_list.append(remote)
                handle_repo._git_custom_command('', cmd_list)
                if is_annex(handle_repo.path):
                    # annex-apply:
                    lgr.info("Updating annex ...")
                    handle_repo._git_custom_command('', ["git", "annex", "merge"])
