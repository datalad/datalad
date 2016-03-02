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
            args=('remote',),
            doc="Remote name to publish the handle to. If there is no such "
                "remote yet, it will be registered(?) using the URL given by "
                "REMOTE_URL.\n"
                "If not even the remote repository exists and you want datalad "
                "to create it, use CREATE.\n"
                "If RECURSIVE is set, the same name will be used to address "
                "the subhandles' remotes.",
            constraints=EnsureStr()),
        remote_url=Parameter(
            args=('--remote-url',),
            doc="The URL of the repository named by REMOTE. This URL has to be "
                "accessible to anyone, who is supposed to have acces to the "
                "published handle later on. (Technically: a git pull URL)\n"
                "If you want to publish RECURSIVE, it is expected, that you "
                "pass a template for building the URLs of all handles to be "
                "published by using placeholders.\n"
                "List of currently available placeholders:\n"
                "$NAME-DASH\tthe name of the handle, where slashes are replaced by dashes.",
            # TODO: What if remote is known, but remote-url is passed?
            #       Redirect the existing remote or ignore or reject?
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        remote_url_push=Parameter(
            args=('--remote-url-push',),
            doc="In case the REMOTE_URL cannot be used to push to the remote "
                "repository, use this parameter to additionally provide a "
                "push URL.\n",
            constraints=EnsureStr() | EnsureNone()),
        # TODO: remote_url_push/remote_url_pull
        # pull ist public URL, die wir eh bekommen vom User!
        # push geht immer auch als pull

        # URL: TEMPLATE
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

                # no hierarchy choices, but URL Template!

            constraints=EnsureChoice(["list"]) | EnsureNone()),
        rewrite_subhandle_urls=Parameter(
            args=("--rewrite-subhandle-urls", ),
            doc="When publishing RECURSIVE, rewrite the URLs of superhandles "
                "linking their subhandles to the URL they were published to.",
            constraints=EnsureChoice({"ask", "never", "all"}),
            # TODO: eventually 'ask' probably should lead to a more chatty
            #       thing, than just yes/no per handle. Allow for editing the
            #       URL to be written.
            ),
        create_ssh=Parameter(
            args=("--create-ssh",),
            doc="Pass a SSH URL, if you want datalad to create the public "
                "repositories via SSH.",
            constraints=EnsureStr() | EnsureNone()),
        roothandle=Parameter(
            doc="Roothandle, HANDLE is referring to. Datalad has a "
                "default root handle.",
            constraints=EnsureStr() | EnsureNone()),)

    def __call__(self, remote, remote_url=None, remote_url_push=None, handle=curdir, recursive=None,
                 rewrite_subhandle_urls="never", create_ssh=None,
                 roothandle=None):
        # Note: "Real" implementation should use getpwd()

        # Note: When pushing, check for annex!

        # TODO: check parameter dependencies:

        # get root handle:
        master = POC_get_root_handle(roothandle)
        lgr.info("Using root handle '%s' ..." % master.path)

        # figure out, what handle to publish:
        if exists(handle):  # local path?
            handle_repo = GitRepo(handle, create=False)
        elif handle in get_submodules_list(master):  # valid handle name?
            handle_repo = GitRepo(opj(master.path, handle), create=False)
        else:
            raise ValueError("Unknown handle '%s'." % handle)

        # ########## RECURSIVE ###################
        # TODO: build a list of handles to publish and there (modified)
        #       parameters (deepest first)
        # May be even make __call__ actually recursive?

        # Q: Rewriting locally, commit and push?
        # => How to commit ignoring the current branch? => don't ignore ;)

        if remote not in handle_repo.git_get_remotes():
            if not remote_url:
                raise ValueError("No remote '%s' found. Provide REMOTE-URL to add it.")
            lgr.info("Remote '%s' doesn't exist yet.")
            if create_ssh:
                lgr.info("Trying to create a remote repository via %s" % create_ssh)
                # TODO:
                pass
            handle_repo.git_remote_add(remote, remote_url)
            if remote_url_push:
                # TODO: add push url
                pass
            lgr.info("Added remote '%s':\n %s (pull)\n%s (push)." % (remote, remote_url, remote_url_push if remote_url_push else remote_url))
        else:
            # known remote: parameters remote-url-* currently invalid.
            # This may change to adapt the existing remote.
            if remote_url:
                lgr.warning("Remote '%s' already exists. Ignoring remote-url %s." % remote_url)
            if remote_url_push:
                lgr.warning("Remote '%s' already exists. Ignoring remote-url-push %s." % remote_url_push)

        # Rewriting submodule URLs:
        if rewrite_subhandle_urls != "never":
            # for each submodule:
            if rewrite_subhandle_urls == "ask":
                # rewrite = ask => True/False = Yes/No
                pass
            elif rewrite_subhandle_urls == "all":
                rewrite = True
            if rewrite:
                # TODO: Rewrite it and commit
                pass

        # push local state:
        handle_repo.git_push(remote)
        # in case of an annex also push git-annex branch:
        if is_annex(handle_repo.path):
            handle_repo.git_push(remote, "+git-annex:git-annex")
