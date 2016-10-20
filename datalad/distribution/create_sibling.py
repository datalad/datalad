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
from glob import glob

from datalad.support.network import RI, URL, SSHRI
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.dochelpers import exc_str
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.support.constraints import EnsureChoice
from datalad.support.annexrepo import AnnexRepo
from ..interface.base import Interface
from datalad.distribution.dataset import EnsureDataset, Dataset, datasetmethod
from datalad.cmd import CommandError
from datalad.utils import not_supported_on_windows, getpwd
from .add_sibling import AddSibling
from datalad import ssh_manager
from datalad.utils import make_tempfile
from datalad.consts import WEB_HTML_DIR, WEB_META_LOG
from datalad.consts import TIMESTAMP_FMT
from datalad.utils import _path_

lgr = logging.getLogger('datalad.distribution.create_sibling')


class CreateSibling(Interface):
    """Create dataset(s)'s sibling (e.g., on a web server).

    Those (empty) datasets can then serve as a target for the `publish` command.
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
                (default: `sshurl`). Accessibility of this URL determines the
                access permissions of potential consumers of the dataset.
                As with `target_dir`, templates (same set of placeholders)
                are supported.  Also, if specified, it is provided as the annex
                description\n""",
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
            constraints=EnsureStr() | EnsureBool()),
        ui=Parameter(
            args=("--ui",),
            metavar='false|true|html_filename',
            doc="""publish a web interface for the dataset with an
            optional user-specified name for the html at publication
            target. defaults to `index.html` at dataset root""",
            constraints=EnsureBool() | EnsureStr()),)

    @staticmethod
    @datasetmethod(name='create_sibling')
    def __call__(sshurl, target=None, target_dir=None,
                 target_url=None, target_pushurl=None,
                 dataset=None, recursive=False,
                 existing='error', shared=False, ui=False):

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
            current_dspath = GitRepo.get_toppath(abspath(getpwd()))
            if current_dspath is None:
                raise ValueError("""No dataset found
                                 at or above {0}.""".format(getpwd()))
            ds = Dataset(current_dspath)
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
        # But we need to run post-update hook in depth-first fashion, so
        # would only collect first and then run (see gh #790)
        remote_repos_to_run_hook_for = []
        for current_dspath in \
                sorted(datasets.keys(), key=lambda x: x.count('/')):
            current_ds = datasets[current_dspath]
            if not current_ds.is_installed():
                lgr.info("Skipping %s since not installed locally", current_dspath)
                continue
            if not replicate_local_structure:
                path = target_dir.replace("%NAME",
                                          current_dspath.replace("/", "-"))
            else:
                # TODO: opj depends on local platform, not the remote one.
                # check how to deal with it. Does windows ssh server accept
                # posix paths? vice versa? Should planned SSH class provide
                # tools for this issue?
                path = normpath(opj(target_dir,
                                    relpath(datasets[current_dspath].path,
                                            start=ds.path)))

            lgr.info("Creating target dataset {0} at {1}".format(current_dspath, path))
            # Must be set to True only if exists and existing='reconfigure'
            # otherwise we might skip actions if we say existing='reconfigure'
            # but it did not even exist before
            only_reconfigure = False
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
                        only_reconfigure = True
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
            if not only_reconfigure:
                # init git and possibly annex repo
                if not CreateSibling.init_remote_repo(
                        path, ssh, shared, datasets[current_dspath],
                        description=target_url):
                    continue

            # check git version on remote end
            lgr.info("Adjusting remote git configuration")
            remote_git_version = CreateSibling.get_remote_git_version(ssh)
            if remote_git_version and remote_git_version >= "2.4":
                # allow for pushing to checked out branch
                try:
                    ssh(["git", "-C", path] + GitRepo._GIT_COMMON_OPTIONS +
                        ["config", "receive.denyCurrentBranch", "updateInstead"])
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
                CreateSibling.create_postupdate_hook(
                    path, ssh, datasets[current_dspath])
            except CommandError as e:
                lgr.error("Failed to add json creation command to post update "
                          "hook.\nError: %s" % exc_str(e))

            # publish web-interface to root dataset on publication server
            if at_root and ui:
                lgr.info("Uploading web interface to %s" % path)
                at_root = False
                try:
                    CreateSibling.upload_web_interface(path, ssh, shared, ui)
                except CommandError as e:
                    lgr.error("Failed to push web interface to the remote "
                              "datalad repository.\nError: %s" % exc_str(e))

            remote_repos_to_run_hook_for.append(path)

        # in reverse order would be depth first
        lgr.debug("Running post-update hooks in all created siblings")
        for path in remote_repos_to_run_hook_for[::-1]:
            # Trigger the hook
            try:
                ssh(
                    ["cd '" + _path_(path, ".git") + "' && hooks/post-update"],
                    wrap_args=False  # we wrapped here manually
                )
            except CommandError as e:
                lgr.error("Failed to run post-update hook under path %s. "
                          "Error: %s" % (path, exc_str(e)))

        if target:
            # add the sibling(s):
            lgr.debug("Adding the siblings")
            if target_url is None:
                target_url = sshurl
            if target_pushurl is None:
                target_pushurl = sshurl
            AddSibling()(dataset=ds,
                         name=target,
                         url=target_url,
                         pushurl=target_pushurl,
                         recursive=recursive,
                         fetch=True,
                         force=existing in {'replace'})

        # TODO: Return value!?
        #       => [(Dataset, fetch_url)]

    @staticmethod
    def init_remote_repo(path, ssh, shared, dataset, description=None):
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
                ssh(
                    ["git", "-C", path, "annex", "init"] +
                    ([description] if description else [])
                )
            except CommandError as e:
                lgr.error("Initialization of remote git annex repository failed at %s."
                          "\nError: %s\nSkipping ..." % (path, exc_str(e)))
                return False
        return True

    @staticmethod
    def get_remote_git_version(ssh):
        try:
            # options to disable all auto so we don't trigger them while testing
            # for absent changes
            out, err = ssh(["git"] + GitRepo._GIT_COMMON_OPTIONS + ["version"])
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
        hooks_remote_dir = opj(path, '.git', 'hooks')
        hook_remote_target = opj(hooks_remote_dir, 'post-update')
        # post-update hook should create its log directory if doesn't exist
        logs_remote_dir = opj(path, WEB_META_LOG)

        make_log_dir = 'mkdir -p "{}"'.format(logs_remote_dir)

        # create json command for current dataset
        json_command = r'''
        mkdir -p {};
        ( which datalad > /dev/null \
        && ( cd ..; GIT_DIR=$PWD/.git datalad ls -a --json file '{}'; ) \
        || echo "no datalad found - skipping generation of indexes for web frontend"; \
        ) &> "{}/{}"
        '''.format(logs_remote_dir,
                   str(path),
                   logs_remote_dir,
                   'datalad-publish-hook-$(date +%s).log' % TIMESTAMP_FMT)

        # collate content for post_update hook
        hook_content = '\n'.join(['#!/bin/bash', 'git update-server-info', make_log_dir, json_command])

        with make_tempfile(content=hook_content) as tempf:  # create post_update hook script
            ssh.copy(tempf, hook_remote_target)             # upload hook to dataset
        ssh(['chmod', '+x', hook_remote_target])            # and make it executable

    @staticmethod
    def upload_web_interface(path, ssh, shared, ui):
        # path to web interface resources on local
        webui_local = opj(dirname(datalad.__file__), 'resources', 'website')
        # local html to dataset
        html_local = opj(webui_local, "index.html")

        # name and location of web-interface html on target
        html_targetname = {True: ui, False: "index.html"}[isinstance(ui, str)]
        html_target = opj(path, html_targetname)

        # upload ui html to target
        ssh.copy(html_local, html_target)

        # upload assets to the dataset
        webresources_local = opj(webui_local, 'assets')
        webresources_remote = opj(path, WEB_HTML_DIR)
        ssh(['mkdir', '-p', webresources_remote])
        ssh.copy(webresources_local, webresources_remote, recursive=True)

        # minimize and upload js assets
        for js_file in glob(opj(webresources_local, 'js', '*.js')):
            with open(js_file) as asset:
                try:
                    from jsmin import jsmin
                    minified = jsmin(asset.read())                      # minify asset
                except ImportError:
                    lgr.warning(
                        "Will not minify web interface javascript, no jsmin available")
                    minified = asset.read()                             # no minify available
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
            ssh(['chmod', mode, '-R', dirname(webresources_remote), opj(path, 'index.html')])
