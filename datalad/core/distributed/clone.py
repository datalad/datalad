# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for dataset installation"""


import logging
from argparse import REMAINDER
from typing import Dict

from datalad.cmd import CommandError
from datalad.config import ConfigManager
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.common_opts import (
    location_description,
    reckless_opt,
)
from datalad.interface.results import get_status_dict
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureKeyChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CapturedException
from datalad.support.network import (
    RI,
    PathRI,
)
from datalad.support.param import Parameter
from datalad.utils import (
    PurePath,
    knows_annex,
    rmtree,
)

from .clone_utils import (  # needed because other code imports it from here
    _check_autoenable_special_remotes,
    _format_clone_errors,
    _generate_candidate_clone_sources,
    _get_remote,
    _get_tracking_source,
    _map_urls,
    _test_existing_clone_target,
    _try_clone_candidates,
    decode_source_spec,
)

from .clone_utils import ( # isort: skip
    # RIA imports needed b/c datalad-next imports it from here ATM
    # Remove after core was released and next dropped the ria patch.
    postclone_preannex_cfg_ria,
    postclonecfg_ria,
)

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.core.distributed.clone')


@build_doc
class Clone(Interface):
    """Obtain a dataset (copy) from a URL or local directory

    The purpose of this command is to obtain a new clone (copy) of a dataset
    and place it into a not-yet-existing or empty directory. As such `clone`
    provides a strict subset of the functionality offered by `install`. Only a
    single dataset can be obtained, and immediate recursive installation of
    subdatasets is not supported. However, once a (super)dataset is installed
    via `clone`, any content, including subdatasets can be obtained by a
    subsequent `get` command.

    Primary differences over a direct `git clone` call are 1) the automatic
    initialization of a dataset annex (pure Git repositories are equally
    supported); 2) automatic registration of the newly obtained dataset as a
    subdataset (submodule), if a parent dataset is specified; 3) support
    for additional resource identifiers (DataLad resource identifiers as used
    on datasets.datalad.org, and RIA store URLs as used for store.datalad.org
    - optionally in specific versions as identified by a branch or a tag; see
    examples); and 4) automatic configurable generation of alternative access
    URL for common cases (such as appending '.git' to the URL in case the
    accessing the base URL failed).

    In case the clone is registered as a subdataset, the original URL passed to
    `clone` is recorded in `.gitmodules` of the parent dataset in addition
    to the resolved URL used internally for git-clone. This allows to preserve
    datalad specific URLs like ria+ssh://... for subsequent calls to `get` if
    the subdataset was locally removed later on.

    || PYTHON >>By default, the command returns a single Dataset instance for
    an installed dataset, regardless of whether it was newly installed ('ok'
    result), or found already installed from the specified source ('notneeded'
    result).<< PYTHON ||

    URL mapping configuration

    'clone' supports the transformation of URLs via (multi-part) substitution
    specifications. A substitution specification is defined as a configuration
    setting 'datalad.clone.url-substition.<seriesID>' with a string containing
    a match and substitution expression, each following Python's regular
    expression syntax. Both expressions are concatenated to a single string
    with an arbitrary delimiter character. The delimiter is defined by
    prefixing the string with the delimiter. Prefix and delimiter are stripped
    from the expressions (Example: ",^http://(.*)$,https://\\1").  This setting
    can be defined multiple times, using the same '<seriesID>'.  Substitutions
    in a series will be applied incrementally, in order of their definition.
    The first substitution in such a series must match, otherwise no further
    substitutions in a series will be considered. However, following the first
    match all further substitutions in a series are processed, regardless
    whether intermediate expressions match or not. Substitution series themselves
    have no particular order, each matching series will result in a candidate
    clone URL. Consequently, the initial match specification in a series should
    be as precise as possible to prevent inflation of candidate URLs.

    .. seealso::

      :ref:`handbook:3-001`
        More information on Remote Indexed Archive (RIA) stores
    """
    # by default ignore everything but install results
    # i.e. no "add to super dataset"
    result_filter = EnsureKeyChoice('action', ('install',))
    # very frequently this command will yield exactly one installed dataset
    # spare people the pain of going through a list by default
    return_type = 'item-or-list'
    # as discussed in #1409 and #1470, we want to return dataset instances
    # matching what is actually available after command completion (and
    # None for any failed dataset installation)
    result_xfm = 'successdatasets-or-none'

    _examples_ = [
        dict(text="Install a dataset from GitHub into the current directory",
             code_py="clone("
             "source='https://github.com/datalad-datasets/longnow"
             "-podcasts.git')",
             code_cmd="datalad clone "
             "https://github.com/datalad-datasets/longnow-podcasts.git"),
        dict(text="Install a dataset into a specific directory",
             code_py="""\
             clone(source='https://github.com/datalad-datasets/longnow-podcasts.git',
                   path='myfavpodcasts')""",
             code_cmd="""\
             datalad clone https://github.com/datalad-datasets/longnow-podcasts.git \\
             myfavpodcasts"""),
        dict(text="Install a dataset as a subdataset into the current dataset",
             code_py="""\
             clone(dataset='.',
                   source='https://github.com/datalad-datasets/longnow-podcasts.git')""",
             code_cmd="datalad clone -d . "
             "https://github.com/datalad-datasets/longnow-podcasts.git"),
        dict(text="Install the main superdataset from datasets.datalad.org",
             code_py="clone(source='///')",
             code_cmd="datalad clone ///"),
        dict(text="Install a dataset identified by a literal alias from store.datalad.org",
             code_py="clone(source='ria+http://store.datalad.org#~hcp-openaccess')",
             code_cmd="datalad clone ria+http://store.datalad.org#~hcp-openaccess"),
        dict(
            text="Install a dataset in a specific version as identified by a "
                 "branch or tag name from store.datalad.org",
            code_py="clone(source='ria+http://store.datalad.org#76b6ca66-36b1-11ea-a2e6-f0d5bf7b5561@myidentifier')",
            code_cmd="datalad clone ria+http://store.datalad.org#76b6ca66-36b1-11ea-a2e6-f0d5bf7b5561@myidentifier"),
        dict(
            text="Install a dataset with group-write access permissions",
            code_py=\
            "clone(source='http://example.com/dataset', reckless='shared-group')",
            code_cmd=\
            "datalad clone http://example.com/dataset --reckless shared-group"),
    ]

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""(parent) dataset to clone into. If given, the newly cloned
            dataset is registered as a subdataset of the parent. Also, if given,
            relative paths are interpreted as being relative to the parent
            dataset, and not relative to the working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        source=Parameter(
            args=("source",),
            metavar='SOURCE',
            doc="""URL, DataLad resource identifier, local path or instance of
            dataset to be cloned""",
            constraints=EnsureStr()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            nargs="?",
            doc="""path to clone into.  If no `path` is provided a
            destination path will be derived from a source URL
            similar to :command:`git clone`"""),
        git_clone_opts=Parameter(
            args=("git_clone_opts",),
            metavar='GIT CLONE OPTIONS',
            nargs=REMAINDER,
            doc="""[PY: A list of command line arguments PY][CMD: Options CMD]
            to pass to :command:`git clone`. [CMD: Any argument specified after
            SOURCE and the optional PATH will be passed to git-clone. CMD] Note
            that not all options will lead to viable results. For example
            '--single-branch' will not result in a functional annex repository
            because both a regular branch and the git-annex branch are
            required. Note that a version in a RIA URL takes precedence over
            '--branch'."""),
        description=location_description,
        reckless=reckless_opt,
    )

    @staticmethod
    @datasetmethod(name='clone')
    @eval_results
    def __call__(
            source,
            path=None,
            git_clone_opts=None,
            *,
            dataset=None,
            description=None,
            reckless=None,
        ):
        # did we explicitly get a dataset to install into?
        # if we got a dataset, path will be resolved against it.
        # Otherwise path will be resolved first.
        ds = require_dataset(
            dataset, check_installed=True, purpose='clone') \
            if dataset is not None else dataset
        refds_path = ds.path if ds else None

        # legacy compatibility
        if reckless is True:
            # so that we can forget about how things used to be
            reckless = 'auto'

        if isinstance(source, Dataset):
            source = source.path

        if source == path:
            # even if they turn out to be identical after resolving symlinks
            # and more sophisticated witchcraft, it would still happily say
            # "it appears to be already installed", so we just catch an
            # obviously pointless input combination
            raise ValueError(
                "clone `source` and destination `path` are identical [{}]. "
                "If you are trying to add a subdataset simply use `save`".format(
                    path))

        if path is not None:
            path = resolve_path(path, dataset)

        # derive target from source:
        if path is None:
            # we got nothing but a source. do something similar to git clone
            # and derive the path from the source and continue
            # since this is a relative `path`, resolve it:
            # we are not going to reuse the decoded URL, as this is done for
            # all source candidates in clone_dataset(), we just use to determine
            # a destination path here in order to perform a bunch of additional
            # checks that shall not pollute the helper function
            source_ = decode_source_spec(
                source, cfg=None if ds is None else ds.config)
            path = resolve_path(source_['default_destpath'], dataset)
            lgr.debug("Determined clone target path from source")
        lgr.debug("Resolved clone target path to: '%s'", path)

        # there is no other way -- my intoxicated brain tells me
        assert(path is not None)

        result_props = dict(
            action='install',
            logger=lgr,
            refds=refds_path,
            source_url=source)

        try:
            # this will implicitly cause pathlib to run a bunch of checks
            # whether the present path makes any sense on the platform
            # we are running on -- we don't care if the path actually
            # exists at this point, but we want to abort early if the path
            # spec is determined to be useless
            # we can do strict=False since we are 3.6+
            path.resolve(strict=False)
        except OSError as e:
            ce = CapturedException(e)
            yield get_status_dict(
                status='error',
                path=path,
                message=('cannot handle target path: %s', ce),
                exception=ce,
                **result_props)
            return

        destination_dataset = Dataset(path)
        result_props['ds'] = destination_dataset

        if ds is not None and ds.pathobj not in path.parents:
            yield get_status_dict(
                status='error',
                message=("clone target path '%s' not in specified target dataset '%s'",
                         path, ds),
                **result_props)
            return

        # perform the actual cloning operation
        clone_failure = False
        for r in clone_dataset(
                [source],
                destination_dataset,
                reckless,
                description,
                result_props,
                cfg=None if ds is None else ds.config,
                clone_opts=git_clone_opts,
                ):
            if r['status'] in ['error', 'impossible']:
                clone_failure = True
            yield r

        if clone_failure:
            # do not proceed saving anything if cloning failed
            return

        # TODO handle any 'version' property handling and verification using a
        # dedicated public helper

        if ds is not None:
            # we created a dataset in another dataset
            # -> make submodule
            actually_saved_subds = False
            for r in ds.save(
                    path,
                    # Note, that here we know we don't save anything but a new
                    # subdataset. Hence, don't go with default commit message,
                    # but be more specific.
                    message="[DATALAD] Added subdataset",
                    return_type='generator',
                    result_filter=None,
                    result_xfm=None,
                    result_renderer='disabled',
                    on_failure='ignore'):
                actually_saved_subds = actually_saved_subds or (
                        r['action'] == 'save' and
                        r['type'] == 'dataset' and
                        r['refds'] == ds.path and
                        r['status'] == 'ok')
                yield r

            # Modify .gitmodules to contain originally given url. This is
            # particularly relevant for postclone routines on a later `get`
            # for that subdataset. See gh-5256.

            if isinstance(RI(source), PathRI):
                # ensure posix paths; Windows paths would neither be meaningful
                # as a committed path nor are they currently stored correctly
                # (see gh-7182).
                # Restricted to when 'source' is identified as a path, b/c this
                # wouldn't work with file-URLs (ria or not):
                #
                # PureWindowsPath("file:///C:/somewhere/path").as_posix() ->
                # 'file:/C:/somewhere/path'
                source = PurePath(source).as_posix()
            if actually_saved_subds:
                # New subdataset actually saved. Amend the modification
                # of .gitmodules.
                # Note, that we didn't allow deviating from git's default
                # behavior WRT a submodule's name vs its path when we made this
                # a new subdataset.
                # all pathobjs involved are platform paths, but the
                # default submodule name equals the relative path
                # in posix conventions, hence .as_posix()
                subds_name = path.relative_to(ds.pathobj).as_posix()
                ds.repo.call_git(
                    ['config',
                     '--file',
                     '.gitmodules',
                     '--replace-all',
                     'submodule.{}.{}'.format(subds_name,
                                              "datalad-url"),
                     source]
                )
                yield from ds.save('.gitmodules',
                                   amend=True, to_git=True,
                                   result_renderer='disabled',
                                   return_type='generator')
            else:
                # We didn't really commit. Just call `subdatasets`
                # in that case to have the modification included in the
                # post-clone state (whatever that may be).
                ds.subdatasets(path, set_property=[("datalad-url", source)])


def clone_dataset(
        srcs,
        destds,
        reckless=None,
        description=None,
        result_props=None,
        cfg=None,
        checkout_gitsha=None,
        clone_opts=None):
    """Internal helper to perform cloning without sanity checks (assumed done)

    This helper does not handle any saving of subdataset modification or adding
    in a superdataset.

    Parameters
    ----------
    srcs : list
      Any suitable clone source specifications (paths, URLs)
    destds : Dataset
      Dataset instance for the clone destination
    reckless : {None, 'auto', 'ephemeral', 'shared-...'}, optional
      Mode switch to put cloned dataset into unsafe/throw-away configurations, i.e.
      sacrifice data safety for performance or resource footprint. When None
      and `cfg` is specified, use the value of `datalad.clone.reckless`.
    description : str, optional
      Location description for the annex of the dataset clone (if there is any).
    result_props : dict, optional
      Default properties for any yielded result, passed on to get_status_dict().
    cfg : ConfigManager, optional
      Configuration for parent dataset. This will be queried instead
      of the global DataLad configuration.
    checkout_gitsha : str, optional
      If given, a specific commit, identified by shasum, will be checked out after
      cloning. A dedicated follow-up fetch will be performed, if the initial clone
      did not obtain the commit object. Should the checkout of the target commit
      cause a detached HEAD, the previously active branch will be reset to the
      target commit.
    clone_opts : list of str, optional
      Options passed to git-clone. Note that for RIA URLs, the version is
      translated to a --branch argument, and that will take precedence over a
      --branch argument included in this value.

    Yields
    ------
    dict
      DataLad result records
    """
    # apply the two in-house patches, do local to avoid circular imports
    from . import (
        clone_ephemeral,
        clone_ria,
    )

    if not result_props:
        # in case the caller had no specific idea on how results should look
        # like, provide sensible defaults
        result_props = dict(
            action='install',
            logger=lgr,
            ds=destds,
        )
    else:
        result_props = result_props.copy()

    candidate_sources = _generate_candidate_clone_sources(
        destds, srcs, cfg)

    # important test!
    # based on this `rmtree` will happen below after failed clone
    dest_path_existed, stop_props = _test_existing_clone_target(
        destds, candidate_sources)
    if stop_props:
        # something happened that indicates we cannot continue
        # yield and return
        result_props.update(stop_props)
        yield get_status_dict(**result_props)
        return

    if reckless is None and cfg:
        # if reckless is not explicitly given, but we operate on a
        # superdataset, query whether it has been instructed to operate
        # in a reckless mode, and inherit it for the coming clone
        reckless = cfg.get('datalad.clone.reckless', None)

    last_candidate, error_msgs, stop_props = _try_clone_candidates(
        destds=destds,
        candidate_sources=candidate_sources,
        clone_opts=clone_opts or [],
        dest_path_existed=dest_path_existed,
    )
    if stop_props:
        # no luck, report and stop
        result_props.update(stop_props)
        yield get_status_dict(**result_props)
        return
    else:
        # we can record the last attempt as the candidate URL that gave
        # a successful clone
        result_props['source'] = last_candidate

    if not destds.is_installed():
        # we do not have a clone, stop, provide aggregate error message
        # covering all attempts
        yield get_status_dict(
            status='error',
            message=_format_clone_errors(
                destds, error_msgs, last_candidate['giturl']),
            **result_props)
        return

    #
    # At minimum all further processing is all candidate for extension
    # patching.  wrap the whole thing in try-except, catch any exceptions
    # report it as an error results `rmtree` any intermediate and return
    #
    try:
        yield from _post_gitclone_processing_(
            destds=destds,
            cfg=cfg,
            gitclonerec=last_candidate,
            reckless=reckless,
            checkout_gitsha=checkout_gitsha,
            description=description,
        )
    except Exception as e:
        ce = CapturedException(e)
        # the rational for turning any exception into an error result is that
        # we are hadly able to distinguish user-error from an other errors
        yield get_status_dict(
            status='error',
            # XXX A test in core insists on the wrong message type to be used
            #error_message=ce.message,
            message=ce.message,
            exception=ce,
            **result_props,
        )
        rmtree(destds.path, children_only=dest_path_existed)
        return

    # yield successful clone of the base dataset now, as any possible
    # subdataset clone down below will not alter the Git-state of the
    # parent
    yield get_status_dict(status='ok', **result_props)


def _post_gitclone_processing_(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        reckless: None or str,
        checkout_gitsha: None or str,
        description: None or str,
):
    """Perform git-clone post-processing

    This is helper is called immediately after a Git clone was established.

    The properties of that clone are passed via `gitclonerec`.

    Yields
    ------
    DataLad result records
    """
    dest_repo = destds.repo
    remote = _get_remote(dest_repo)

    yield from _post_git_init_processing_(
        destds=destds,
        cfg=cfg,
        gitclonerec=gitclonerec,
        remote=remote,
        reckless=reckless,
    )

    if knows_annex(destds.path):
        # init annex when traces of a remote annex can be detected
        yield from _pre_annex_init_processing_(
            destds=destds,
            cfg=cfg,
            gitclonerec=gitclonerec,
            remote=remote,
            reckless=reckless,
        )
        dest_repo = _annex_init(
            destds=destds,
            cfg=cfg,
            gitclonerec=gitclonerec,
            remote=remote,
            description=description,
        )
        yield from _post_annex_init_processing_(
            destds=destds,
            cfg=cfg,
            gitclonerec=gitclonerec,
            remote=remote,
            reckless=reckless,
        )

    if checkout_gitsha and \
       dest_repo.get_hexsha(
            dest_repo.get_corresponding_branch()) != checkout_gitsha:
        try:
            postclone_checkout_commit(dest_repo, checkout_gitsha,
                                      remote=remote)
        except Exception:
            # We were supposed to clone a particular version but failed to.
            # This is particularly pointless in case of subdatasets and
            # potentially fatal with current implementation of recursion.
            # see gh-5387
            lgr.debug(
                "Failed to checkout %s, removing this clone attempt at %s",
                checkout_gitsha, destds.path)
            raise

    yield from _pre_final_processing_(
        destds=destds,
        cfg=cfg,
        gitclonerec=gitclonerec,
        remote=remote,
        reckless=reckless,
    )


def _post_git_init_processing_(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        remote: str,
        reckless: None or str,
):
    """Any post-git-init processing that need not be concerned with git-annex
    """
    if not gitclonerec.get("version"):
        postclone_check_head(destds, remote=remote)

    # act on --reckless=shared-...
    # must happen prior git-annex-init, where we can cheaply alter the repo
    # setup through safe re-init'ing
    if reckless and reckless.startswith('shared-'):
        lgr.debug(
            'Reinitializing %s to enable shared access permissions',
            destds)
        destds.repo.call_git(['init', '--shared={}'.format(reckless[7:])])

    # trick to have the function behave like a generator, even if it
    # (currently) doesn't actually yield anything.
    # but a patched version might want to...so for uniformity with
    # _post_annex_init_processing_() let's do this
    if False:
        yield


def _pre_annex_init_processing_(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        remote: str,
        reckless: None or str,
):
    """Pre-processing a to-be-initialized annex repository"""
    if reckless == 'auto':
        lgr.debug(
            "Instruct annex to hardlink content in %s from local "
            "sources, if possible (reckless)", destds.path)
        destds.config.set(
            'annex.hardlink', 'true', scope='local', reload=True)

    # trick to have the function behave like a generator, even if it
    # (currently) doesn't actually yield anything.
    if False:
        yield


def _annex_init(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        remote: str,
        description: None or str,
):
    """Initializing an annex repository"""
    lgr.debug("Initializing annex repo at %s", destds.path)
    # Note, that we cannot enforce annex-init via AnnexRepo().
    # If such an instance already exists, its __init__ will not be executed.
    # Therefore do quick test once we have an object and decide whether to call
    # its _init().
    #
    # Additionally, call init if we need to add a description (see #1403),
    # since AnnexRepo.__init__ can only do it with create=True
    repo = AnnexRepo(destds.path, init=True)
    if not repo.is_initialized() or description:
        repo._init(description=description)
    return repo


def _post_annex_init_processing_(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        remote: str,
        reckless: None or str,
):
    """Post-processing an annex repository"""
    # convenience aliases
    repo = destds.repo
    ds = destds

    if reckless == 'auto' or (reckless and reckless.startswith('shared-')):
        repo.call_annex(['untrust', 'here'])

    _check_autoenable_special_remotes(repo)

    # we have just cloned the repo, so it has a remote `remote`, configure any
    # reachable origin of origins
    yield from configure_origins(ds, ds, remote=remote)


def _pre_final_processing_(
        *,
        destds: Dataset,
        cfg: ConfigManager,
        gitclonerec: Dict,
        remote: str,
        reckless: None or str,
):
    """Any post-processing after Git and git-annex pieces are fully initialized
    """
    if reckless:
        # store the reckless setting in the dataset to make it
        # known to later clones of subdatasets via get()
        destds.config.set(
            'datalad.clone.reckless', reckless,
            scope='local',
            reload=True)
    else:
        # We would still want to reload configuration to ensure that any of the
        # above git invocations could have potentially changed the config
        # TODO: might no longer be necessary if 0.14.0 adds reloading upon
        # non-readonly commands invocation
        destds.config.reload()

    # trick to have the function behave like a generator, even if it
    # (currently) doesn't actually yield anything.
    if False:
        yield


def postclone_checkout_commit(repo, target_commit, remote="origin"):
    """Helper to check out a specific target commit in a fresh clone.

    Will not check (again) if current commit and target commit are already
    the same!
    """
    # record what branch we were on right after the clone
    active_branch = repo.get_active_branch()
    corr_branch = repo.get_corresponding_branch(branch=active_branch)
    was_adjusted = bool(corr_branch)
    repo_orig_branch = corr_branch or active_branch
    # if we are on a branch this hexsha will be the tip of that branch
    repo_orig_hexsha = repo.get_hexsha(repo_orig_branch)
    # make sure we have the desired commit locally
    # expensive and possibly error-prone fetch conditional on cheap
    # local check
    if not repo.commit_exists(target_commit):
        try:
            repo.fetch(remote=remote, refspec=target_commit)
        except CommandError as e:
            CapturedException(e)
            pass
        # instead of inspecting the fetch results for possible ways
        # with which it could failed to produced the desired result
        # let's verify the presence of the commit directly, we are in
        # expensive-land already anyways
        if not repo.commit_exists(target_commit):
            # there is nothing we can do about this
            # MIH thinks that removing the clone is not needed, as a likely
            # next step will have to be a manual recovery intervention
            # and not another blind attempt
            raise ValueError(
                'Target commit %s does not exist in the clone, and '
                'a fetch that commit from remote failed'
                % target_commit[:8])
    # checkout the desired commit
    repo.call_git(['checkout', target_commit])
    # did we detach?
    if repo_orig_branch and not repo.get_active_branch():
        # trace if current state is a predecessor of the branch_hexsha
        lgr.debug(
            "Detached HEAD after resetting worktree of %s "
            "(original branch: %s)", repo, repo_orig_branch)
        if repo.get_merge_base(
                [repo_orig_hexsha, target_commit]) == target_commit:
            # we assume the target_commit to be from the same branch,
            # because it is an ancestor -- update that original branch
            # to point to the target_commit, and update HEAD to point to
            # that location
            lgr.info(
                "Reset branch '%s' to %s (from %s) to "
                "avoid a detached HEAD",
                repo_orig_branch, target_commit[:8], repo_orig_hexsha[:8])
            branch_ref = 'refs/heads/%s' % repo_orig_branch
            repo.update_ref(branch_ref, target_commit)
            repo.update_ref('HEAD', branch_ref, symbolic=True)
            if was_adjusted:
                # Note: The --force is needed because the adjust branch already
                # exists.
                repo.adjust(options=["--unlock", "--force"])
        else:
            lgr.warning(
                "%s has a detached HEAD, because the target commit "
                "%s has no unique ancestor with branch '%s'",
                repo, target_commit[:8], repo_orig_branch)


def postclone_check_head(ds, remote="origin"):
    repo = ds.repo
    if not repo.commit_exists("HEAD"):
        # HEAD points to an unborn branch. A likely cause of this is that the
        # remote's main branch is something other than master but HEAD wasn't
        # adjusted accordingly.
        #
        # Let's choose the most recently updated remote ref (according to
        # commit date). In the case of a submodule, switching to a ref with
        # commits prevents .update_submodule() from failing. It is likely that
        # the ref includes the registered commit, but we don't have the
        # information here to know for sure. If it doesn't, .update_submodule()
        # will check out a detached HEAD.
        remote_branches = (
            b["refname:strip=2"] for b in repo.for_each_ref_(
                fields="refname:strip=2", sort="-committerdate",
                pattern="refs/remotes/" + remote))
        for rbranch in remote_branches:
            if rbranch in [remote + "/git-annex", "HEAD"]:
                continue
            if rbranch.startswith(remote + "/adjusted/"):
                # If necessary for this file system, a downstream
                # git-annex-init call will handle moving into an
                # adjusted state.
                continue
            repo.call_git(["checkout", "-b",
                           rbranch[len(remote) + 1:],  # drop "<remote>/"
                           "--track", rbranch])
            lgr.debug("Checked out local branch from %s", rbranch)
            return
        lgr.warning("Cloned %s but could not find a branch "
                    "with commits", ds.path)


def configure_origins(cfgds, probeds, label=None, remote="origin"):
    """Configure any discoverable local dataset sibling as a remote

    Parameters
    ----------
    cfgds : Dataset
      Dataset to receive the remote configurations
    probeds : Dataset
      Dataset to start looking for `remote` remotes. May be identical with
      `cfgds`.
    label : int, optional
      Each discovered remote will be configured as a remote under the name
      '<remote>-<label>'. If no label is given, '2' will be used by default,
      given that there is typically a remote named `remote` already.
    remote : str, optional
      Name of the default remote on clone.
    """
    if label is None:
        label = 1
    # let's look at the URL for that remote and see if it is a local
    # dataset
    origin_url = probeds.config.get(f'remote.{remote}.url')
    if not origin_url:
        # no remote with default name, nothing to do
        return
    if not cfgds.config.obtain(
            'datalad.install.inherit-local-origin',
            default=True):
        # no inheritance wanted
        return
    if not isinstance(RI(origin_url), PathRI):
        # not local path
        return

    # no need to reconfigure original/direct remote again
    if cfgds != probeds:
        # prevent duplicates
        known_remote_urls = set(
            cfgds.config.get(r + '.url', None)
            for r in cfgds.config.sections()
            if r.startswith('remote.')
        )
        if origin_url not in known_remote_urls:
            yield from cfgds.siblings(
                'configure',
                # no chance for conflict, can only be the second configured
                # remote
                name='{}-{}'.format(remote, label),
                url=origin_url,
                # fetch to get all annex info
                fetch=True,
                result_renderer='disabled',
                on_failure='ignore',
            )
    # and dive deeper
    # given the clone source is a local dataset, we can have a
    # cheap look at it, and configure its own `remote` as a remote
    # (if there is any), and benefit from additional annex availability
    # But first check if we would recurse into the same dataset
    # to prevent infinite recursion (see gh-7721)
    next_dataset_path = probeds.pathobj / origin_url
    if next_dataset_path.resolve() != probeds.pathobj.resolve():
        yield from configure_origins(
            cfgds,
            Dataset(next_dataset_path),
            label=label + 1,
            remote=remote)
