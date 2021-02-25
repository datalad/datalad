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
import os
from os.path import (
    curdir,
    dirname,
    join as opj,
    normpath,
    relpath,
)

import datalad
from datalad import ssh_manager

from datalad.ui import ui

from datalad.cmd import (
    CommandError,
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.consts import (
    TIMESTAMP_FMT,
    WEB_HTML_DIR,
    WEB_META_LOG
)
from datalad.dochelpers import exc_str
from datalad.distribution.siblings import (
    _DelayedSuper,
    Siblings,
)
from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
    EnsureDataset,
    resolve_path,
    require_dataset,
)
from datalad.interface.base import (
    build_doc,
    Interface,
)
from datalad.interface.utils import eval_results
from datalad.interface.common_opts import (
    annex_group_opt,
    annex_groupwanted_opt,
    annex_wanted_opt,
    as_common_datasrc,
    inherit_opt,
    publish_by_default,
    publish_depends,
    recursion_flag,
    recursion_limit,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    MissingExternalDependency,
)
from datalad.support.external_versions import external_versions
from datalad.support.network import (
    is_ssh,
    PathRI,
    RI,
)
from datalad.support.sshconnector import sh_quote
from datalad.support.param import Parameter
from datalad.utils import (
    make_tempfile,
    _path_,
    slash_join,
    ensure_list,
)
from datalad.core.local.diff import diff_dataset

from datalad.utils import on_windows

lgr = logging.getLogger('datalad.distribution.create_sibling')
# Window's own mkdir command creates intermediate directories by default
# and does not take flags: https://github.com/datalad/datalad/issues/5211
mkdir_cmd = "mkdir" if on_windows else "mkdir -p" 


class _RunnerAdapter(WitlessRunner):
    """An adapter to use interchanegably with SSH connection"""

    def __call__(self, cmd):
        out = self.run(cmd, protocol=StdOutErrCapture)
        return out['stdout'], out['stderr']

    def get_git_version(self):
        return external_versions['cmd:git']

    def get_annex_version(self):
        return external_versions['cmd:annex']

    def put(self, source, destination, recursive=False,
            preserve_attrs=False):
        import shutil
        copy_fn = shutil.copy2 if preserve_attrs else shutil.copy
        if recursive:
            args = [source, destination]
            kwargs = {"copy_function": copy_fn}
            try:
                shutil.copytree(*args, **kwargs)
            except FileExistsError:
                # SSHConnection.put() is okay with copying a tree if the
                # destination directory already exists. With Python 3.8, we can
                # make copytree() do the same with dirs_exist_ok=True. But for
                # now, just rely on `cp`.
                cmd = ["cp", "-R"]
                if preserve_attrs:
                    cmd.append("-p")
                self(cmd + args)
        else:
            copy_fn(source, destination)


def _create_dataset_sibling(
        name,
        ds,
        hierarchy_basepath,
        shell,
        replicate_local_structure,
        ri,
        target_dir,
        target_url,
        target_pushurl,
        existing,
        shared,
        group,
        publish_depends,
        publish_by_default,
        install_postupdate_hook,
        as_common_datasrc,
        annex_wanted,
        annex_group,
        annex_groupwanted,
        inherit
):
    """Everyone is very smart here and could figure out the combinatorial
    affluence among provided tiny (just slightly over a dozen) number of options
    and only a few pages of code
    """
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

    ds_repo = ds.repo
    # construct a would-be ssh url based on the current dataset's path
    ri.path = remoteds_path
    ds_url = ri.as_str()
    # configure dataset's git-access urls
    ds_target_url = target_url.replace('%RELNAME', ds_name) \
        if target_url else ds_url
    # push, configure only if needed
    ds_target_pushurl = None
    if ds_target_url != ds_url:
        # not guaranteed that we can push via the primary URL
        ds_target_pushurl = target_pushurl.replace('%RELNAME', ds_name) \
            if target_pushurl else ds_url

    lgr.info("Considering to create a target dataset {0} at {1} of {2}".format(
        localds_path, remoteds_path,
        "localhost" if isinstance(ri, PathRI) else ri.hostname))
    # Must be set to True only if exists and existing='reconfigure'
    # otherwise we might skip actions if we say existing='reconfigure'
    # but it did not even exist before
    only_reconfigure = False
    if remoteds_path != '.':
        # check if target exists
        # TODO: Is this condition valid for != '.' only?
        path_children = _ls_remote_path(shell, remoteds_path)
        path_exists = path_children is not None

        if path_exists:
            _msg = "Target path %s already exists." % remoteds_path
        if path_exists and not path_children:
            # path should be an empty directory, which should be ok to remove
            try:
                lgr.debug(
                    "Trying to rmdir %s on remote since seems to be an empty dir",
                    remoteds_path
                )
                # should be safe since should not remove anything unless an empty dir
                shell("rmdir {}".format(sh_quote(remoteds_path)))
                path_exists = False
            except CommandError as e:
                # If fails to rmdir -- either contains stuff no permissions
                # TODO: fixup encode/decode dance again :-/ we should have got
                # unicode/str here by now.  I guess it is the same as
                # https://github.com/ReproNim/niceman/issues/83
                # where I have reused this Runner thing
                try:
                    # ds_name is unicode which makes _msg unicode so we must be
                    # unicode-ready
                    err_str = str(e.stderr)
                except UnicodeDecodeError:
                    err_str = e.stderr.decode(errors='replace')
                _msg += " And it fails to rmdir (%s)." % (err_str.strip(),)

        if path_exists:
            if existing == 'error':
                raise RuntimeError(_msg)
            elif existing == 'skip':
                lgr.info(_msg + " Skipping")
                return
            elif existing == 'replace':
                remove = False
                if path_children:
                    has_git = '.git' in path_children
                    _msg_stats = _msg \
                                 + " It is %sa git repository and has %d files/dirs." % (
                                     "" if has_git else "not ", len(path_children)
                                 )
                    if ui.is_interactive:
                        remove = ui.yesno(
                            "Do you really want to remove it?",
                            title=_msg_stats,
                            default=False
                        )
                    else:
                        raise RuntimeError(
                            _msg_stats +
                            " Remove it manually first or rerun datalad in "
                            "interactive shell to confirm this action.")
                if not remove:
                    raise RuntimeError(_msg)
                # Remote location might already contain a git repository or be
                # just a directory.
                lgr.info(_msg + " Replacing")
                # enable write permissions to allow removing dir
                shell("chmod -R +r+w {}".format(sh_quote(remoteds_path)))
                # remove target at path
                shell("rm -rf {}".format(sh_quote(remoteds_path)))
                # if we succeeded in removing it
                path_exists = False
                # Since it is gone now, git-annex also should forget about it
                remotes = ds_repo.get_remotes()
                if name in remotes:
                    # so we had this remote already, we should announce it dead
                    # XXX what if there was some kind of mismatch and this name
                    # isn't matching the actual remote UUID?  should have we
                    # checked more carefully?
                    lgr.info(
                        "Announcing existing remote %s dead to annex and removing",
                        name
                    )
                    if isinstance(ds_repo, AnnexRepo):
                        ds_repo.set_remote_dead(name)
                    ds_repo.remove_remote(name)
            elif existing == 'reconfigure':
                lgr.info(_msg + " Will only reconfigure")
                only_reconfigure = True
            else:
                raise ValueError(
                    "Do not know how to handle existing={}".format(
                        repr(existing)))
        if not path_exists:
            shell("{} {}".format(mkdir_cmd, sh_quote(remoteds_path)))

    delayed_super = _DelayedSuper(ds)
    if inherit and delayed_super.super:
        if shared is None:
            # here we must analyze current_ds's super, not the super_ds
            # inherit from the setting on remote end
            shared = CreateSibling._get_ds_remote_shared_setting(
                delayed_super, name, shell)

        if not install_postupdate_hook:
            # Even though directive from above was False due to no UI explicitly
            # requested, we were asked to inherit the setup, so we might need
            # to install the hook, if super has it on remote
            install_postupdate_hook = CreateSibling._has_active_postupdate(
                delayed_super, name, shell)



    if group:
        # Either repository existed before or a new directory was created for it,
        # set its group to a desired one if was provided with the same chgrp
        shell("chgrp -R {} {}".format(
            sh_quote(str(group)),
            sh_quote(remoteds_path)))
    # don't (re-)initialize dataset if existing == reconfigure
    if not only_reconfigure:
        # init git and possibly annex repo
        if not CreateSibling.init_remote_repo(
                remoteds_path, shell, shared, ds,
                description=target_url):
            return

        if target_url and not is_ssh(target_url):
            # we are not coming in via SSH, hence cannot assume proper
            # setup for webserver access -> fix
            shell('git -C {} update-server-info'.format(sh_quote(remoteds_path)))
    else:
        # TODO -- we might still want to reconfigure 'shared' setting!
        pass

    # at this point we have a remote sibling in some shape or form
    # -> add as remote
    lgr.debug("Adding the siblings")
    # TODO generator, yield the now swallowed results
    Siblings.__call__(
        'configure',
        dataset=ds,
        name=name,
        url=ds_target_url,
        pushurl=ds_target_pushurl,
        recursive=False,
        fetch=True,
        as_common_datasrc=as_common_datasrc,
        publish_by_default=publish_by_default,
        publish_depends=publish_depends,
        annex_wanted=annex_wanted,
        annex_group=annex_group,
        annex_groupwanted=annex_groupwanted,
        inherit=inherit,
        result_renderer=None,
    )

    # check git version on remote end
    lgr.info("Adjusting remote git configuration")
    if shell.get_git_version() and shell.get_git_version() >= LooseVersion("2.4"):
        # allow for pushing to checked out branch
        try:
            shell("git -C {} config receive.denyCurrentBranch updateInstead".format(
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
                  " and run with --existing=reconfigure",
                  shell.get_git_version())

    branch = ds_repo.get_active_branch()
    if branch is not None:
        branch = ds_repo.get_corresponding_branch(branch) or branch
        # Setting the HEAD for the created sibling to the original repo's
        # current branch should be unsurprising, and it helps with consumers
        # that don't properly handle the default branch with no commits. See
        # gh-4349.
        shell("git -C {} symbolic-ref HEAD refs/heads/{}"
              .format(sh_quote(remoteds_path), branch))

    if install_postupdate_hook:
        # enable metadata refresh on dataset updates to publication server
        lgr.info("Enabling git post-update hook ...")
        try:
            CreateSibling.create_postupdate_hook(
                remoteds_path, shell, ds)
        except CommandError as e:
            lgr.error("Failed to add json creation command to post update "
                      "hook.\nError: %s" % exc_str(e))

    return remoteds_path


def _ls_remote_path(ssh, path):
    try:
        # yoh tried ls on mac
        out, err = ssh("ls -A1 {}".format(sh_quote(path)))
        if err:
            # we might even want to raise an exception, but since it was
            # not raised, let's just log a warning
            lgr.warning(
                "There was some output to stderr while running ls on %s via ssh: %s",
                path, err
            )
    except CommandError as e:
        if "No such file or directory" in e.stderr and \
                path in e.stderr:
            return None
        else:
            raise  # It's an unexpected failure here
    return [l for l in out.split(os.linesep) if l]


@build_doc
class CreateSibling(Interface):
    """Create a dataset sibling on a UNIX-like Shell (local or SSH)-accessible machine

    Given a local dataset, and a path or SSH login information this command
    creates a remote dataset repository and configures it as a dataset sibling
    to be used as a publication target (see `publish` command).

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
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

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
            nargs='?',
            doc="""Login information for the target server. This can be given
                as a URL (ssh://host/path), SSH-style (user@host:path) or just
                a local path.
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
                shall be created. By default this is set to the URL (or local
                path) specified via [PY: `sshurl` PY][CMD: SSHURL CMD]. If a
                relative path is provided here, it is interpreted as being
                relative to the user's home directory on the server (or
                relative to [PY: `sshurl` PY][CMD: SSHURL CMD], when that is a
                local path).
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
            constraints=EnsureChoice('skip', 'error', 'reconfigure', 'replace'),
            metavar='MODE',
            doc="""action to perform, if a sibling is already configured under the
            given name and/or a target (non-empty) directory already exists.
            In this case, a dataset can be skipped ('skip'), the sibling
            configuration be updated ('reconfigure'), or process interrupts with
            error ('error'). DANGER ZONE: If 'replace' is used, an existing target
            directory will be forcefully removed, re-initialized, and the
            sibling (re-)configured (thus implies 'reconfigure').
            `replace` could lead to data loss, so use with care.  To minimize
            possibility of data loss, in interactive mode DataLad will ask for
            confirmation, but it would raise an exception in non-interactive mode.
            """,),
        inherit=inherit_opt,
        shared=Parameter(
            args=("--shared",),
            metavar='{false|true|umask|group|all|world|everybody|0xxx}',
            doc="""if given, configures the access permissions on the server
            for multi-users (this could include access by a webserver!).
            Possible values for this option are identical to those of
            `git init --shared` and are described in its documentation.""",
            constraints=EnsureStr() | EnsureBool() | EnsureNone()),
        group=Parameter(
            args=("--group",),
            metavar="GROUP",
            doc="""Filesystem group for the repository. Specifying the group is
            particularly important when [CMD: --shared=group CMD][PY:
            shared="group" PY]""",
            constraints=EnsureStr() | EnsureNone()
        ),
        ui=Parameter(
            args=("--ui",),
            metavar='{false|true|html_filename}',
            doc="""publish a web interface for the dataset with an
            optional user-specified name for the html at publication
            target. defaults to `index.html` at dataset root""",
            constraints=EnsureBool() | EnsureStr()),
        as_common_datasrc=as_common_datasrc,
        publish_depends=publish_depends,
        publish_by_default=publish_by_default,
        annex_wanted=annex_wanted_opt,
        annex_group=annex_group_opt,
        annex_groupwanted=annex_groupwanted_opt,
        since=Parameter(
            args=("--since",),
            constraints=EnsureStr() | EnsureNone(),
            doc="""limit processing to datasets that have been changed since a given
            state (by tag, branch, commit, etc). This can be used to create siblings
            for recently added subdatasets."""),
    )

    @staticmethod
    @datasetmethod(name='create_sibling')
    @eval_results
    def __call__(sshurl, name=None, target_dir=None,
                 target_url=None, target_pushurl=None,
                 dataset=None,
                 recursive=False,
                 recursion_limit=None,
                 existing='error',
                 shared=None,
                 group=None,
                 ui=False,
                 as_common_datasrc=None,
                 publish_by_default=None,
                 publish_depends=None,
                 annex_wanted=None, annex_group=None, annex_groupwanted=None,
                 inherit=False,
                 since=None):
        #
        # nothing without a base dataset
        #
        ds = require_dataset(dataset, check_installed=True,
                             purpose='creating a sibling')
        refds_path = ds.path

        #
        # all checks that are possible before we start parsing the dataset
        #

        # possibly use sshurl to get the name in case if not specified
        if not sshurl:
            if not inherit:
                raise InsufficientArgumentsError(
                    "needs at least an SSH URL, if no inherit option"
                )
            if name is None:
                raise ValueError(
                    "Neither SSH URL, nor the name of sibling to inherit from "
                    "was specified"
                )
            # It might well be that we already have this remote setup
            try:
                sshurl = CreateSibling._get_remote_url(ds, name)
            except Exception as exc:
                lgr.debug('%s does not know about url for %s: %s', ds, name, exc_str(exc))
        elif inherit:
            raise ValueError(
                "For now, for clarity not allowing specifying a custom sshurl "
                "while inheriting settings"
            )
            # may be could be safely dropped -- still WiP

        if not sshurl:
            # TODO: may be more back up before _prep?
            super_ds = ds.get_superdataset()
            if not super_ds:
                raise ValueError(
                    "Could not determine super dataset for %s to inherit URL"
                    % ds
                )
            super_url = CreateSibling._get_remote_url(super_ds, name)
            # for now assuming hierarchical setup
            # (TODO: to be able to destinguish between the two, probably
            # needs storing datalad.*.target_dir to have %RELNAME in there)
            sshurl = slash_join(super_url, relpath(refds_path, super_ds.path))

        # check the login URL
        sibling_ri = RI(sshurl)
        ssh_sibling = is_ssh(sibling_ri)
        if not (ssh_sibling or isinstance(sibling_ri, PathRI)):
            raise ValueError(
                "Unsupported SSH URL or path: '{0}', "
                "use ssh://host/path, host:path or path syntax".format(sshurl))

        if not name:
            name = sibling_ri.hostname if ssh_sibling else "local"
            lgr.debug(
                "No sibling name given. Using %s'%s' as sibling name",
                "URL hostname " if ssh_sibling else "",
                name)
        if since == '':
            # consider creating siblings only since the point of
            # the last update
            # XXX here we assume one to one mapping of names from local branches
            # to the remote
            active_branch = ds.repo.get_active_branch()
            since = '%s/%s' % (name, active_branch)

        #
        # parse the base dataset to find all subdatasets that need processing
        #
        to_process = []
        cand_ds = [
            Dataset(r['path'])
            for r in diff_dataset(
                ds,
                fr=since,
                to=None,
                # make explicit, but doesn't matter, no recursion in diff()
                constant_refs=True,
                # contrain to the paths of all locally existing subdatasets
                path=[
                    sds['path']
                    for sds in ds.subdatasets(
                        recursive=recursive,
                        recursion_limit=recursion_limit,
                        fulfilled=True,
                        result_renderer=None)
                ],
                # save cycles, we are only looking for datasets
                annex=None,
                untracked='no',
                # recursion was done faster by subdatasets()
                recursive=False,
                # save cycles, we are only looking for datasets
                eval_file_type=False,
            )
            if r.get('type') == 'dataset' and r.get('state', None) != 'clean'
        ]
        # check remotes setup
        for d in cand_ds if since else ([ds] + cand_ds):
            d_repo = d.repo
            if d_repo is None:
                continue
            checkds_remotes = d.repo.get_remotes()
            res = dict(
                action='create_sibling',
                path=d.path,
                type='dataset',
            )

            if publish_depends:
                # make sure dependencies are valid
                # TODO: inherit -- we might want to automagically create
                # those dependents as well???
                unknown_deps = set(ensure_list(publish_depends)).difference(
                    checkds_remotes)
                if unknown_deps:
                    yield dict(
                        res,
                        status='error',
                        message=('unknown sibling(s) specified as publication '
                                 'dependency: %s', unknown_deps),
                    )
                    continue
            if name in checkds_remotes and existing in ('error', 'skip'):
                yield dict(
                    res,
                    status='error' if existing == 'error' else 'notneeded',
                    message=(
                        "sibling '%s' already configured (specify alternative "
                        "name, or force reconfiguration via --existing", name),
                )
                continue
            to_process.append(res)

        if not to_process:
            # we ruled out all possibilities
            # TODO wait for gh-1218 and make better return values
            lgr.info("No datasets qualify for sibling creation. "
                     "Consider different settings for --existing "
                     "or --since if this is unexpected")
            return

        if ssh_sibling:
            # request ssh connection:
            lgr.info("Connecting ...")
            shell = ssh_manager.get_connection(sshurl)
        else:
            shell = _RunnerAdapter()
            sibling_ri.path = str(resolve_path(sibling_ri.path, dataset))
            if target_dir:
                target_dir = opj(sibling_ri.path, target_dir)

        if target_dir is None:
            if sibling_ri.path:
                target_dir = sibling_ri.path
            else:
                target_dir = '.'

        # TODO: centralize and generalize template symbol handling
        replicate_local_structure = "%RELNAME" not in target_dir

        if not shell.get_annex_version():
            raise MissingExternalDependency(
                'git-annex',
                msg="It's required on the {} machine to create a sibling"
                    .format('remote' if ssh_sibling else 'local'))

        #
        # all checks done and we have a connection, now do something
        #

        # loop over all datasets, ordered from top to bottom to make test
        # below valid (existing directories would cause the machinery to halt)
        # But we need to run post-update hook in depth-first fashion, so
        # would only collect first and then run (see gh #790)
        yielded = set()
        remote_repos_to_run_hook_for = []
        for currentds_ap in \
                sorted(to_process, key=lambda x: x['path'].count('/')):
            current_ds = Dataset(currentds_ap['path'])

            path = _create_dataset_sibling(
                name,
                current_ds,
                refds_path,
                shell,
                replicate_local_structure,
                sibling_ri,
                target_dir,
                target_url,
                target_pushurl,
                existing,
                shared,
                group,
                publish_depends,
                publish_by_default,
                ui,
                as_common_datasrc,
                annex_wanted,
                annex_group,
                annex_groupwanted,
                inherit
            )
            if not path:
                # nothing new was created
                # TODO is 'notneeded' appropriate in this case?
                currentds_ap['status'] = 'notneeded'
                # TODO explain status in 'message'
                yield currentds_ap
                yielded.add(currentds_ap['path'])
                continue
            remote_repos_to_run_hook_for.append((path, currentds_ap))

            # publish web-interface to root dataset on publication server
            if current_ds.path == refds_path and ui:
                lgr.info("Uploading web interface to %s" % path)
                try:
                    CreateSibling.upload_web_interface(path, shell, shared, ui)
                except CommandError as e:
                    currentds_ap['status'] = 'error'
                    currentds_ap['message'] = (
                        "failed to push web interface to the remote datalad repository (%s)",
                        exc_str(e))
                    yield currentds_ap
                    yielded.add(currentds_ap['path'])
                    continue

        # in reverse order would be depth first
        lgr.info("Running post-update hooks in all created siblings")
        # TODO: add progressbar
        for path, currentds_ap in remote_repos_to_run_hook_for[::-1]:
            # Trigger the hook
            lgr.debug("Running hook for %s (if exists and executable)", path)
            try:
                shell("cd {} "
                      "&& ( [ -x hooks/post-update ] && hooks/post-update || true )"
                      "".format(sh_quote(_path_(path, ".git"))))
            except CommandError as e:
                currentds_ap['status'] = 'error'
                currentds_ap['message'] = (
                    "failed to run post-update hook under remote path %s (%s)",
                    path, exc_str(e))
                yield currentds_ap
                yielded.add(currentds_ap['path'])
                continue
            if not currentds_ap['path'] in yielded:
                # if we were silent until now everything is just splendid
                currentds_ap['status'] = 'ok'
                yield currentds_ap

    @staticmethod
    def _run_on_ds_ssh_remote(ds, name, ssh, cmd):
        """Given a dataset, and name of the remote, run command via ssh

        Parameters
        ----------
        cmd: str
          Will be .format()'ed given the `path` to the dataset on remote

        Returns
        -------
        out

        Raises
        ------
        CommandError
        """
        remote_url = CreateSibling._get_remote_url(ds, name)
        remote_ri = RI(remote_url)
        out, err = ssh(cmd.format(path=sh_quote(remote_ri.path)))
        if err:
            lgr.warning("Got stderr while calling ssh: %s", err)
        return out

    @staticmethod
    def _get_ds_remote_shared_setting(ds, name, ssh):
        """Figure out setting of sharedrepository for dataset's `name` remote"""
        shared = None
        try:
            # TODO -- we might need to expanduser taking .user into account
            # but then it must be done also on remote side
            out = CreateSibling._run_on_ds_ssh_remote(
                ds, name, ssh,
                'git -C {path} config --get core.sharedrepository'
            )
            shared = out.strip()
        except CommandError as e:
            lgr.debug(
                "Could not figure out remote shared setting of %s for %s due "
                "to %s",
                ds, name, exc_str(e)
            )
            # could well be ok if e.g. not shared
            # TODO: more detailed analysis may be?
        return shared

    @staticmethod
    def _has_active_postupdate(ds, name, ssh):
        """Figure out either has active post-update hook

        Returns
        -------
        bool or None
          None if something went wrong and we could not figure out
        """
        has_active_post_update = None
        try:
            # TODO -- we might need to expanduser taking .user into account
            # but then it must be done also on remote side
            out = CreateSibling._run_on_ds_ssh_remote(
                ds, name, ssh,
                'cd {path} && [ -x .git/hooks/post-update ] && echo yes || echo no'
            )
            out = out.strip()
            assert out in ('yes', 'no')
            has_active_post_update = out == "yes"
        except CommandError as e:
            lgr.debug(
                "Could not figure out either %s on remote %s has active "
                "post_update hook due to %s",
                ds, name, exc_str(e)
            )
        return has_active_post_update

    @staticmethod
    def _get_remote_url(ds, name):
        """A little helper to get url from pushurl or from url if not defined"""
        # take pushurl if present, if not -- just a url
        url = ds.config.get('remote.%s.pushurl' % name) or \
            ds.config.get('remote.%s.url' % name)
        if not url:
            raise ValueError(
                "%s had neither pushurl or url defined for %s" % (ds, name)
            )
        return url

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
    def create_postupdate_hook(path, ssh, dataset):
        # location of post-update hook file, logs folder on remote target
        hooks_remote_dir = opj(path, '.git', 'hooks')
        # make sure hooks directory exists (see #1251)
        ssh('{} {}'.format(mkdir_cmd, sh_quote(hooks_remote_dir)))
        hook_remote_target = opj(hooks_remote_dir, 'post-update')

        # create json command for current dataset
        log_filename = 'datalad-publish-hook-$(date +%s).log' % TIMESTAMP_FMT
        hook_content = r'''#!/bin/bash

git update-server-info

#
# DataLad
#
# (Re)generate meta-data for DataLad Web UI and possibly init new submodules
dsdir="$(dirname $0)/../.."
logfile="$dsdir/{WEB_META_LOG}/{log_filename}"

if [ ! -e "$dsdir/.git" ]; then
  echo Assumption of being under .git has failed >&2
  exit 1
fi

mkdir -p "$dsdir/{WEB_META_LOG}"  # assure logs directory exists

# Avoid file name collisions.
suffix=0
logfile_orig="$logfile"
while [ -f "$logfile" ]; do
  suffix=$(( $suffix + 1 ))
  logfile="$logfile_orig.$suffix"
done

( which datalad > /dev/null \
  && ( cd "$dsdir"; GIT_DIR="$PWD/.git" datalad ls -a --json file .; ) \
  || echo "E: no datalad found - skipping generation of indexes for web frontend"; \
) &> "$logfile"
'''.format(WEB_META_LOG=WEB_META_LOG, **locals())

        with make_tempfile(content=hook_content) as tempf:
            # create post_update hook script
            # upload hook to dataset
            ssh.put(tempf, hook_remote_target)
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
        ssh.put(html_local, html_target)

        # upload assets to the dataset
        webresources_local = opj(webui_local, 'assets')
        webresources_remote = opj(path, WEB_HTML_DIR)
        ssh('{} {}'.format(mkdir_cmd, sh_quote(webresources_remote)))
        ssh.put(webresources_local, webresources_remote, recursive=True)

        # minimize and upload js assets
        for js_file in glob(opj(webresources_local, 'js', '*.js')):
            with open(js_file) as asset:
                try:
                    from jsmin import jsmin
                    # jsmin = lambda x: x   # no minimization
                    minified = jsmin(asset.read())                      # minify asset
                except ImportError:
                    lgr.warning(
                        "Will not minify web interface javascript, no jsmin available")
                    minified = asset.read()                             # no minify available
                with make_tempfile(content=minified) as tempf:          # write minified to tempfile
                    js_name = js_file.split('/')[-1]
                    ssh.put(tempf, opj(webresources_remote, 'assets', 'js', js_name))  # and upload js

        # explicitly make web+metadata dir of dataset world-readable, if shared set to 'all'
        mode = None
        if shared in (True, 'true', 'all', 'world', 'everybody'):
            mode = 'a+rX'
        elif shared == 'group':
            mode = 'g+rX'
        elif str(shared).startswith('0'):
            mode = shared

        if mode:
            ssh('chmod -R {} {} {}'.format(
                mode,
                sh_quote(dirname(webresources_remote)),
                sh_quote(opj(path, 'index.html'))))
