# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Create a sibling in a RIA store"""

__docformat__ = 'restructuredtext'


import logging
import subprocess

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
from datalad.utils import (
    Path,
    quote_cmdlinearg,
    rmtree,
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
from datalad.distributed.ria_utils import (
    get_layout_locations,
    verify_ria_url,
)

lgr = logging.getLogger('datalad.distributed.create_sibling_ria')


@build_doc
class CreateSiblingRia(Interface):
    """Creates a sibling to a dataset in a RIA store

    This creates a representation of a dataset in a ria-remote compliant
    storage location. For access to it two siblings are configured for the
    dataset by default. A "regular" one and a RIA remote (git-annex
    special remote). Furthermore, the former is configured to have a
    publication dependency on the latter. If not given a default name for
    the RIA remote is derived from the sibling's name by appending "-ria".

    The store's base path currently is expected to either:

      - not yet exist or
      - be empty or
      - have a valid "ria-layout-version" file and an "error_logs" directory.

    In the first two cases, said file and directory are created by this
    command. Alternatively you can manually create the third case, of course.
    Please note, that "ria-layout-version" needs to contain a line stating the
    version (currently "1") and optionally enable error logging (append a pipe
    symbol and an "l"  in that case). Currently, this line MUST end with a newline!

    Error logging will create files in the "error_log" directory whenever the
    RIA special remote (storage sibling) raises an exception, storing the
    python traceback of it. The logfiles are named according to the scheme
    <dataset id>.<annex uuid of the remote>.log showing 'who' ran into this
    issue with what dataset. Since this logging can potentially leak personal
    data (like local file paths for example) it can be disabled from the client
    side via "annex.ria-remote.<RIAREMOTE>.ignore-remote-config".

    Todo
    ----
    Where to put the description of a RIA store (see below)?

    The targeted layout of such a store is a tree of datasets, starting at the
    configured base path. First level of subdirectories are named for the first
    three characters of the datasets' id, second level is the remainder of
    those ids. The thereby created dataset directories contain a bare git
    repository. Those bare repositories are slightly different from plain
    git-annex bare repositories in that they use the standard dirhashmixed
    layout beneath annex/objects as opposed to dirhashlower, which is
    git-annex's default for bare repositories. Furthermore, there is an
    additional directory 'archives' within the dataset directories, which may
    or may not contain archives with annexed content.  Note, that this helps to
    reduce the number of inodes consumed (no checkout + potential archive) as
    well as it allows to resolve dependencies (that is (sub)datasets) merely by
    their id.  Finally, there is a file "ria-layout-version" put beneath the
    store's base path, determining the version of the dataset tree layout and a
    file of the same name per each dataset directory determining object tree
    layout version (we already switch from dirhashlower to dirhashmixed for
    example) and an additional directory "error_logs" at the toplevel.  """

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
            metavar="ria+<ssh|file>://<host>[/path]",
            doc="""URL identifying the target RIA store and access protocol.
            """,
            constraints=EnsureStr() | EnsureNone()),
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""Name of the sibling.
            With `recursive`, the same name will be used to label all
            the subdatasets' siblings.""",
            constraints=EnsureStr() | EnsureNone(),
            required=True),
        ria_remote_name=Parameter(
            args=("--ria-remote-name",),
            metavar="NAME",
            doc="""Name of the RIA remote (a git-annex special remote).
            Must not be identical to the sibling name. If not specified,
            defaults to the sibling name plus a '-ria' suffix.""",
            constraints=EnsureStr() | EnsureNone()),
        post_update_hook=Parameter(
            args=("--post-update-hook",),
            doc="""Enable git's default post-update-hook for the created
            sibling.""",
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
        ria_remote=Parameter(
            args=("--no-ria-remote",),
            dest='ria_remote',
            doc="""Whether to establish remote indexed archive (RIA) capabilties
            for the created sibling. If enabled, git-annex special remote access
            will be configured to enable regular git-annex key storage, and
            also retrieval of keys from (compressed) 7z archives that might be
            provided by the dataset store. If disabled, git-annex is instructed
            to ignore the sibling.""",
            action="store_false"),
        existing=Parameter(
            args=("--existing",),
            constraints=EnsureChoice(
                'skip', 'error', 'reconfigure') | EnsureNone(),
            metavar='MODE',
            doc="""Action to perform, if a sibling or ria-remote is already
            configured under the given name and/or a target already exists.
            In this case, a dataset can be skipped ('skip'), an existing target
            repository be forcefully re-initialized, and the sibling
            (re-)configured ('reconfigure'), or the command be instructed to
            fail ('error').""", ),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
        trust_level=Parameter(
            args=("--trust-level",),
            metavar="TRUST-LEVEL",
            constraints=EnsureChoice(
                'trust', 'semitrust', 'untrust') | EnsureNone(),
            doc="""specify a trust level for the RIA sibling. Internally this
            will call the respective git-annex command. If not specified
            nothing will be explicitly done, thereby defaulting to git-annex'
            default.""",),
    )

    @staticmethod
    @datasetmethod(name='create_sibling_ria')
    @eval_results
    def __call__(url,
                 name,
                 dataset=None,
                 ria_remote_name=None,
                 post_update_hook=False,
                 shared=None,
                 group=None,
                 ria_remote=True,
                 existing='error',
                 trust_level=None,
                 recursive=False,
                 recursion_limit=None
                 ):

        ds = require_dataset(
            dataset, check_installed=True, purpose='create sibling RIA')
        res_kwargs = dict(
            ds=ds,
            action="create-sibling-ria",
            logger=lgr,
        )

        if ds.repo.get_hexsha() is None or ds.id is None:
            raise RuntimeError(
                "Repository at {} is not a DataLad dataset, "
                "run 'datalad create [--force]' first.".format(ds.path))

        if not ria_remote and ria_remote_name:
            lgr.warning(
                "RIA remote setup disabled, but a ria-remote name was provided"
            )

        if ria_remote and not ria_remote_name:
            ria_remote_name = "{}-ria".format(name)

        if ria_remote and name == ria_remote_name:
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
            # in recursive mode this check could take a substantial amount of
            # time: employ a progress bar (or rather a counter, because we dont
            # know the total in advance
            pbar_id = 'check-siblings-{}'.format(id(ds))
            log_progress(
                lgr.info, pbar_id,
                'Start checking pre-existing sibling configuration %s', ds,
                label='Query siblings',
                unit=' Siblings',
            )
            # even if we have to fail, let's report all conflicting siblings
            # in subdatasets
            failed = False
            for r in ds.siblings(result_renderer=None,
                                 recursive=recursive,
                                 recursion_limit=recursion_limit):
                log_progress(
                    lgr.info, pbar_id,
                    'Discovered sibling %s in dataset at %s',
                    r['name'], r['path'],
                    update=1,
                    increment=True)
                if not r['type'] == 'sibling' or r['status'] != 'ok':
                    # this is an internal status query that has not consequence
                    # for the outside world. Be silent unless something useful
                    # can be said
                    #yield r
                    continue
                if r['name'] == name:
                    res = get_status_dict(
                        status='error',
                        message="a sibling '{}' is already configured in "
                        "dataset {}".format(name, r['path']),
                        **res_kwargs,
                    )
                    failed = True
                    yield res
                    continue
                if ria_remote_name and r['name'] == ria_remote_name:
                    res = get_status_dict(
                        status='error',
                        message="a sibling '{}' is already configured in "
                        "dataset {}".format(ria_remote_name, r['path']),
                        **res_kwargs,
                    )
                    failed = True
                    yield res
                    continue
            log_progress(
                lgr.info, pbar_id,
                'Finished checking pre-existing sibling configuration %s', ds,
            )
            if failed:
                return

        yield from _create_sibling_ria(
            ds,
            url,
            name,
            ria_remote,
            ria_remote_name,
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

            for subds in ds.subdatasets(fulfilled=True,
                                        recursive=True,
                                        recursion_limit=recursion_limit,
                                        result_xfm='datasets'):
                yield from _create_sibling_ria(
                    subds,
                    url,
                    name,
                    ria_remote,
                    ria_remote_name,
                    existing,
                    shared,
                    group,
                    post_update_hook,
                    trust_level,
                    res_kwargs)


def _create_sibling_ria(
        ds,
        url,
        name,
        ria_remote,
        ria_remote_name,
        existing,
        shared,
        group,
        post_update_hook,
        trust_level,
        res_kwargs):
    # be safe across datasets
    res_kwargs = res_kwargs.copy()

    # parse target URL
    try:
        ssh_host, base_path = verify_ria_url(url, ds.config)
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
    # determine layout locations; go for a v1 layout
    repo_path, _, _ = get_layout_locations(1, base_path, ds.id)

    ds_siblings = [r['name'] for r in ds.siblings(result_renderer=None)]
    # Figure whether we are supposed to skip this very dataset
    if existing == 'skip' and (
            name in ds_siblings or (
                ria_remote_name and ria_remote_name in ds_siblings)):
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

    lgr.info("create sibling{} '{}'{} ...".format(
        's' if ria_remote_name else '',
        name,
        " and '{}'".format(ria_remote_name) if ria_remote_name else '',
    ))
    if ria_remote:
        lgr.debug('init special remote {}'.format(ria_remote_name))
        ria_remote_options = ['type=external',
                              'externaltype=ria',
                              'encryption=none',
                              'autoenable=true',
                              'url={}'.format(url)]
        try:
            ds.repo.init_remote(
                ria_remote_name,
                options=ria_remote_options)
        except CommandError as e:
            if existing == 'reconfigure' \
                    and 'git-annex: There is already a special remote' \
                    in e.stderr:
                # run enableremote instead
                lgr.debug(
                    "special remote '%s' already exists. "
                    "Run enableremote instead.",
                    ria_remote_name)
                # TODO: Use AnnexRepo.enable_remote (which needs to get
                #       `options` first)
                cmd = [
                    'git',
                    'annex',
                    'enableremote',
                    ria_remote_name] + ria_remote_options
                subprocess.run(cmd, cwd=quote_cmdlinearg(ds.repo.path))
            else:
                yield get_status_dict(
                    status='error',
                    message="initremote failed.\nstdout: %s\nstderr: %s"
                    % (e.stdout, e.stderr),
                    **res_kwargs
                )
                return

        # 1. create remote object store:
        # Note: All it actually takes is to trigger the special
        # remote's `prepare` method once.
        # ATM trying to achieve that by invoking a minimal fsck.
        # TODO: - It's probably faster to actually talk to the special
        #         remote (i.e. pretending to be annex and use
        #         the protocol to send PREPARE)
        #       - Alternatively we can create the remote directory and
        #         ria version file directly, but this means
        #         code duplication that then needs to be kept in sync
        #         with ria-remote implementation.
        #       - this leads to the third option: Have that creation
        #         routine importable and callable from
        #         ria-remote package without the need to actually
        #         instantiate a RIARemote object
        lgr.debug("initializing object store")
        ds.repo.fsck(
            remote=ria_remote_name,
            fast=True,
            annex_options=['--exclude=*/*'])

        if trust_level:
            ds.repo.call_git(['annex', trust_level, ria_remote_name])

    else:
        # with no special remote we currently need to create the
        # required directories
        # TODO: This should be cleaner once we have access to the
        #       special remote's RemoteIO classes without
        #       talking via annex
        if ssh_host:
            ssh('mkdir -p {}'.format(quote_cmdlinearg(str(repo_path))))
        else:
            repo_path.mkdir(parents=True)

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
        if post_update_hook:
            ssh('mv {} {}'.format(quote_cmdlinearg(str(disabled_hook)),
                                  quote_cmdlinearg(str(enabled_hook))))

        if group:
            # Either repository existed before or a new directory was
            # created for it, set its group to a desired one if was
            # provided with the same chgrp
            ssh(chgrp_cmd)
    else:
        GitRepo(repo_path, create=True, bare=True,
                shared=" --shared='{}'".format(
                    quote_cmdlinearg(shared)) if shared else None)
        if post_update_hook:
            disabled_hook.rename(enabled_hook)
        if group:
            # TODO; do we need a cwd here?
            subprocess.run(chgrp_cmd, cwd=quote_cmdlinearg(ds.path))

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
        where="local")
    ds.siblings(
        'configure',
        name=name,
        url=git_url
        if ssh_host
        else str(repo_path),
        recursive=False,
        # Note, that this should be None if ria_remote was not set
        publish_depends=ria_remote_name,
        result_renderer=None,
        # Note, that otherwise a subsequent publish will report
        # "notneeded".
        fetch=True
    )

    yield get_status_dict(
        status='ok',
        **res_kwargs,
    )
