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
from os.path import join as opj, abspath, basename, relpath, normpath
from distutils.version import LooseVersion

from six.moves.urllib.parse import urlparse

from datalad.support.param import Parameter
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.support.constraints import EnsureChoice
from datalad.support.gitrepo import GitRepo
from datalad.cmd import Runner
from ..interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod
from datalad.cmd import CommandError
from datalad.utils import not_supported_on_windows, getpwd
from .add_sibling import AddSibling
from datalad import ssh_manager

lgr = logging.getLogger('datalad.distribution.create_publication_target_sshwebserver')


class CreatePublicationTargetSSHWebserver(Interface):
    """Create a dataset on a web server via SSH, that may then serve as
    a target for the publish command, if added as a sibling."""

    _params_ = dict(
        # TODO: Somehow the replacement of '_' and '-' is buggy on
        # positional arguments
        # TODO: Figure out, whether (and when) to use `sshurl` as push url
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to create the publication target for.  If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        sshurl=Parameter(
            args=("sshurl",),
            doc="""SSH URL to use to log into the server and create the target
                dataset(s).  This also serves as a default for the URL to be
                used to add the target as a sibling to `dataset` and as a
                default for the directory on the server, where to create the
                dataset""",
            constraints=EnsureStr()),
        target=Parameter(
            args=('target',),
            doc="""sibling name to create for this publication target.
                If `recursive` is set, the same name will be used to address
                the subdatasets' siblings.  Note, that this is just a
                convenience function, calling add_sibling after the actual
                creation of the target dataset(s).  Whenever the creation fails,
                no siblings are added""",
            constraints=EnsureStr() | EnsureNone(),
            nargs="?"),
        target_dir=Parameter(
            args=('--target-dir',),
            doc="""path to the directory on the server where to create the
                dataset.  By default it's wherever `sshurl` points to.  If a
                relative path is provided, it's interpreted as relative to the
                user's home directory on the server.
                Especially when using `recursive`, it's possible to provide a
                template for building the URLs of all (sub)datasets to be
                created by using placeholders.  If you don't provide a template
                the local hierarchy with respect to `dataset` will be
                replicated on the server rooting in `target_dir`.\n
                list of currently available placeholders:\n
                %%NAME\tthe name of the datasets, where slashes are
                replaced by dashes\n""",
            constraints=EnsureStr() | EnsureNone()),
        target_url=Parameter(
            args=('--target-url',),
            doc="""the URL of the dataset sibling named by `target`.  Defaults
                to `sshurl`.  This URL has to be accessible to anyone, who is
                supposed to have access to the dataset later on.\n
                Especially when using `recursive`, it's possible to provide a
                template for building the URLs of all (sub)datasets to be
                created by using placeholders.\n
                list of currently available placeholders:\n
                %%NAME\tthe name of the datasets, where slashes are
                replaced by dashes\n""",
            nargs="?",
            constraints=EnsureStr() | EnsureNone()),
        target_pushurl=Parameter(
            args=('--target-pushurl',),
            doc="""defaults to `sshurl`.  In case the `target_url` cannot be
                used to publish to the dataset sibling, this option specifies a
                URL to be used for the actual publication operation""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""recursively create the publication target for all
                subdatasets of `dataset`""",),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'replace', 'raise'),
            doc="""zction to perform, if target directory exists already.
                Dataset is skipped if `skip`. `replace` forces to (re-)init
                git and to (re-)configure sibling `target`
                (i.e. its URL(s)) in case it already exists.  `raise` just
                raises an Exception""",),
        shared=Parameter(
            args=("--shared",),
            doc="""passed to git-init.  TODO: Figure out how to communicate what
                this is about""",
            constraints=EnsureStr() | EnsureBool()),)

    @staticmethod
    @datasetmethod(name='create_publication_target_sshwebserver')
    def __call__(sshurl, target=None, target_dir=None,
                 target_url=None, target_pushurl=None,
                 dataset=None, recursive=False,
                 existing='raise', shared=False):

        if sshurl is None:
            raise ValueError("""insufficient information for target creation
            (needs at least a dataset and a SSH URL).""")

        if target is None and (target_url is not None
                               or target_pushurl is not None):
            raise ValueError("""insufficient information for adding the target
            as a sibling (needs at least a name)""")

        # shortcut
        ds = dataset

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
        assert(ds is not None and sshurl is not None)

        if not ds.is_installed():
            raise ValueError("""Dataset {0} is not installed yet.""".format(ds))
        assert(ds.repo is not None)

        # determine target parameters:
        parsed_target = urlparse(sshurl)
        host_name = parsed_target.netloc

        # TODO: Sufficient to fail on this condition?
        if not parsed_target.netloc:
            raise ValueError("Malformed URL: {0}".format(sshurl))

        if target_dir is None:
            if parsed_target.path:
                target_dir = parsed_target.path
            else:
                target_dir = '.'

        # TODO: centralize and generalize template symbol handling
        replicate_local_structure = False
        if "%NAME" not in target_dir:
            replicate_local_structure = True

        # collect datasets to use:
        datasets = dict()
        datasets[basename(ds.path)] = ds
        if recursive:
            for subds in ds.get_dataset_handles(recursive=True):
                sub_path = opj(ds.path, subds)
                # TODO: when enhancing Dataset/*Repo classes and therefore
                # adapt to moved code, make proper distinction between name and
                # path of a submodule, which are technically different. This
                # probably will become important on windows as well as whenever
                # we want to allow for moved worktrees.
                datasets[basename(ds.path) + '/' + subds] = \
                    Dataset(sub_path)

        # request ssh connection:
        not_supported_on_windows("TODO")
        lgr.info("Connecting ...")
        ssh = ssh_manager.get_connection(sshurl)
        ssh.open()

        lgr.info("Creating target datasets ...")
        for current_dataset in datasets:
            if not replicate_local_structure:
                path = target_dir.replace("%NAME",
                                          current_dataset.replace("/", "-"))
            else:
                # TODO: opj depends on local platform, not the remote one.
                # check how to deal with it. Does windows ssh server accept
                # posix paths? vice versa? Should planned SSH class provide
                # tools for this issue?
                path = normpath(opj(target_dir,
                                    relpath(datasets[current_dataset].path,
                                            start=ds.path)))

            if path != '.':
                # check if target exists
                # TODO: Is this condition valid for != '.' only?
                path_exists = True
                try:
                    out, err = ssh(["ls", path])
                except CommandError as e:
                    if "No such file or directory" in e.stderr and \
                                    path in e.stderr:
                        path_exists = False
                    else:
                        raise  # It's an unexpected failure here

                if path_exists:
                    if existing == 'raise':
                        raise RuntimeError(
                            "Target directory %s already exists." % path)
                    elif existing == 'skip':
                        continue
                    elif existing == 'replace':
                        pass
                    else:
                        raise ValueError("Do not know how to hand existing=%s" % repr(existing))

                try:
                    ssh(["mkdir", "-p", path])
                except CommandError as e:
                    lgr.error("Remotely creating target directory failed at "
                              "%s.\nError: %s" % (path, str(e)))
                    continue

            # init git repo
            cmd = ["git", "-C", path, "init"]
            if shared:
                cmd.append("--shared=%s" % shared)
            try:
                ssh(cmd)
            except CommandError as e:
                lgr.error("Remotely initializing git repository failed at %s."
                          "\nError: %s\nSkipping ..." % (path, str(e)))
                continue

            # check git version on remote end:
            try:
                out, err = ssh(["git", "version"])
                assert out.strip().startswith("git version")
                git_version = out.strip().split()[2]
                lgr.debug("Detected git version on server: %s" % git_version)
                if LooseVersion(git_version) < "2.4":
                    lgr.error("Git version >= 2.4 needed to configure remote."
                              " Version detected on server: %s\nSkipping ..."
                              % git_version)
                    continue

            except CommandError as e:
                lgr.warning(
                    "Failed to determine git version on remote.\n"
                    "Error: {0}\nTrying to configure anyway "
                    "...".format(e.message))

            # allow for pushing to checked out branch
            try:
                ssh(["git", "-C", path, "config", "receive.denyCurrentBranch",
                     "updateInstead"])
            except CommandError as e:
                lgr.warning("git config failed at remote location %s.\n"
                            "You will not be able to push to checked out "
                            "branch." % path)

            # enable post-update hook:
            try:
                ssh(["mv", opj(path, ".git/hooks/post-update.sample"),
                             opj(path, ".git/hooks/post-update")])
            except CommandError as e:
                lgr.error("Failed to enable post update hook.\n"
                          "Error: %s" % e.message)

            # initially update server info "manually":
            try:
                ssh(["git", "-C", path, "update-server-info"])
            except CommandError as e:
                lgr.error("Failed to update server info.\n"
                          "Error: %s" % e.message)

        if target:
            # add the sibling(s):
            if target_url is None:
                target_url = sshurl
            if target_pushurl is None:
                target_pushurl = sshurl
            result_adding = AddSibling()(dataset=ds,
                                         name=target,
                                         url=target_url,
                                         pushurl=target_pushurl,
                                         recursive=recursive,
                                         force=existing in {'replace'})

        # TODO: Return value!?
