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
from ..interface.base import Interface
from ..interface.POC_helpers import get_submodules_dict, get_submodules_list, get_all_submodules_dict, get_git_dir, get_remotes
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod, resolve_path
from datalad.cmd import CommandError
from datalad.utils import assure_dir, not_supported_on_windows, getpwd
from datalad.consts import HANDLE_META_DIR, POC_STD_META_FILE


lgr = logging.getLogger('datalad.distribution.create_publication_target_sshwebserver')


class CreatePublicationTargetSSHWebserver(Interface):
    """Create a target repository for publish and add it as a remote to
    push to."""

    _params_ = dict(
        # TODO: Somehow the replacement of '_' and '-' is buggy on
        # positional arguments
        # TODO: Figure out, whether (and when) to use `sshurl` as push url
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to create the publication target for. If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        target=Parameter(
            args=('target',),
            doc="""Sibling name to create for this publication target.
                If RECURSIVE is set, the same name will be used to address
                the subdatasets' siblings""",
            constraints=EnsureStr() | EnsureNone()),
        sshurl=Parameter(
            args=("sshurl",),
            doc="""SSH URL to use to create the target sibling(s)""",
            constraints=EnsureStr() | EnsureNone()),
        target_dir=Parameter(
            args=('--target-dir',),
            doc="""Directory on the server where to create the repository and
                that will be accessible via `target_url`. By
                default it's wherever `sshurl` points to.
                If you want to publish recursively, it is expected, that you
                pass a template for building the URLs of all (sub)datasets to
                be published by using placeholders.\n
                List of currently available placeholders:\n
                %%NAME\tthe name of the handle, where slashes are
                replaced by dashes.\n""",
            constraints=EnsureStr() | EnsureNone()),
        target_url=Parameter(
            args=('--target-url',),
            doc="""The URL of the dataset sibling named by `target`. Defaults
                to `sshurl`. This URL has to be accessible to anyone, who is
                supposed to have access to the published dataset later on.\n
                If you want to publish with `recursive`, it is expected, that
                you pass a template for building the URLs of all (sub)datasets
                to be published by using placeholders.\n
                List of currently available placeholders:\n
                %%NAME\tthe name of the dataset, where slashes are replaced by
                dashes.\nThis option is ignored if there is already a
                configured sibling dataset under the name given by `target`""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        target_pushurl=Parameter(
            args=('--target-pushurl',),
            doc="""Defaults to `sshurl`. In case the `target_url` cannot be
                used to publish to the dataset sibling, this option specifies a
                URL to be used for the actual publication operation.\n
                This option is ignored if there is already a configured sibling
                dataset under the name given by `target`""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""Recursively create the publication target for all
                subdatasets of `dataset`""",),
        force=Parameter(
            args=("--force", "-f",),
            action="store_true",
            doc="""If target directory exists already, force to (re-)init
                git""",),)

    @staticmethod
    @datasetmethod(name='create_publication_target_sshwebserver')
    def __call__(dataset=None, target=None, sshurl=None, target_dir=None,
                 target_url=None, target_pushurl=None, recursive=False,
                 force=False):
        # shortcut
        ds = dataset

        if target is None or sshurl is None:
            raise ValueError("""insufficient information for target creation
                (needs at least a dataset, a target name and a SSH URL.""")

        if ds is not None and not isinstance(ds, Dataset):
            ds = Dataset(ds)
        if ds is None:
            # try to find a dataset at or above CWD
            dspath = GitRepo.get_toppath(abspath(getpwd()))
            if dspath is None:
                raise ValueError("""No dataset found
                                 at or above {0}.""".format(getpwd()))
            ds = Dataset(dspath)
            lgr.debug("Resolved dataset for target creation: {0}".format(ds))
        assert(ds is not None and target is not None and sshurl is not None)

        if not ds.is_installed():
            raise ValueError("""Dataset {0} is not installed yet.""".format(ds))
        assert(ds.repo is not None)

        # determine target parameters:
        parsed_target = urlparse(sshurl)
        host_name = parsed_target.netloc

        if not parsed_target.netloc:
            raise ValueError("Malformed URL: {0}".format(sshurl))

        if parsed_target.path:
            if target_dir:
                # TODO: if we support publishing to windows, this could fail
                # from a unix machine
                target_dir = opj(parsed_target.path, target_dir)
            else:
                target_dir = parsed_target.path
        else:
            # XXX do we want to go with the user's home dir at all?
            target_dir = target_dir if target_dir else '.'

        # set default urls:
        # TODO: Allow for templates in sshurl directly?
        # TODO: Check whether template leads to conflicting urls if recursive
        if target_url is None:
            target_url = sshurl + target_dir
        if target_pushurl is None:
            target_pushurl = sshurl + target_dir

        # create dict: dataset.name => dataset.repo
        # TODO: with these names, do checks for urls. See above.
        repos = dict()
        repos[basename(ds.path)] = ds.repo
        if recursive:
            for subds in ds.get_dataset_handles(recursive=True):
                sub_path = opj(ds.path, subds)
                repos[basename(ds.path) + '/' + subds] = \
                    GitRepo(sub_path, create=False)

        # setup SSH Connection:
        # TODO: Make the entire setup a helper to use it when pushing via
        # publish?

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

        for repo in repos:

            if target in repos[repo].git_get_remotes():
                # TODO: skip or raise? If raise, do it before looping, in order
                # to fail without messing up things by partially doing the shit
                # - what about just adding new push url to that remote?
                # - if url(s) fit, then still try to create target?

                # cmd = ["git", "remote", "get-url", "--push", remote]
                # out, err = runner.run(cmd, cwd=handle_repo.path)
                # if handle_remote_url_push != out.strip():
                lgr.warning("Sibling {0} already exists. Skipping".format(target))
                continue

            # %NAME
            REPO_NAME = repo.replace("/", "-")

            # create remote repository
            path = target_dir.replace("%NAME", REPO_NAME)

            if path != '.':
                # check if target exists, and if not --force is given,
                # fail here
                # TODO: Is this condition valid for != '.' only?
                path_exists = True
                cmd = ssh_cmd + ["ls", path]
                try:
                    out, err = runner.run(cmd, expect_fail=True,
                                          expect_stderr=True)
                except CommandError as e:
                    if "%s: No such file or directory" % path in e.stderr:
                        path_exists = False
                    else:
                        raise  # It's an unexpected failure here

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

            # add the remote
            cmd = ["git", "remote", "add", target,
                   target_url.replace("%NAME", REPO_NAME)]
            runner.run(cmd, cwd=repos[repo].path)
            cmd = ["git", "remote", "set-url", "--push", target,
                   target_pushurl.replace("%NAME", REPO_NAME)]
            runner.run(cmd, cwd=repos[repo].path)

