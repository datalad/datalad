# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Create a sibling in a RIA store"""

__docformat__ = 'restructuredtext'


import logging

from datalad.cmd import WitlessRunner as Runner
from datalad.interface.common_opts import (
    recursion_flag,
    recursion_limit
)
from datalad.interface.base import (
    build_doc,
    Interface,
)
from datalad.interface.results import (
    get_status_dict,
)
from datalad.interface.utils import eval_results
from datalad.support.annexrepo import AnnexRepo
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.distribution.dataset import (
    datasetmethod,
    EnsureDataset,
    require_dataset,
)
from datalad.distribution.utils import _yield_ds_w_matching_siblings
from datalad.distributed.ora_remote import (
    LocalIO,
    RIARemoteError,
    RemoteCommandFailedError,
    SSHRemoteIO,
)
from datalad.utils import (
    Path,
    quote_cmdlinearg,
)
from datalad.support.exceptions import (
    CommandError
)
from datalad.support.gitrepo import (
    GitRepo
)
from datalad.core.distributed.clone import (
    decode_source_spec
)
from datalad.log import log_progress
from datalad.customremotes.ria_utils import (
    get_layout_locations,
    verify_ria_url,
    create_store,
    create_ds_in_store
)

lgr = logging.getLogger('datalad.distributed.create_sibling_ria')


@build_doc
class CreateSiblingRia(Interface):
    """Creates a sibling to a dataset in a RIA store

    Communication with a dataset in a RIA store is implemented via two
    siblings. A regular Git remote (repository sibling) and a git-annex
    special remote for data transfer (storage sibling) -- with the former
    having a publication dependency on the latter. By default, the name of the
    storage sibling is derived from the repository sibling's name by appending
    "-storage".

    The store's base path is expected to not exist, be an empty directory,
    or a valid RIA store.

    RIA store layout
    ~~~~~~~~~~~~~~~~

    A RIA store is a directory tree with a dedicated subdirectory for each
    dataset in the store. The subdirectory name is constructed from the
    DataLad dataset ID, e.g. '124/68afe-59ec-11ea-93d7-f0d5bf7b5561', where
    the first three characters of the ID are used for an intermediate
    subdirectory in order to mitigate files system limitations for stores
    containing a large number of datasets.

    Each dataset subdirectory contains a standard bare Git repository for
    the dataset.

    In addition, a subdirectory 'annex' hold a standard Git-annex object
    store. However, instead of using the 'dirhashlower' naming scheme for
    the object directories, like Git-annex would do, a 'dirhashmixed'
    layout is used -- the same as for non-bare Git repositories or regular
    DataLad datasets.

    Optionally, there can be a further subdirectory 'archives' with
    (compressed) 7z archives of annex objects. The storage remote is able to
    pull annex objects from these archives, if it cannot find in the regular
    annex object store. This feature can be useful for storing large
    collections of rarely changing data on systems that limit the number of
    files that can be stored.

    Each dataset directory also contains a 'ria-layout-version' file that
    identifies the data organization (as, for example, described above).

    Lastly, there is a global 'ria-layout-version' file at the store's
    base path that identifies where dataset subdirectories themselves are
    located. At present, this file must contain a single line stating the
    version (currently "1"). This line MUST end with a newline character.

    It is possible to define an alias for an individual dataset in a store by
    placing a symlink to the dataset location into an 'alias/' directory
    in the root of the store. This enables dataset access via URLs of format:
    'ria+<protocol>://<storelocation>#~<aliasname>'.

    Error logging
    ~~~~~~~~~~~~~

    To enable error logging at the remote end, append a pipe symbol and an "l"
    to the version number in ria-layout-version (like so '1|l\\n').

    Error logging will create files in an "error_log" directory whenever the
    git-annex special remote (storage sibling) raises an exception, storing the
    Python traceback of it. The logfiles are named according to the scheme
    '<dataset id>.<annex uuid of the remote>.log' showing "who" ran into this
    issue with which dataset. Because logging can potentially leak personal
    data (like local file paths for example), it can be disabled client-side
    by setting the configuration variable
    "annex.ora-remote.<storage-sibling-name>.ignore-remote-config".
    """

    # TODO: description?
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to process.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        url=Parameter(
            args=("url",),
            metavar="ria+<ssh|file|http(s)>://<host>[/path]",
            doc="""URL identifying the target RIA store and access protocol. If
            ``push_url||--push-url`` is given in addition, this is
            used for read access only. Otherwise it will be used for write
            access too and to create the repository sibling in the RIA store.
            Note, that HTTP(S) currently is valid for consumption only thus
            requiring to provide ``push_url||--push-url``.
            """,
            constraints=EnsureStr() | EnsureNone()),
        push_url=Parameter(
            args=("--push-url",),
            metavar="ria+<ssh|file>://<host>[/path]",
            doc="""URL identifying the target RIA store and access protocol for
            write access to the storage sibling. If given this will also be used
            for creation of the repository sibling in the RIA store.""",
            constraints=EnsureStr() | EnsureNone()),
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""Name of the sibling.
            With `recursive`, the same name will be used to label all
            the subdatasets' siblings.""",
            constraints=EnsureStr() | EnsureNone(),
            required=True),
        storage_name=Parameter(
            args=("--storage-name",),
            metavar="NAME",
            doc="""Name of the storage sibling (git-annex special remote).
            Must not be identical to the sibling name. If not specified,
            defaults to the sibling name plus '-storage' suffix. If only
            a storage sibling is created, this setting is ignored, and
            the primary sibling name is used.""",
            constraints=EnsureStr() | EnsureNone()),
        alias=Parameter(
            args=('--alias',),
            metavar='ALIAS',
            doc="""Alias for the dataset in the RIA store.
            Add the necessary symlink so that this dataset can be cloned from the RIA
            store using the given ALIAS instead of its ID.
            With `recursive=True`, only the top dataset will be aliased.""",
            constraints=EnsureStr() | EnsureNone()),
        post_update_hook=Parameter(
            args=("--post-update-hook",),
            doc="""Enable Git's default post-update-hook for the created
            sibling. This is useful when the sibling is made accessible via a
            "dumb server" that requires running 'git update-server-info'
            to let Git interact properly with it.""",
            action="store_true"),
        shared=Parameter(
            args=("--shared",),
            metavar='{false|true|umask|group|all|world|everybody|0xxx}',
            doc="""If given, configures the permissions in the
            RIA store for multi-users access.
            Possible values for this option are identical to those of
            `git init --shared` and are described in its documentation.""",
            constraints=EnsureStr() | EnsureBool() | EnsureNone()),
        group=Parameter(
            args=("--group",),
            metavar="GROUP",
            doc="""Filesystem group for the repository. Specifying the group is
            crucial when [CMD: --shared=group CMD][PY: shared="group" PY]""",
            constraints=EnsureStr() | EnsureNone()),
        storage_sibling=Parameter(
            args=("--storage-sibling",),
            dest='storage_sibling',
            metavar='MODE',
            constraints=EnsureChoice('only') | EnsureBool() | EnsureNone(),
            doc="""By default, an ORA storage sibling and a Git repository
            sibling are created ([CMD: on CMD][PY: True|'on' PY]).
            Alternatively, creation of the storage sibling can be disabled
            ([CMD: off CMD][PY: False|'off' PY]), or a storage sibling
            created only and no Git sibling
            ([CMD: only CMD][PY: 'only' PY]). In the latter mode, no Git
            installation is required on the target host."""),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice('skip', 'error', 'reconfigure'),
            metavar='MODE',
            doc="""Action to perform, if a (storage) sibling is already
            configured under the given name and/or a target already exists.
            In this case, a dataset can be skipped ('skip'), an existing target
            repository be forcefully re-initialized, and the sibling
            (re-)configured ('reconfigure'), or the command be instructed to
            fail ('error').""", ),
        new_store_ok=Parameter(
            args=("--new-store-ok",),
            action='store_true',
            doc="""When set, a new store will be created, if necessary. Otherwise, a sibling
            will only be created if the url points to an existing RIA store.""",
        ),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        trust_level=Parameter(
            args=("--trust-level",),
            metavar="TRUST-LEVEL",
            constraints=EnsureChoice('trust', 'semitrust', 'untrust', None),
            doc="""specify a trust level for the storage sibling. If not
            specified, the default git-annex trust level is used. 'trust'
            should be used with care (see the git-annex-trust man page).""",),
        disable_storage__=Parameter(
            args=("--no-storage-sibling",),
            dest='disable_storage__',
            doc="""This option is deprecated. Use '--storage-sibling off'
            instead.""",
            action="store_false"),
    )

    @staticmethod
    @datasetmethod(name='create_sibling_ria')
    @eval_results
    def __call__(url,
                 name,
                 *,  # note that `name` is required but not posarg in CLI
                 dataset=None,
                 storage_name=None,
                 alias=None,
                 post_update_hook=False,
                 shared=None,
                 group=None,
                 storage_sibling=True,
                 existing='error',
                 new_store_ok=False,
                 trust_level=None,
                 recursive=False,
                 recursion_limit=None,
                 disable_storage__=None,
                 push_url=None
                 ):
        if disable_storage__ is not None:
            import warnings
            warnings.warn("datalad-create-sibling-ria --no-storage-sibling "
                          "is deprecated, use --storage-sibling off instead.",
                          DeprecationWarning)
            # recode to new setup
            disable_storage__ = None
            storage_sibling = False

        if storage_sibling == 'only' and storage_name:
            lgr.warning(
                "Sibling name will be used for storage sibling in "
                "storage-sibling-only mode, but a storage sibling name "
                "was provided"
            )

        ds = require_dataset(
            dataset, check_installed=True, purpose='create RIA sibling(s)')
        res_kwargs = dict(
            ds=ds,
            action="create-sibling-ria",
            logger=lgr,
        )

        # parse target URL
        # Note: URL parsing is done twice ATM (for top-level ds). This can't be
        # reduced to single instance, since rewriting url based on config could
        # be different for subdatasets.
        try:
            ssh_host, base_path, rewritten_url = \
                verify_ria_url(push_url if push_url else url, ds.config)
        except ValueError as e:
            yield get_status_dict(
                status='error',
                message=str(e),
                **res_kwargs
            )
            return

        if ds.repo.get_hexsha() is None or ds.id is None:
            raise RuntimeError(
                "Repository at {} is not a DataLad dataset, "
                "run 'datalad create [--force]' first.".format(ds.path))

        if not storage_sibling and storage_name:
            lgr.warning(
                "Storage sibling setup disabled, but a storage sibling name "
                "was provided"
            )

        if storage_sibling and not storage_name:
            storage_name = "{}-storage".format(name)

        if storage_sibling and name == storage_name:
            # leads to unresolvable, circular dependency with publish-depends
            raise ValueError("sibling names must not be equal")

        if not isinstance(url, str):
            raise TypeError("url is not a string, but %s" % type(url))

        # Query existing siblings upfront in order to fail early on
        # existing=='error', since misconfiguration (particularly of special
        # remotes) only to fail in a subdataset later on with that config, can
        # be quite painful.
        # TODO: messages - this is "create-sibling". Don't confuse existence of
        #       local remotes with existence of the actual remote sibling
        #       in wording
        if existing == 'error':
            failed = False
            for dpath, sname in _yield_ds_w_matching_siblings(
                    ds,
                    (name, storage_name),
                    recursive=recursive,
                    recursion_limit=recursion_limit):
                res = get_status_dict(
                    status='error',
                    message=(
                        "a sibling %r is already configured in dataset %r",
                        sname, dpath),
                    type='sibling',
                    name=sname,
                    **res_kwargs,
                )
                failed = True
                yield res
            if failed:
                return
        # TODO: - URL parsing + store creation needs to be RF'ed based on
        #         command abstractions
        #       - more generally consider store creation a dedicated command or
        #         option

        io = SSHRemoteIO(ssh_host) if ssh_host else LocalIO()
        try:
            # determine the existence of a store by trying to read its layout.
            # Because this raises a FileNotFound error if non-existent, we need
            # to catch it
            io.read_file(Path(base_path) / 'ria-layout-version')
        except (FileNotFoundError, RIARemoteError, RemoteCommandFailedError) as e:
            if not new_store_ok:
                # we're instructed to only act in case of an existing RIA store
                res = get_status_dict(
                    status='error',
                    message="No store found at '{}'. Forgot "
                            "--new-store-ok ?".format(
                        Path(base_path)),
                    **res_kwargs)
                yield res
                return

        log_progress(
            lgr.info, 'create-sibling-ria',
            'Creating a new RIA store at %s', Path(base_path),
        )
        create_store(io,
                     Path(base_path),
                     '1')

        yield from _create_sibling_ria(
            ds,
            url,
            push_url,
            name,
            storage_sibling,
            storage_name,
            alias,
            existing,
            shared,
            group,
            post_update_hook,
            trust_level,
            res_kwargs)

        if recursive:
            # Note: subdatasets can be treated independently, so go full
            # recursion when querying for them and _no_recursion with the
            # actual call. Theoretically this can be parallelized.

            for subds in ds.subdatasets(state='present',
                                        recursive=True,
                                        recursion_limit=recursion_limit,
                                        return_type='generator',
                                        result_renderer='disabled',
                                        result_xfm='datasets'):
                yield from _create_sibling_ria(
                    subds,
                    url,
                    push_url,
                    name,
                    storage_sibling,
                    storage_name,
                    None,  # subdatasets can't have the same alias as the parent
                    existing,
                    shared,
                    group,
                    post_update_hook,
                    trust_level,
                    res_kwargs)


def _create_sibling_ria(
        ds,
        url,
        push_url,
        name,
        storage_sibling,
        storage_name,
        alias,
        existing,
        shared,
        group,
        post_update_hook,
        trust_level,
        res_kwargs):
    # be safe across datasets
    res_kwargs = res_kwargs.copy()
    # update dataset
    res_kwargs['ds'] = ds

    if not isinstance(ds.repo, AnnexRepo):
        # No point in dealing with a special remote when there's no annex.
        # Note, that in recursive invocations this might only apply to some of
        # the datasets. Therefore dealing with it here rather than one level up.
        lgr.debug("No annex at %s. Ignoring special remote options.", ds.path)
        storage_sibling = False
        storage_name = None

    # parse target URL
    try:
        ssh_host, base_path, rewritten_url = \
            verify_ria_url(push_url if push_url else url, ds.config)
    except ValueError as e:
        yield get_status_dict(
            status='error',
            message=str(e),
            **res_kwargs
        )
        return

    base_path = Path(base_path)

    git_url = decode_source_spec(
        # append dataset id to url and use magic from clone-helper:
        url + '#{}'.format(ds.id),
        cfg=ds.config
    )['giturl']
    git_push_url = decode_source_spec(
        push_url + '#{}'.format(ds.id),
        cfg=ds.config
    )['giturl'] if push_url else None

    # determine layout locations; go for a v1 store-level layout
    repo_path, _, _ = get_layout_locations(1, base_path, ds.id)

    ds_siblings = [
        r['name'] for r in ds.siblings(
            result_renderer='disabled',
            return_type='generator')
    ]
    # Figure whether we are supposed to skip this very dataset
    if existing == 'skip' and (
            name in ds_siblings or (
                storage_name and storage_name in ds_siblings)):
        yield get_status_dict(
            status='notneeded',
            message="Skipped on existing sibling",
            **res_kwargs
        )
        # if we skip here, nothing else can change that decision further
        # down
        return

    # figure whether we need to skip or error due an existing target repo before
    # we try to init a special remote.
    if ssh_host:
        from datalad import ssh_manager
        ssh = ssh_manager.get_connection(
            ssh_host,
            use_remote_annex_bundle=False)
        ssh.open()

    if existing in ['skip', 'error']:
        config_path = repo_path / 'config'
        # No .git -- if it's an existing repo in a RIA store it should be a
        # bare repo.
        # Theoretically we could have additional checks for whether we have
        # an empty repo dir or a non-bare repo or whatever else.
        if ssh_host:
            try:
                ssh('[ -e {p} ]'.format(p=quote_cmdlinearg(str(config_path))))
                exists = True
            except CommandError:
                exists = False
        else:
            exists = config_path.exists()

        if exists:
            if existing == 'skip':
                # 1. not rendered by default
                # 2. message doesn't show up in ultimate result
                #    record as shown by -f json_pp
                yield get_status_dict(
                    status='notneeded',
                    message="Skipped on existing remote "
                            "directory {}".format(repo_path),
                    **res_kwargs
                )
                return
            else:  # existing == 'error'
                yield get_status_dict(
                    status='error',
                    message="remote directory {} already "
                            "exists.".format(repo_path),
                    **res_kwargs
                )
                return

    if storage_sibling == 'only':
        lgr.info("create storage sibling '{}' ...".format(name))
    else:
        lgr.info("create sibling{} '{}'{} ...".format(
            's' if storage_name else '',
            name,
            " and '{}'".format(storage_name) if storage_name else '',
        ))
    create_ds_in_store(SSHRemoteIO(ssh_host) if ssh_host else LocalIO(),
                       base_path, ds.id, '2', '1', alias,
                       init_obj_tree=storage_sibling is not False)
    if storage_sibling:
        # we are using the main `name`, if the only thing we are creating
        # is the storage sibling
        srname = name if storage_sibling == 'only' else storage_name

        lgr.debug('init special remote {}'.format(srname))
        special_remote_options = [
            'type=external',
            'externaltype=ora',
            'encryption=none',
            'autoenable=true',
            'url={}'.format(url)]
        if push_url:
            special_remote_options.append('push-url={}'.format(push_url))
        try:
            ds.repo.init_remote(
                srname,
                options=special_remote_options)
        except CommandError as e:
            if existing == 'reconfigure' \
                    and 'git-annex: There is already a special remote' \
                    in e.stderr:
                # run enableremote instead
                lgr.debug(
                    "special remote '%s' already exists. "
                    "Run enableremote instead.",
                    srname)
                # TODO: Use AnnexRepo.enable_remote (which needs to get
                #       `options` first)
                ds.repo.call_annex([
                    'enableremote',
                    srname] + special_remote_options)
            else:
                yield get_status_dict(
                    status='error',
                    message="initremote failed.\nstdout: %s\nstderr: %s"
                    % (e.stdout, e.stderr),
                    **res_kwargs
                )
                return

        if trust_level:
            trust_cmd = [trust_level]
            if trust_level == 'trust':
                # Following git-annex 8.20201129-73-g6a0030a11, using `git
                # annex trust` requires --force.
                trust_cmd.append('--force')
            ds.repo.call_annex(trust_cmd + [srname])
        # get uuid for use in bare repo's config
        uuid = ds.config.get("remote.{}.annex-uuid".format(srname))

    if storage_sibling == 'only':
        # we can stop here, the rest of the function is about setting up
        # the git remote part of the sibling
        yield get_status_dict(
            status='ok',
            **res_kwargs,
        )
        return

    # 2. create a bare repository in-store:

    lgr.debug("init bare repository")
    # TODO: we should prob. check whether it's there already. How?
    # Note: like the special remote itself, we assume local FS if no
    # SSH host is specified
    disabled_hook = repo_path / 'hooks' / 'post-update.sample'
    enabled_hook = repo_path / 'hooks' / 'post-update'

    if group:
        chgrp_cmd = "chgrp -R {} {}".format(
            quote_cmdlinearg(str(group)),
            quote_cmdlinearg(str(repo_path)))

    if ssh_host:
        ssh('cd {rootdir} && git init --bare{shared}'.format(
            rootdir=quote_cmdlinearg(str(repo_path)),
            shared=" --shared='{}'".format(
                quote_cmdlinearg(shared)) if shared else ''
        ))

        if storage_sibling:
            # write special remote's uuid into git-config, so clone can
            # which one it is supposed to be and enable it even with
            # fallback URL
            ssh("cd {rootdir} && git config datalad.ora-remote.uuid {uuid}"
                "".format(rootdir=quote_cmdlinearg(str(repo_path)),
                          uuid=uuid))

        if post_update_hook:
            ssh('mv {} {}'.format(quote_cmdlinearg(str(disabled_hook)),
                                  quote_cmdlinearg(str(enabled_hook))))

        if group:
            # Either repository existed before or a new directory was
            # created for it, set its group to a desired one if was
            # provided with the same chgrp
            ssh(chgrp_cmd)

        # finally update server
        if post_update_hook:
            # Conditional on post_update_hook, since one w/o the other doesn't
            # seem to make much sense.
            ssh('cd {rootdir} && git update-server-info'.format(
                rootdir=quote_cmdlinearg(str(repo_path))
            ))
    else:
        gr = GitRepo(repo_path, create=True, bare=True,
                     shared=shared if shared else None)
        if storage_sibling:
            # write special remote's uuid into git-config, so clone can
            # which one it is supposed to be and enable it even with
            # fallback URL
            gr.config.add("datalad.ora-remote.uuid", uuid, scope='local')

        if post_update_hook:
            disabled_hook.rename(enabled_hook)
        if group:
            # No CWD needed here, since `chgrp` is expected to be found via PATH
            # and the path it's operating on is absolute (repo_path). No
            # repository operation involved.
            Runner().run(chgrp_cmd)
        # finally update server
        if post_update_hook:
            # Conditional on post_update_hook, since one w/o the other doesn't
            # seem to make much sense.
            gr.call_git(["update-server-info"])

    # add a git remote to the bare repository
    # Note: needs annex-ignore! Otherwise we might push into dirhash
    # lower annex/object tree instead of mixed, since it's a bare
    # repo. This in turn would be an issue, if we want to pack the
    # entire thing into an archive. Special remote will then not be
    # able to access content in the "wrong" place within the archive
    lgr.debug("set up git remote")
    if name in ds_siblings:
        # otherwise we should have skipped or failed before
        assert existing == 'reconfigure'
    ds.config.set(
        "remote.{}.annex-ignore".format(name),
        value="true",
        scope="local")
    yield from ds.siblings(
        'configure',
        name=name,
        url=str(repo_path) if url.startswith("ria+file") else git_url,
        pushurl=git_push_url,
        recursive=False,
        # Note, that this should be None if storage_sibling was not set
        publish_depends=storage_name,
        result_renderer='disabled',
        return_type='generator',
        # Note, that otherwise a subsequent publish will report
        # "notneeded".
        fetch=True
    )

    yield get_status_dict(
        status='ok',
        **res_kwargs,
    )
