# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for handle publishing

"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureChoice
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex
from datalad.cmd import CommandError

lgr = logging.getLogger('datalad.interface.POC_publish')


class POCPublish(Interface):
    """publish a handle.

    This is basic implementation for testing purposes
    """

    _params_ = dict(
        remote=Parameter(
            args=('dst',),
            doc="Remote name to publish the handle to. If there is no such "
                "remote yet, it will be registered(?) using the URL given by "
                "REMOTE-URL."
                "If not even the remote repository exists and you want publish "
                "to create it, use CREATE."
                "If RECURSIVE is set, the remote names for subhandles will be "
                "derived by concatenating this remote name, a connecting "
                "dash and the subhandle's name.",
            constraints=EnsureStr()),
        remote_url=Parameter(
            args=('--remote-url',),
            doc="The URL of the repository named by REMOTE.",
            # TODO: What if remote is known, but remote-url is passed?
            #       Redirect the existing remote or ignore or reject?
            # TODO: RECURSIVE? => REMOTE-URL/what? depends on tree or list?
            #       list: hierarchical-subhandle-name (replace / by -)?
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        # TODO: remote_url_push/remote_url_pull
        handle=Parameter(
            args=('--handle',),
            doc="Name of or path to the handle to publish. Defaults to CWD.",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            doc="""If set, this also publishes all subhandles of HANDLE. Set to
                'list' to publish subhandles at the same directory level as
                the handle itself (hint: github) or set to 'tree' to
                hierarchically publish them.
                Note: Since it is not clear in detail yet, what 'tree' means,
                only 'list' is currently implemented. """,
                # TODO: Does 'tree' derive from relative URLs of submodules or
                # from the hierarchy of submodules?
            constraints=EnsureChoice(["list"]) | EnsureNone()),
        rewrite_subhandle_urls=Parameter(
            args=("--rewrite-subhandle-urls", ),
            doc="When publishing RECURSIVE, rewrite the URLs of superhandles "
                "linking their subhandles to the URL they were published to.",
            constraints=EnsureChoice({"ask", "never", "all"}),),
        create_ssh=Parameter(
            args=("--create-ssh",),
            doc="Pass a SSH URL, if you want publish to create the public "
                "repositories via SSH.",
            constraints=EnsureStr() | EnsureNone()),)

    def __call__(self, remote, remote_url=None, handle=curdir, recursive=None,
                 rewrite_subhandle_urls="never", create_ssh=None):



        ########

            # option -create(method) + ssh-url
            # remote-name as a target
            # not existent => url
            # remote names uniform within a tree

        #######

        # Maybe enhance what dst is expected to be:
        # detect whether dst is a valid git repo => push?
        # => does this imply to not rewrite any URL?
        # => is there a branch to push to?

        # else:
        # detect ssh address
        # => create repo(s) to push to

        # rewrite submodule URLs?
        # => do it locally and push or do it directly on the server?



        return