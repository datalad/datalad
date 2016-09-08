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
import datalad
from os.path import join as opj, abspath, basename, relpath, normpath, dirname
from distutils.version import LooseVersion
from jsmin import jsmin
from glob import glob

from datalad.support.network import RI, URL, SSHRI
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.dochelpers import exc_str
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.support.constraints import EnsureChoice
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from ..interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod
from datalad.cmd import CommandError
from datalad.utils import not_supported_on_windows, getpwd
from .add_sibling import AddSibling
from datalad import ssh_manager
from datalad.cmd import Runner
from datalad.dochelpers import exc_str
from datalad.utils import make_tempfile

lgr = logging.getLogger('datalad.distribution.create_publication_target_sshwebserver')


class CreatePublicationTargetSSHWebserver(Interface):
    """Create empty dataset(s) on a web server via SSH.

    They can then serve as a target for the `publish` command, once added as a
    sibling.
    """

    _params_ = dict(
        # TODO: Figure out, whether (and when) to use `sshurl` as push url
        dataset=Parameter(
            args=("--dataset", "-d",),
            doc="""specify the dataset to create the publication target for. If
                no dataset is given, an attempt is made to identify the dataset
                based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        sshurl=Parameter(
            args=("sshurl",),
            metavar='SSHURL',
            doc="""Login information for the target server. This can be given
                as a URL (ssh://host/path) or SSH-style (user@host:path).
                Unless overridden, this also serves the future dataset's access
                URL and path on the server.""",
            constraints=EnsureStr()),
        target=Parameter(
            args=('target',),
            metavar='TARGETNAME',
            doc="""sibling name to create for this publication target.
                If `recursive` is set, the same name will be used to label all
                the subdatasets' siblings.  Note, this is just a
                convenience option, siblings can also be added at a later point
                in time.  When creation target datasets fails, no siblings are
                added""",
            constraints=EnsureStr() | EnsureNone(),
            nargs="?"),
        target_dir=Parameter(
            args=('--target-dir',),
            metavar='PATH',
            doc="""path to the directory *on the server* where the dataset
                shall be created. By default the SSH access URL is used to
                identify this directory. If a relative path is provided here,
                it is interpreted as being relative to the user's home
                directory on the server.\n
                Additional features are relevant for recursive processing of
                datasets with subdatasets. By default, the local
                dataset structure is replicated on the server. However, it is
                possible to provide a template for generating different target
                directory names for all (sub)datasets. Templates can contain
                certain placeholder that are substituted for each (sub)dataset.
                For example: "/mydirectory/dataset-%%NAME".\nSupported
                placeholders:\n
                %%NAME - the name of the datasets, with any slashes replaced by
                dashes\n""",
            constraints=EnsureStr() | EnsureNone()),
        target_url=Parameter(
            args=('--target-url',),
            metavar='URL',
            doc=""""public" access URL of the to-be-created target dataset(s)
                (default: `sshurl`). Accessiblity of this URL determines the
                access permissions of potential consumers of the dataset.
                As with `target_dir`, templates (same set of placeholders)
                are supported.\n""",
            constraints=EnsureStr() | EnsureNone()),
        target_pushurl=Parameter(
            args=('--target-pushurl',),
            metavar='URL',
            doc="""In case the `target_url` cannot be used to publish to the
                dataset, this option specifies an alternative URL for this
                purpose. As with `target_url`, templates (same set of
                placeholders) are supported.\n""",
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r"),
            action="store_true",
            doc="""recursively create the publication target for all
                subdatasets of `dataset`""",),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'replace', 'error', 'reconfigure'),
            metavar='MODE',
            doc="""action to perform, if target directory exists already.
                Dataset is skipped if 'skip'. 'replace' forces to (re-)init
                the dataset, and to (re-)configure the dataset sibling,
                i.e. its URL(s), in case it already exists. 'reconfigure'
                updates metadata of the dataset sibling. 'error' causes
                an exception to be raised.""",),
        shared=Parameter(
            args=("--shared",),
            metavar='false|true|umask|group|all|world|everybody|0xxx',
            doc="""if given, configures the access permissions on the server
            for multi-users (this could include access by a webserver!).
            Possible values for this option are identical to those of
            `git init --shared` and are described in its documentation.""",
            constraints=EnsureStr() | EnsureBool()),)

    @staticmethod
    @datasetmethod(name='create_publication_target_sshwebserver')
    def __call__(sshurl, target=None, target_dir=None,
                 target_url=None, target_pushurl=None,
                 dataset=None, recursive=False,
                 existing='error', shared=False):

        if sshurl is None:
            raise ValueError("""insufficient information for target creation
            (needs at least a dataset and a SSH URL).""")

        if target is None and (target_url is not None or
                               target_pushurl is not None):
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
        sshri = RI(sshurl)

        if not isinstance(sshri, SSHRI) \
                and not (isinstance(sshri, URL) and sshri.scheme == 'ssh'):
                    raise ValueError("Unsupported SSH URL: '{0}', use ssh://host/path or host:path syntax".format(sshurl))

        if target_dir is None:
            if sshri.path:
                target_dir = sshri.path
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
            for subds in ds.get_subdatasets(recursive=True):
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

        # flag to check if at dataset_root
        at_root = True

        # loop over all datasets, ordered from top to bottom to make test
        # below valid (existing directories would cause the machinery to halt)
        for current_dataset in \
                sorted(datasets.keys(), key=lambda x: x.count('/')):
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

            lgr.info("Creating target dataset {0} at {1}".format(current_dataset, path))
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
                    if existing == 'error':
                        raise RuntimeError("Target directory %s already exists." % path)
                    elif existing == 'skip':
                        continue
                    elif existing == 'replace':
                        ssh(["chmod", "+r+w", "-R", path])  # enable write permissions to allow removing dir
                        ssh(["rm", "-rf", path])            # remove target at path
                        path_exists = False                 # if we succeeded in removing it
                    elif existing == 'reconfigure':
                        pass
                    else:
                        raise ValueError("Do not know how to handle existing=%s" % repr(existing))

                if not path_exists:
                    try:
                        ssh(["mkdir", "-p", path])
                    except CommandError as e:
                        lgr.error("Remotely creating target directory failed at "
                                  "%s.\nError: %s" % (path, exc_str(e)))
                        continue

            # don't (re-)initialize dataset if existing == reconfigure
            if existing != 'reconfigure':
                # init git repo
                if not CreatePublicationTargetSSHWebserver.init_remote_repo(path, ssh, shared,
                                                                            datasets[current_dataset]):
                    continue

            # check git version on remote end
            lgr.info("Adjusting remote git configuration")
            remote_git_version = CreatePublicationTargetSSHWebserver.get_remote_git_version(ssh)
            if remote_git_version and remote_git_version >= "2.4":
                # allow for pushing to checked out branch
                try:
                    ssh(["git", "-C", path, "config", "receive.denyCurrentBranch",
                         "updateInstead"])
                except CommandError as e:
                    lgr.error("git config failed at remote location %s.\n"
                              "You will not be able to push to checked out "
                              "branch. Error: %s", path, exc_str(e))
            else:
                lgr.error("Git version >= 2.4 needed to configure remote."
                          " Version detected on server: %s\nSkipping configuration"
                          " of receive.denyCurrentBranch - you will not be able to"
                          " publish updates to this repository. Upgrade your git"
                          " and run with --existing=reconfigure"
                          % remote_git_version)

            # enable metadata refresh on dataset updates to publication server
            lgr.info("Enabling git post-update hook ...")
            try:
                CreatePublicationTargetSSHWebserver.create_postupdate_hook(path, ssh, datasets[current_dataset])
            except CommandError as e:
                lgr.error("Failed to add json creation command to post update hook.\n"
                          "Error: %s" % exc_str(e))

            # publish web-interface to root dataset on publication server
            if at_root:
                lgr.info("Uploading web interface to %s" % path)
                at_root = False
                try:
                    CreatePublicationTargetSSHWebserver.upload_web_interface(path, ssh, shared)
                except CommandError as e:
                    lgr.error("Failed to push web interface to the remote datalad repository.\n"
                              "Error: %s" % exc_str(e))

            # don't (re-)initialize dataset if existing == reconfigure
            if existing != 'reconfigure':
                # initially update server info "manually":
                try:
                    ssh(["git", "-C", path, "update-server-info"])
                except CommandError as e:
                    lgr.error("Failed to update server info.\n"
                              "Error: %s" % exc_str(e))

        if target:
            # add the sibling(s):
            if target_url is None:
                target_url = sshurl
            if target_pushurl is None:
                target_pushurl = sshurl
            AddSibling()(dataset=ds,
                         name=target,
                         url=target_url,
                         pushurl=target_pushurl,
                         recursive=recursive,
                         force=existing in {'replace'})

        # TODO: Return value!?
        #       => [(Dataset, fetch_url)]

    @staticmethod
    def init_remote_repo(path, ssh, shared, dataset):
        cmd = ["git", "-C", path, "init"]
        if shared:
            cmd.append("--shared=%s" % shared)
        try:
            ssh(cmd)
        except CommandError as e:
            lgr.error("Initialization of remote git repository failed at %s."
                      "\nError: %s\nSkipping ..." % (path, exc_str(e)))
            return False

        if isinstance(dataset.repo, AnnexRepo):
            # init remote git annex repo (part fix of #463)
            try:
                ssh(["git", "-C", path, "annex", "init"])
            except CommandError as e:
                lgr.error("Initialization of remote git annex repository failed at %s."
                          "\nError: %s\nSkipping ..." % (path, exc_str(e)))
                return False
        return True

    @staticmethod
    def get_remote_git_version(ssh):
        try:
            out, err = ssh(["git", "version"])
            assert out.strip().startswith("git version")
            git_version = out.strip().split()[2]
            lgr.debug("Detected git version on server: %s" % git_version)
            return LooseVersion(git_version)

        except CommandError as e:
            lgr.warning(
                "Failed to determine git version on remote.\n"
                "Error: {0}\nTrying to configure anyway "
                "...".format(exc_str(e)))
        return None

    @staticmethod
    def create_postupdate_hook(path, ssh, dataset):
        # location of post-update hook file, logs folder on remote target
        hook_remote_target = opj(path, '.git', 'hooks', 'post-update')
        logs_remote_target = opj(path, '.git', 'datalad', 'logs')

        # create json command for current dataset
        json_command = 'which datalad > /dev/null && (cd ..; GIT_DIR=$PWD/.git datalad ls -r --json file \'{}\';) &> "{}/{}"'
        json_command = json_command.format(str(path), logs_remote_target, 'datalad-publish-hook-$(date +%Y-%m-%dT%H:%M:%S%z).log')

        # collate content for post_update hook
        hook_content = '\n'.join(['#!/bin/bash', 'git update-server-info', json_command])

        # make datalad logs directory
        ssh(['mkdir', '-p', logs_remote_target])

        with make_tempfile(content=hook_content) as tempf:  # create post_update hook script
            ssh.copy(tempf, hook_remote_target)             # upload hook to dataset
        ssh(['chmod', '+x', hook_remote_target])            # and make it executable

        # Initialize annex repo on remote copy if current_dataset is an AnnexRepo
        if isinstance(dataset.repo, AnnexRepo):
            ssh(['git', '-C', path, 'annex', 'init', path])

    @staticmethod
    def upload_web_interface(path, ssh, shared):
        # path to web interface resources on local
        webui_local = opj(dirname(datalad.__file__), 'resources', 'website')
        # upload html to dataset
        html = opj(webui_local, 'index.html')
        ssh.copy(html, path)

        # upload assets to the dataset
        webresources_local = opj(webui_local, 'assets')
        webresources_remote = opj(path, '.git', 'datalad', 'web')
        ssh(['mkdir', '-p', webresources_remote])
        ssh.copy(webresources_local, webresources_remote, recursive=True)

        # minimize and upload js assets
        for js_file in glob(opj(webresources_local, 'js', '*.js')):
            with open(js_file) as asset:
                minified = jsmin(asset.read())                          # minify asset
                with make_tempfile(content=minified) as tempf:          # write minified to tempfile
                    js_name = js_file.split('/')[-1]
                    ssh.copy(tempf, opj(webresources_remote, 'assets', 'js', js_name))  # and upload js

        # explicitly make web+metadata dir of dataset world-readable, if shared set to 'all'
        mode = None
        if shared in (True, 'true', 'all', 'world', 'everybody'):
            mode = 'a+rX'
        elif shared == 'group':
            mode = 'g+rX'
        elif str(shared).startswith('0'):
            mode = shared

        if mode:
            ssh(['chmod', mode, '-R', dirname(webresources_remote)])
