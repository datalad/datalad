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
        apply=Parameter(
            args=("--apply", "-a"),
            action="store_true",
            doc="Merge changes from remote.",),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""If set this updates all possibly existing subhandles,
             too."""),)

    def __call__(self, handle=curdir, roothandle=None, apply=False, recursive=False):
        """

        :param handle:
        :param roothandle:
        :param apply:
        :param recursive:
        :return:
        """

        if recursive:
            raise NotImplementedError("Option '--recursive' not implemented yet.")

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
        if len(handle_remotes) > 1 and apply:
            lgr.debug("Found multiple remotes:\n%s" % handle_remotes)
            raise NotImplementedError("No merge strategy for multiple remotes "
                                      "implemented yet.")

        lgr.info("Updating handle '%s' ..." % handle_repo.path)

        # fetch all remote:
        lgr.info("Fetching remotes ...")
        handle_repo.git_fetch('', "--all")

        # apply:
        if apply:
            lgr.info("Applying changes from tracking branch...")
            handle_repo._git_custom_command('', ["git", "merge"])
            if is_annex(handle_repo.path):
                # annex-apply:
                lgr.info("Updating annex ...")
                handle_repo._git_custom_command('', ["git", "annex", "merge"])
