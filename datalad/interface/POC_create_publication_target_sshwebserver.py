# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for creation of publication target via SSH
"""

__docformat__ = 'restructuredtext'


import logging

from os import curdir
from os.path import join as opj, abspath, expanduser, expandvars, exists, isdir, basename, commonprefix

from six.moves.urllib.parse import urlparse

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool, \
    EnsureDatasetAbsolutePath
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.cmdline.helpers import POC_get_root_handle
from .base import Interface
from .POC_helpers import get_submodules_dict, get_submodules_list, is_annex, get_all_submodules_dict, get_git_dir, get_remotes
from datalad.cmd import CommandError
from datalad.utils import assure_dir, not_supported_on_windows
from datalad.consts import HANDLE_META_DIR, POC_STD_META_FILE


lgr = logging.getLogger('datalad.interface.POC_create_publication_target_sshwebserver')


class POCCreatePublicationTargetSSHWebserver(Interface):
    """Create a target repository for publish and add it as a remote to
    push to."""

    _params_ = dict(
        # TODO: Somehow the replacement of '_' and '-' is buggy on positional arguments
        sshurl=Parameter(
            args=("sshurl",),
            doc="SSH URL to use to create the target repository.",
            constraints=EnsureStr()),
        remote=Parameter(
            args=('remote',),
            doc="Remote name to create for this publication target."
                "If RECURSIVE is set, the same name will be used to address "
                "the subhandles' remotes.",
            constraints=EnsureStr()),
        remote_url=Parameter(
            args=('--remote-url',),
            doc="The URL of the repository named by REMOTE. This URL has to be "
                "accessible to anyone, who is supposed to have access to the "
                "published handle later on. (Technically: a git fetch URL)\n"
                "If you want to publish RECURSIVE, it is expected, that you "
                "pass a template for building the URLs of all handles to be "
                "published by using placeholders.\n"
                "List of currently available placeholders:\n"
                "%%NAME\tthe name of the handle, where slashes are "
                "replaced by dashes.\n"
                "If no URL is given, SSH-URL is used. This is probably not want "
                "you want.",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        remote_url_push=Parameter(
            args=('--remote-url-push',),
            doc="In case the REMOTE_URL cannot be used to push to the remote "
                "repository, use this parameter to additionally provide a "
                "push URL.\n"
                "By default the REMOTE-URL is used (which defaults to the SSH-URL)."
                "If you want to publish RECURSIVE, it is expected, that you "
                "pass a template for building the URLs of all handles to be "
                "published by using placeholders.\n"
                "List of currently available placeholders:\n"
                "%%NAME\tthe name of the handle, where slashes are "
                "replaced by dashes.\n",
            constraints=EnsureStr() | EnsureNone()),
        target_dir=Parameter(
            args=('--target-dir',),
            doc="Directory on the server where to create the repository and "
                "that will be accessible via REMOTE-URL. By "
                "default it's wherever SSH-URL points to."
                "If you want to publish RECURSIVE, it is expected, that you "
                "pass a template for building the URLs of all handles to be "
                "published by using placeholders.\n"
                "List of currently available placeholders:\n"
                "%%NAME\tthe name of the handle, where slashes are "
                "replaced by dashes.\n",
            constraints=EnsureStr() | EnsureNone()),
        handle=Parameter(
            args=('--handle',),
            doc="Name of or path to the handle to publish. Defaults to CWD.",
            nargs="?",
            constraints=EnsureDatasetAbsolutePath()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="Recursively create target repositories for all subhandles of "
                "HANDLE."),
        force=Parameter(
            args=("--force", "-f",),
            doc="If target directory exists already, force to (re-)init git.",
            constraints=EnsureBool(),),)

    @staticmethod
    def __call__(sshurl, remote, remote_url=None, remote_url_push=None,
                 target_dir=None, handle=curdir, recursive=False,
                 force=False):

        # TODO: Exception handling:
        top_handle_repo = GitRepo(handle, create=False)

        # check parameters:
        if remote_url is None:
            remote_url = sshurl
        if remote_url_push is None:
            remote_url_push = remote_url
        # we want to be able to redeploy to a configured remote
        # if remote in get_remotes(top_handle_repo, all=True):
        #    raise ValueError("Remote '%s' already exists." % remote)

        handles_to_use = [top_handle_repo]
        if recursive:
            if not remote_url:
                raise
            if not target_dir:
                raise
            handles_to_use += [GitRepo(opj(top_handle_repo.path, sub_path))
                               for sub_path in
                               get_submodules_list(top_handle_repo)]

        # setup SSH Connection:
        # TODO: Make the entire setup a helper to use it when pushing via publish?
        parsed_target = urlparse(sshurl)
        host_name = parsed_target.netloc

        # - build control master:
        from datalad.utils import assure_dir
        not_supported_on_windows("TODO")
        from os import geteuid  # Linux specific import
        var_run_user_datalad = "/var/run/user/%s/datalad" % geteuid()
        assure_dir(var_run_user_datalad)
        control_path = "%s/%s" % (var_run_user_datalad, host_name)
        control_path += ":%s" % parsed_target.port if parsed_target.port else ""

        # - start control master:
        cmd = "ssh -o ControlMaster=yes -o \"ControlPath=%s\" " \
              "-o ControlPersist=yes %s exit" % (control_path, host_name)
        lgr.debug("Try starting control master by calling:\n%s" % cmd)
        import subprocess
        proc = subprocess.Popen(cmd, shell=True)
        proc.communicate(input="\n")  # why the f.. this is necessary?

        runner = Runner()
        ssh_cmd = ["ssh", "-S", control_path, host_name]

        # TODO: parsed_target.path may have to be stripped off of leading "/".

        if parsed_target.path:
            if target_dir:
                # XXX if we support publishing to windows, this could fail
                # from a unix machine
                target_dir = opj(parsed_target.path, target_dir)
            else:
                target_dir = parsed_target.path
        else:
            # XXX do we want to go with the user's home dir at all?
            target_dir = target_dir if target_dir else '.'

        for handle_repo in handles_to_use:

            # create remote repository
            handle_name = handle_repo.path[len(
                commonprefix([top_handle_repo.path,
                              handle_repo.path])):].strip("/")
            path = target_dir.replace("%%NAME", handle_name.replace("/", "-"))

            if path != '.':
                # check if target exists, and if not --force is given,
                # fail here
                # TODO: Is this condition valid for != '.' only?
                path_exists = True
                cmd = ssh_cmd + ["ls", path]
                try:
                    out, err = runner.run(cmd)
                except CommandError as e:
                    if "%s: No such file or directory" % path in e.stderr:
                        path_exists = False
                    else:
                        raise # It's an unexpected failure here

                if path_exists and not force:
                    raise RuntimeError("Target directory %s already exists." %
                                       path)

                cmd = ssh_cmd + ["mkdir", "-p", path]
                try:
                    runner.run(cmd)
                except CommandError as e:
                    lgr.error("Remotely creating target directory failed at "
                              "%s.\nError: %s" % (path, str(e)))
                    continue

            # init git repo
            cmd = ssh_cmd + ["git", "-C", path, "init"]
            try:
                runner.run(cmd)
            except CommandError as e:
                lgr.error("Remotely initializing git repository failed at %s."
                          "\nError: %s" % (path, str(e)))
                continue

            # allow for pushing to checked out branch
            cmd = ssh_cmd + ["git", "-C", path, "config",
                             "receive.denyCurrentBranch",
                             "updateInstead"]
            try:
                runner.run(cmd)
            except CommandError as e:
                lgr.warning("git config failed at remote location %s.\n"
                            "Skipped." % path)

            # add remote
            handle_remote_url = \
                remote_url.replace("%%NAME", handle_name.replace("/", "-"))
            handle_remote_url_push = \
                remote_url_push.replace("%%NAME", handle_name.replace("/", "-"))
            if remote not in handle_repo.git_get_remotes():
                cmd = ["git", "remote", "add", remote, handle_remote_url]
                runner.run(cmd, cwd=handle_repo.path)
                cmd = ["git", "remote", "set-url", "--push", remote,
                       handle_remote_url_push]
                runner.run(cmd, cwd=handle_repo.path)
            else:
                cmd = ["git", "remote", "get-url", "--push", remote]
                out, err = runner.run(cmd, cwd=handle_repo.path)
                if handle_remote_url_push != out.strip():
                    lgr.error("Remote {1} is already configured with a "
                              "different URL".format(remote))
                    continue



