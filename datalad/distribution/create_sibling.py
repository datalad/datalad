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


from distutils.version import LooseVersion
from glob import glob
import logging
from os.path import join as opj, relpath, normpath, dirname, curdir

import datalad
from datalad import ssh_manager
from datalad.cmd import CommandError
from datalad.consts import WEB_HTML_DIR, WEB_META_LOG
from datalad.consts import TIMESTAMP_FMT
from datalad.dochelpers import exc_str
from datalad.distribution.add_sibling import AddSibling
from datalad.distribution.add_sibling import _check_deps
from datalad.distribution.dataset import EnsureDataset, Dataset, \
    datasetmethod, require_dataset
from datalad.interface.base import Interface
from datalad.interface.common_opts import recursion_limit, recursion_flag
from datalad.interface.common_opts import as_common_datasrc
from datalad.interface.common_opts import publish_by_default
from datalad.interface.common_opts import publish_depends
from datalad.interface.utils import filter_unmodified
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import EnsureStr, EnsureNone, EnsureBool
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.network import RI
from datalad.support.network import is_ssh
from datalad.support.sshconnector import sh_quote
from datalad.support.param import Parameter
from datalad.utils import make_tempfile
from datalad.utils import not_supported_on_windows
from datalad.utils import _path_

lgr = logging.getLogger('datalad.distribution.create_sibling')


def _create_dataset_sibling(
        name,
        ds,
        hierarchy_basepath,
        ssh,
        replicate_local_structure,
        ssh_url,
        target_dir,
        target_url,
        target_pushurl,
        existing,
        shared,
        remote_git_version,
        publish_depends,
        publish_by_default,
        as_common_datasrc):
    localds_path = ds.path
    ds_name = relpath(localds_path, start=hierarchy_basepath)
    if not replicate_local_structure:
        ds_name = '' if ds_name == curdir \
            else '-{}'.format(ds_name.replace("/", "-"))
        remoteds_path = target_dir.replace(
            "%RELNAME",
            ds_name)
    else:
        # TODO: opj depends on local platform, not the remote one.
        # check how to deal with it. Does windows ssh server accept
        # posix paths? vice versa? Should planned SSH class provide
        # tools for this issue?
        # see gh-1188
        remoteds_path = normpath(opj(target_dir, ds_name))

    # construct a would-be ssh url based on the current dataset's path
    ssh_url.path = remoteds_path
    ds_sshurl = ssh_url.as_str()
    # configure dataset's git-access urls
    ds_target_url = target_url.replace('%RELNAME', ds_name) \
        if target_url else ds_sshurl
    # push, configure only if needed
    ds_target_pushurl = None
    if ds_target_url != ds_sshurl:
        # not guaranteed that we can push via the primary URL
        ds_target_pushurl = target_pushurl.replace('%RELNAME', ds_name) \
            if target_pushurl else ds_sshurl

    lgr.info("Creating target dataset {0} at {1}".format(
        localds_path, remoteds_path))
    # Must be set to True only if exists and existing='reconfigure'
    # otherwise we might skip actions if we say existing='reconfigure'
    # but it did not even exist before
    only_reconfigure = False
    if remoteds_path != '.':
        # check if target exists
        # TODO: Is this condition valid for != '.' only?
        path_exists = True
        try:
            out, err = ssh("ls {}".format(sh_quote(remoteds_path)))
        except CommandError as e:
            if "No such file or directory" in e.stderr and \
                    remoteds_path in e.stderr:
                path_exists = False
            else:
                raise  # It's an unexpected failure here

        if path_exists:
            if existing == 'error':
                raise RuntimeError(
                    "Target directory {} already exists.".format(
                        remoteds_path))
            elif existing == 'skip':
                return
            elif existing == 'replace':
                # enable write permissions to allow removing dir
                ssh("chmod +r+w -R {}".format(sh_quote(remoteds_path)))
                # remove target at path
                ssh("rm -rf {}".format(sh_quote(remoteds_path)))
                # if we succeeded in removing it
                path_exists = False
            elif existing == 'reconfigure':
                only_reconfigure = True
            else:
                raise ValueError(
                    "Do not know how to handle existing={}".format(
                        repr(existing)))

        if not path_exists:
            try:
                ssh("mkdir -p {}".format(sh_quote(remoteds_path)))
            except CommandError as e:
                lgr.error("Remotely creating target directory failed at "
                          "%s.\nError: %s" % (remoteds_path, exc_str(e)))
                return

    # don't (re-)initialize dataset if existing == reconfigure
    if not only_reconfigure:
        # init git and possibly annex repo
        if not CreateSibling.init_remote_repo(
                remoteds_path, ssh, shared, ds,
                description=target_url):
            return

    # at this point we have a remote sibling in some shape or form
    # -> add as remote
    lgr.debug("Adding the siblings")
    AddSibling.__call__(
        dataset=ds,
        name=name,
        url=ds_target_url,
        pushurl=ds_target_pushurl,
        recursive=False,
        fetch=True,
        force=existing in {'reconfigure', 'replace'},
        as_common_datasrc=as_common_datasrc,
        publish_by_default=publish_by_default,
        publish_depends=publish_depends)

    # check git version on remote end
    lgr.info("Adjusting remote git configuration")
    if remote_git_version and remote_git_version >= "2.4":
        # allow for pushing to checked out branch
        try:
            ssh("git -C {} config receive.denyCurrentBranch updateInstead".format(
                sh_quote(remoteds_path)))
        except CommandError as e:
            lgr.error("git config failed at remote location %s.\n"
                      "You will not be able to push to checked out "
                      "branch. Error: %s", remoteds_path, exc_str(e))
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
            remoteds_path, ssh, ds)
    except CommandError as e:
        lgr.error("Failed to add json creation command to post update "
                  "hook.\nError: %s" % exc_str(e))

    return remoteds_path


class CreateSibling(Interface):
    """Create a dataset sibling on a UNIX-like SSH-accessible machine

    Given a local dataset, and SSH login information this command creates
    a remote dataset repository and configures it as a dataset sibling to
    be used as a publication target (see `publish` command).

    Various properties of the remote sibling can be configured (e.g. name
    location on the server, read and write access URLs, and access
    permissions.

    Optionally, a basic web-viewer for DataLad datasets can be installed
    at the remote location.

    This command supports recursive processing of dataset hierarchies, creating
    a remote sibling for each dataset in the hierarchy. By default, remote
    siblings are created in hierarchical structure that reflects the
    organization on the local file system. However, a simple templating
    mechanism is provided to produce a flat list of datasets (see
    --target-dir).
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
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""sibling name to create for this publication target.
                If `recursive` is set, the same name will be used to label all
                the subdatasets' siblings. When creating a target dataset fails,
                no sibling is added""",
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
                For example: "/mydirectory/dataset%%RELNAME".\nSupported
                placeholders:\n
                %%RELNAME - the name of the datasets, with any slashes replaced by
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
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'replace', 'error', 'reconfigure'),
            metavar='MODE',
            doc="""action to perform, if a sibling is already configured under the
            given name and/or a target directory already exists.
            In this case, a dataset can be skipped ('skip'), an existing target
            directory be forcefully re-initialized, and the sibling (re-)configured
            ('replace', implies 'reconfigure'), the sibling configuration be updated
            only ('reconfigure'), or to error ('error').""",),
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
            constraints=EnsureBool() | EnsureStr()),
        as_common_datasrc=as_common_datasrc,
        publish_depends=publish_depends,
        publish_by_default=publish_by_default,
        since=Parameter(
            args=("--since",),
            constraints=EnsureStr() | EnsureNone(),
            doc="""limit processing to datasets that have been changed since a given
            state (by tag, branch, commit, etc). This can be used to create siblings
            for recently added subdatasets."""),
    )

    @staticmethod
    @datasetmethod(name='create_sibling')
    def __call__(sshurl, name=None, target_dir=None,
                 target_url=None, target_pushurl=None,
                 dataset=None,
                 recursive=False,
                 recursion_limit=None,
                 existing='error', shared=False, ui=False,
                 as_common_datasrc=None,
                 publish_by_default=None,
                 publish_depends=None,
                 since=None):

        # there is no point in doing anything further
        not_supported_on_windows(
            "Support for SSH connections is not yet implemented in Windows")

        if not sshurl:
            raise InsufficientArgumentsError(
                "need at least an SSH URL")

        # check the login URL
        sshri = RI(sshurl)
        if not is_ssh(sshri):
            raise ValueError(
                "Unsupported SSH URL: '{0}', "
                "use ssh://host/path or host:path syntax".format(sshurl))

        if not name:
            # use the hostname as default remote name
            name = sshri.hostname
            lgr.debug(
                "No sibling name given, use URL hostname '%s' as sibling name",
                name)

        ds = require_dataset(dataset, check_installed=True,
                             purpose='creating a sibling')

        # use common sorting implementation to discover all subdatasets
        content_by_ds, unavailable_paths = Interface._prep(
            # the base data set is the only path
            path=ds.path,
            dataset=ds,
            recursive=recursive,
            recursion_limit=recursion_limit)
        # dataset arg was tested before, only existing dataset should be reported
        assert(not unavailable_paths)

        # anal verification
        assert(ds is not None and sshurl is not None and ds.repo is not None)

        if since:
            mod_subs = []
            content_by_ds = filter_unmodified(content_by_ds, ds, since)
            # look for those subdatasets that are listed as modified
            # together with a .gitmodules change
            for d, paths in content_by_ds.items():
                if any(p.endswith('.gitmodules') for p in paths):
                    mod_subs.extend(p for p in paths if p in content_by_ds)
            content_by_ds = mod_subs

        # dataset instances
        datasets = {p: Dataset(p) for p in content_by_ds}

        # make sure dependencies are valid
        for d in datasets.values():
            _check_deps(d.repo, publish_depends)

        # find datasets with existing remotes with the target name
        remote_existing = [p for p in datasets
                           if name in datasets[p].repo.get_remotes()]

        if existing == 'error' and remote_existing:
            raise ValueError(
                "sibling '{name}' already configured for dataset{plural}: "
                "{existing}. Specify alternative sibling name, or force "
                "reconfiguration via --existing".format(
                    name=name,
                    existing=remote_existing,
                    plural='s' if len(remote_existing) > 1 else ''))
        if existing == 'skip':
            # no need to process already configured datasets
            lgr.info(
                "Skipping dataset{plural} with an already configured "
                "sibling '{name}': {existing}".format(
                    name=name,
                    existing=remote_existing,
                    plural='s' if len(remote_existing) > 1 else ''))
            datasets = {p: d for p, d in datasets.items()
                        if p not in remote_existing}

        if not datasets:
            # we ruled out all possibilities
            # TODO wait for gh-1218 and make better return values
            lgr.info("No datasets qualify for sibling creation. "
                     "Consider different settings for --existing "
                     "or --since if this is unexpected")
            return

        if target_dir is None:
            if sshri.path:
                target_dir = sshri.path
            else:
                target_dir = '.'

        # TODO: centralize and generalize template symbol handling
        replicate_local_structure = False
        if "%RELNAME" not in target_dir:
            replicate_local_structure = True

        # request ssh connection:
        lgr.info("Connecting ...")
        ssh = ssh_manager.get_connection(sshurl)
        ssh.open()
        remote_git_version = CreateSibling.get_remote_git_version(ssh)

        # loop over all datasets, ordered from top to bottom to make test
        # below valid (existing directories would cause the machinery to halt)
        # But we need to run post-update hook in depth-first fashion, so
        # would only collect first and then run (see gh #790)
        remote_repos_to_run_hook_for = []
        for current_dspath in \
                sorted(datasets.keys(), key=lambda x: x.count('/')):
            current_ds = datasets[current_dspath]
            path = _create_dataset_sibling(
                name,
                current_ds,
                ds.path,
                ssh,
                replicate_local_structure,
                sshri,
                target_dir,
                target_url,
                target_pushurl,
                existing,
                shared,
                remote_git_version,
                publish_depends,
                publish_by_default,
                as_common_datasrc)
            if not path:
                # nothing new was created
                continue
            remote_repos_to_run_hook_for.append(path)

            # publish web-interface to root dataset on publication server
            if current_dspath == ds.path and ui:
                lgr.info("Uploading web interface to %s" % path)
                try:
                    CreateSibling.upload_web_interface(path, ssh, shared, ui)
                except CommandError as e:
                    lgr.error("Failed to push web interface to the remote "
                              "datalad repository.\nError: %s" % exc_str(e))

        # in reverse order would be depth first
        lgr.debug("Running post-update hooks in all created siblings")
        for path in remote_repos_to_run_hook_for[::-1]:
            # Trigger the hook
            try:
                ssh("cd {} && hooks/post-update".format(
                    sh_quote(_path_(path, ".git")))
                )
            except CommandError as e:
                lgr.error("Failed to run post-update hook under path %s. "
                          "Error: %s" % (path, exc_str(e)))

        # TODO: Return value!?
        #       => [(Dataset, fetch_url)]

    @staticmethod
    def init_remote_repo(path, ssh, shared, dataset, description=None):
        cmd = "git -C {} init{}".format(
            sh_quote(path),
            " --shared='{}'".format(sh_quote(shared)) if shared else '')
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
                    "git -C {} annex init {}".format(
                        sh_quote(path),
                        sh_quote(description)
                        if description else '')
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
            out, err = ssh("git version")
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

        with make_tempfile(content=hook_content) as tempf:
            # create post_update hook script
            # upload hook to dataset
            ssh.copy(tempf, hook_remote_target)
        # and make it executable
        ssh('chmod +x {}'.format(sh_quote(hook_remote_target)))

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
        ssh('mkdir -p {}'.format(sh_quote(webresources_remote)))
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
            ssh('chmod {} -R {} {}'.format(
                mode,
                sh_quote(dirname(webresources_remote)),
                sh_quote(opj(path, 'index.html'))))
