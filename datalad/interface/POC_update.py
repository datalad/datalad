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
from datalad.support.constraints import EnsureStr, EnsureNone
from datalad.support.gitrepo import GitRepo
from datalad.support.exceptions import CommandError
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_list, is_annex

lgr = logging.getLogger('datalad.interface.POC_update')


class POCUpdate(Interface):
    """Update a handle."""

    _params_ = dict(
        handle=Parameter(
            args=('handle',),
            nargs='?',
            doc="name of or path to the handle to be updated",
            constraints=EnsureStr() | EnsureNone()),
        roothandle=Parameter(
            doc="Roothandle, where to install the handle to. Datalad has a "
                "default root handle.",
            constraints=EnsureStr() | EnsureNone()),
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

    def __call__(self, handle=curdir, roothandle=None, merge=False,
                 recursive=False, all=False, reobtain_data=False):
        """

        :param handle:
        :param roothandle:
        :param apply:
        :param recursive:
        :return:
        """

        if recursive:
            raise NotImplementedError("Option '--recursive' not implemented yet.")

        if reobtain_data:
            raise NotImplementedError("Option '--reobtain-data' not implemented yet.")

        master = POC_get_root_handle(roothandle)
        lgr.info("Update using root handle '%s' ..." % master.path)

        # figure out, what handle to update:
        if handle != curdir:
            if handle not in get_submodules_list(master):
                raise ValueError("Handle '%s' is not installed in "
                                 "root handle %s" % (handle, master.path))
            else:
                handle_repo = GitRepo(opj(master.path, handle), create=False)
        else:
            handle_repo = GitRepo(handle, create=False)

        # get all remotes:
        handle_remotes = handle_repo.git_get_remotes()

        # Currently '--apply' works for single remote only:
        if len(handle_remotes) > 1 and merge:
            lgr.debug("Found multiple remotes:\n%s" % handle_remotes)
            raise NotImplementedError("No merge strategy for multiple remotes "
                                      "implemented yet.")

        lgr.info("Updating handle '%s' ..." % handle_repo.path)

        # fetch remote(s):
        lgr.info("Fetching remote(s) ...")
        handle_repo.git_fetch('', "--all" if all else '')

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
                handle_repo.git_fetch(std_out.strip(), "git-annex")

        # merge:
        if merge:
            lgr.info("Applying changes from tracking branch...")
            handle_repo._git_custom_command('', ["git", "merge"])
            if is_annex(handle_repo.path):
                # annex-apply:
                lgr.info("Updating annex ...")
                handle_repo._git_custom_command('', ["git", "annex", "merge"])
