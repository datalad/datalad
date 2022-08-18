# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for dataset installation"""


from argparse import REMAINDER
import logging
import re
from os.path import expanduser
from collections import OrderedDict
from urllib.parse import unquote as urlunquote

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.interface.common_opts import (
    location_description,
    reckless_opt,
)
from datalad.log import log_progress
from datalad.support.gitrepo import (
    GitRepo,
)
from datalad.cmd import (
    CommandError,
    GitWitlessRunner,
    StdOutCapture,
)
from datalad.distributed.ora_remote import (
    LocalIO,
    RIARemoteError,
    SSHRemoteIO,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
    EnsureKeyChoice,
)
from datalad.support.exceptions import (
    CapturedException,
    DownloadError,
)
from datalad.support.param import Parameter
from datalad.support.strings import get_replacement_dict
from datalad.support.network import (
    DataLadRI,
    PathRI,
    RI,
    SSHRI,
    URL,
    download_url,
    get_local_file_url,
    is_url,
)
from datalad.dochelpers import (
    single_or_plural,
)
from datalad.utils import (
    ensure_bool,
    ensure_list,
    knows_annex,
    make_tempfile,
    Path,
    PurePosixPath,
    rmtree,
)

from datalad.distribution.dataset import (
    Dataset,
    datasetmethod,
    resolve_path,
    require_dataset,
    EnsureDataset,
)
from datalad.distribution.utils import (
    _get_flexible_source_candidates,
)
from datalad.utils import (
    check_symlink_capability
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
            if actually_saved_subds:
                # New subdataset actually saved. Amend the modification
                # of .gitmodules. Note, that we didn't allow to deviate
                # from git default behavior WRT a submodule's name vs
                # its path when we made this a new subdataset.
                subds_name = path.relative_to(ds.pathobj)
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


def _get_url_mappings(cfg):
    cfg_prefix = 'datalad.clone.url-substitute.'
    # figure out which keys we should be looking for
    # in the active config
    subst_keys = set(k for k in cfg.keys() if k.startswith(cfg_prefix))
    # and in the common config specs
    from datalad.interface.common_cfg import definitions
    subst_keys.update(k for k in definitions if k.startswith(cfg_prefix))
    # TODO a potential sorting of substitution series could be implemented
    # here
    return [
        # decode the rule specifications
        get_replacement_dict(
            # one or more could come out
            ensure_list(
                cfg.get(
                    k,
                    # make sure to pull the default from the common config
                    default=cfg.obtain(k),
                    # we specifically support declaration of multiple
                    # settings to build replacement chains
                    get_all=True)))
        for k in subst_keys
    ]


def _map_urls(cfg, urls):
    mapping_specs = _get_url_mappings(cfg)
    if not mapping_specs:
        return urls

    mapped = []
    # we process the candidate in order to maintain any prioritization
    # encoded in it (e.g. _get_flexible_source_candidates_for_submodule)
    # if we have a matching mapping replace the URL in its position
    for u in urls:
        # we only permit a single match
        # TODO we likely want to RF this to pick the longest match
        mapping_applied = False
        # try one mapping set at a time
        for mapping_spec in mapping_specs:
            # process all substitution patterns in the specification
            # always operate on strings (could be a Path instance too)
            mu = str(u)
            matched = False
            for match_ex, subst_ex in mapping_spec.items():
                if not matched:
                    matched = re.match(match_ex, mu) is not None
                if not matched:
                    break
                # try to map, would return unchanged, if there is no match
                mu = re.sub(match_ex, subst_ex, mu)
            if mu != u:
                lgr.debug("URL substitution: '%s' -> '%s'", u, mu)
                mapped.append(mu)
                # we could consider breaking after the for effective mapping
                # specification. however, that would mean any generic
                # definition of a broadly matching substitution would derail
                # the entroe system. moreover, suddently order would matter
                # substantially
                mapping_applied = True
        if not mapping_applied:
            # none of the mappings matches, go with the original URL
            # (really original, not the stringified one)
            mapped.append(u)
    return mapped


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
    if not result_props:
        # in case the caller had no specific idea on how results should look
        # like, provide sensible defaults
        result_props = dict(
            action='install',
            logger=lgr,
            ds=destds,
        )

    if reckless is None and cfg:
        # if reckless is not explicitly given, but we operate on a
        # superdataset, query whether it has been instructed to operate
        # in a reckless mode, and inherit it for the coming clone
        reckless = cfg.get('datalad.clone.reckless', None)

    dest_path = destds.pathobj

    # check for configured URL mappings, either in the given config manager
    # or in the one of the destination dataset, which is typically not existent
    # yet and the process config manager is then used effectively
    srcs = _map_urls(cfg or destds.config, srcs)

    # decode all source candidate specifications
    candidate_sources = [decode_source_spec(s, cfg=cfg) for s in srcs]

    # now expand the candidate sources with additional variants of the decoded
    # giturl, while duplicating the other properties in the additional records
    # for simplicity. The hope is to overcome a few corner cases and be more
    # robust than git clone
    candidate_sources = [
        dict(props, giturl=s) for props in candidate_sources
        for s in _get_flexible_source_candidates(props['giturl'])
    ]

    # important test! based on this `rmtree` will happen below after failed clone
    dest_path_existed = dest_path.exists()
    if dest_path_existed and any(dest_path.iterdir()):
        if destds.is_installed():
            # check if dest was cloned from the given source before
            # this is where we would have installed this from
            # this is where it was actually installed from
            track_name, track_url = _get_tracking_source(destds)
            try:
                # this will get us track_url in system native path conventions,
                # whenever it is a path (and not a URL)
                # this is needed to match it to any potentially incoming local
                # source path in the 'notneeded' test below
                track_path = str(Path(track_url))
            except Exception as e:
                CapturedException(e)
                # this should never happen, because Path() will let any non-path stringification
                # pass through unmodified, but we do not want any potential crash due to
                # pathlib behavior changes
                lgr.debug("Unexpected behavior of pathlib!")
                track_path = None
            for cand in candidate_sources:
                src = cand['giturl']
                if track_url == src \
                        or (not is_url(track_url)
                            and get_local_file_url(track_url, compatibility='git') == src) \
                        or track_path == expanduser(src):
                    yield get_status_dict(
                        status='notneeded',
                        message=("dataset %s was already cloned from '%s'",
                                 destds,
                                 src),
                        **result_props)
                    return
        # anything else is an error
        yield get_status_dict(
            status='error',
            message='target path already exists and not empty, refuse to clone into target path',
            **result_props)
        return

    log_progress(
        lgr.info,
        'cloneds',
        'Cloning dataset to %s', destds,
        total=len(candidate_sources),
        label='Clone attempt',
        unit=' Candidate locations',
    )
    clone_opts = clone_opts or []
    error_msgs = OrderedDict()  # accumulate all error messages formatted per each url
    for cand in candidate_sources:
        log_progress(
            lgr.info,
            'cloneds',
            'Attempting to clone from %s to %s', cand['giturl'], dest_path,
            update=1,
            increment=True)

        if cand.get('version', None):
            opts = clone_opts + ["--branch=" + cand['version']]
        else:
            opts = clone_opts

        try:
            # TODO for now GitRepo.clone() cannot handle Path instances, and PY35
            # doesn't make it happen seamlessly
            GitRepo.clone(
                path=str(dest_path),
                url=cand['giturl'],
                clone_options=opts,
                create=True)

        except CommandError as e:
            ce = CapturedException(e)
            e_stderr = e.stderr

            error_msgs[cand['giturl']] = e
            lgr.debug("Failed to clone from URL: %s (%s)",
                      cand['giturl'], ce)
            if dest_path.exists():
                lgr.debug("Wiping out unsuccessful clone attempt at: %s",
                          dest_path)
                # We must not just rmtree since it might be curdir etc
                # we should remove all files/directories under it
                # TODO stringification can be removed once patlib compatible
                # or if PY35 is no longer supported
                rmtree(str(dest_path), children_only=dest_path_existed)

            if e_stderr and 'could not create work tree' in e_stderr.lower():
                # this cannot be fixed by trying another URL
                re_match = re.match(r".*fatal: (.*)$", e_stderr,
                                    flags=re.MULTILINE | re.DOTALL)
                # cancel progress bar
                log_progress(
                    lgr.info,
                    'cloneds',
                    'Completed clone attempts for %s', destds
                )
                yield get_status_dict(
                    status='error',
                    message=re_match.group(1).strip()
                    if re_match else "stderr: " + e_stderr,
                    **result_props)
                return
            # next candidate
            continue

        result_props['source'] = cand
        # do not bother with other sources if succeeded
        break

    log_progress(
        lgr.info,
        'cloneds',
        'Completed clone attempts for %s', destds
    )

    if not destds.is_installed():
        if len(error_msgs):
            if all(not e.stdout and not e.stderr for e in error_msgs.values()):
                # there is nothing we can learn from the actual exception,
                # the exit code is uninformative, the command is predictable
                error_msg = "Failed to clone from all attempted sources: %s"
                error_args = list(error_msgs.keys())
            else:
                error_msg = "Failed to clone from any candidate source URL. " \
                            "Encountered errors per each url were:\n- %s"
                error_args = '\n- '.join(
                    '{}\n  {}'.format(url, exc.to_str())
                    for url, exc in error_msgs.items()
                )
        else:
            # yoh: Not sure if we ever get here but I felt that there could
            #      be a case when this might happen and original error would
            #      not be sufficient to troubleshoot what is going on.
            error_msg = "Awkward error -- we failed to clone properly. " \
                        "Although no errors were encountered, target " \
                        "dataset at %s seems to be not fully installed. " \
                        "The 'succesful' source was: %s"
            error_args = (destds.path, cand['giturl'])
        yield get_status_dict(
            status='error',
            message=(error_msg, error_args),
            **result_props)
        return

    dest_repo = destds.repo

    remotes = dest_repo.get_remotes(with_urls_only=True)
    nremotes = len(remotes)
    if nremotes == 1:
        remote = remotes[0]
        lgr.debug("Determined %s to be remote of %s", remote, destds)
    elif remotes > 1:
        lgr.warning(
            "Fresh clone %s unexpected has multiple remotes: %s. Using %s",
            destds.path, remotes, remotes[0])
        remote = remotes[0]
    else:
        raise RuntimeError("bug: fresh clone has zero remotes")

    if not cand.get("version"):
        postclone_check_head(destds, remote=remote)

    # act on --reckless=shared-...
    # must happen prior git-annex-init, where we can cheaply alter the repo
    # setup through safe re-init'ing
    if reckless and reckless.startswith('shared-'):
        lgr.debug('Reinitializing %s to enable shared access permissions', destds)
        destds.repo.call_git(['init', '--shared={}'.format(reckless[7:])])

    # In case of RIA stores we need to prepare *before* annex is called at all
    if result_props['source']['type'] == 'ria':
        postclone_preannex_cfg_ria(destds, remote=remote)

    yield from postclonecfg_annexdataset(
        destds,
        reckless,
        description,
        remote=remote)

    if checkout_gitsha and \
       dest_repo.get_hexsha(dest_repo.get_corresponding_branch()) != checkout_gitsha:
        try:
            postclone_checkout_commit(dest_repo, checkout_gitsha,
                                      remote=remote)
        except Exception as e:
            ce = CapturedException(e)
            yield get_status_dict(
                status='error',
                message=str(ce),
                exception=ce,
                **result_props,
            )

            # We were supposed to clone a particular version but failed to.
            # This is particularly pointless in case of subdatasets and
            # potentially fatal with current implementation of recursion.
            # see gh-5387
            lgr.debug("Failed to checkout %s, removing this clone attempt at %s", checkout_gitsha, dest_path)
            # TODO stringification can be removed once pathlib compatible
            # or if PY35 is no longer supported
            rmtree(str(dest_path), children_only=dest_path_existed)
            return

    # perform any post-processing that needs to know details of the clone
    # source
    if result_props['source']['type'] == 'ria':
        yield from postclonecfg_ria(destds, result_props['source'],
                                    remote=remote)

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

    # yield successful clone of the base dataset now, as any possible
    # subdataset clone down below will not alter the Git-state of the
    # parent
    yield get_status_dict(status='ok', **result_props)


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


def postclone_preannex_cfg_ria(ds, remote="origin"):

    # We need to annex-ignore the remote before annex-init is called on the clone,
    # due to issues 5186 and 5253 (and we would have done it afterwards anyway).
    # annex/objects in RIA stores is special for several reasons.
    # 1. the remote doesn't know about it (no actual local annex for the remote)
    # 2. RIA may use hashdir mixed, copying data to it via git-annex (if cloned
    #    via ssh or local) would make it see a bare repo and establish a
    #    hashdir lower annex object tree.
    # 3. We want the ORA remote to receive all data for the store, so its
    #    objects could be moved into archives (the main point of a RIA store).

    # Note, that this function might need an enhancement as theoretically a RIA
    # store could also hold simple standard annexes w/o an intended ORA remote.
    # This needs the introduction of a new version label in RIA datasets, making
    # the following call conditional.
    ds.config.set(f'remote.{remote}.annex-ignore', 'true', scope='local')


def postclonecfg_ria(ds, props, remote="origin"):
    """Configure a dataset freshly cloned from a RIA store"""
    repo = ds.repo

    def get_uuid_from_store(store_url):
        # First figure whether we cloned via SSH, HTTP or local path and then
        # get that config file the same way:
        config_content = None
        scheme = store_url.split(':', 1)[0]
        if scheme in ['http', 'https']:
            try:
                config_content = download_url(
                    "{}{}config".format(
                        store_url,
                        '/' if not store_url.endswith('/') else ''))
            except DownloadError as e:
                ce = CapturedException(e)
                lgr.debug("Failed to get config file from source:\n%s", ce)
        elif scheme == 'ssh':
            # TODO: switch the following to proper command abstraction:
            # SSHRemoteIO ignores the path part ATM. No remote CWD! (To be
            # changed with command abstractions). So we need to get that part to
            # have a valid path to the remote's config file:
            cfg_path = PurePosixPath(URL(store_url).path) / 'config'
            io = SSHRemoteIO(store_url)
            try:
                config_content = io.read_file(cfg_path)
            except RIARemoteError as e:
                ce = CapturedException(e)
                lgr.debug("Failed to get config file from source: %s", ce)

        elif scheme == 'file':
            # TODO: switch the following to proper command abstraction:
            io = LocalIO()
            cfg_path = Path(URL(store_url).localpath) / 'config'
            try:
                config_content = io.read_file(cfg_path)
            except (RIARemoteError, OSError) as e:
                ce = CapturedException(e)
                lgr.debug("Failed to get config file from source: %s", ce)
        else:
            lgr.debug("Unknown URL-Scheme %s in %s. Can handle SSH, HTTP or "
                      "FILE scheme URLs.", scheme, props['source'])

        # And read it
        uuid = None
        if config_content:
            # TODO: We might be able to spare the saving to a file.
            #       "git config -f -" is not explicitly documented but happens
            #       to work and would read from stdin. Make sure we know this
            #       works for required git versions and on all platforms.
            with make_tempfile(content=config_content) as cfg_file:
                runner = GitWitlessRunner()
                try:
                    result = runner.run(
                        ['git', 'config', '-f', cfg_file,
                         'datalad.ora-remote.uuid'],
                        protocol=StdOutCapture
                    )
                    uuid = result['stdout'].strip()
                except CommandError as e:
                    ce = CapturedException(e)
                    # doesn't contain what we are looking for
                    lgr.debug("Found no UUID for ORA special remote at "
                              "'%s' (%s)", remote, ce)

        return uuid




    # chances are that if this dataset came from a RIA store, its subdatasets
    # may live there too. Place a subdataset source candidate config that makes
    # get probe this RIA store when obtaining subdatasets
    ria_store_url = props['source'].split('#', maxsplit=1)[0]
    ds.config.set(
        # we use the label 'origin' for this candidate in order to not have to
        # generate a complicated name from the actual source specification.
        # we pick a cost of 200 to sort it before datalad's default candidates
        # for non-RIA URLs, because they prioritize hierarchical layouts that
        # cannot be found in a RIA store
        'datalad.get.subdataset-source-candidate-200origin',
        # use the entire original URL, up to the fragment + plus dataset ID
        # placeholder, this should make things work with any store setup we
        # support (paths, ports, ...)
        ria_store_url + '#{id}',
        scope='local')

    # setup publication dependency, if a corresponding special remote exists
    # and was enabled (there could be RIA stores that actually only have repos)
    # make this function be a generator
    ora_remotes = [s for s in ds.siblings('query', result_renderer='disabled')
                   if s.get('annex-externaltype') == 'ora']
    # get full special remotes' config for access to stored URL
    srs = repo.get_special_remotes() \
        if hasattr(repo, 'get_special_remotes') else dict()

    has_only_disabled_ora = \
        not ora_remotes and \
        any(r.get('externaltype') == 'ora' for r in srs.values())

    def match_in_urls(special_remote_cfg, url_to_match):
        # Figure whether either `url` or `push-url` in an ORA remote's config
        # match a given URL (to a RIA store).
        return special_remote_cfg['url'].startswith(url_to_match) or \
               (special_remote_cfg['push-url'].startswith(url_to_match)
                if 'push-url' in special_remote_cfg else False)

    no_enabled_ora_matches_url = \
        all(not match_in_urls(srs[r['annex-uuid']], ria_store_url)
            for r in ora_remotes)

    if has_only_disabled_ora or no_enabled_ora_matches_url:

        # No ORA remote autoenabled, but configuration known about at least one,
        # or enabled ORA remotes seem to not match clone URL.
        # Let's check the remote's config for datalad.ora-remote.uuid as stored
        # by create-sibling-ria and try enabling that one.
        lgr.debug("Found no autoenabled ORA special remote. Trying to look it "
                  "up in source config ...")

        org_uuid = get_uuid_from_store(props['giturl'])

        # Now, enable it. If annex-init didn't fail to enable it as stored, we
        # wouldn't end up here, so enable with store URL as suggested by the URL
        # we cloned from.
        if org_uuid:
            if org_uuid in srs.keys():
                # TODO: - Double-check autoenable value and only do this when
                #         true?
                #       - What if still fails? -> Annex shouldn't change config
                #         in that case

                # we only need the store:
                new_url = props['source'].split('#')[0]
                try:
                    repo.enable_remote(srs[org_uuid]['name'],
                                       options=['url={}'.format(new_url)]
                                       )
                    lgr.info("Reconfigured %s for %s",
                             srs[org_uuid]['name'], new_url)
                    # update ora_remotes for considering publication dependency
                    # below
                    ora_remotes = [s for s in
                                   ds.siblings('query',
                                               result_renderer='disabled')
                                   if s.get('annex-externaltype', None) ==
                                   'ora']
                except CommandError as e:
                    ce = CapturedException(e)
                    lgr.debug("Failed to reconfigure ORA special remote: %s", ce)
            else:
                lgr.debug("Unknown ORA special remote uuid at '%s': %s",
                          remote, org_uuid)

    # Set publication dependency for `remote` on the respective ORA remote:
    if ora_remotes:
        url_matching_remotes = [r for r in ora_remotes
                                if srs[r['annex-uuid']]['url'] == ria_store_url]

        if len(url_matching_remotes) == 1:
            # We have exactly one ORA remote with the same store URL we used for
            # cloning (includes previously reconfigured remote).
            # Set publication dependency:
            yield from ds.siblings('configure',
                                   name=remote,
                                   publish_depends=url_matching_remotes[0]['name'],
                                   result_filter=None,
                                   result_renderer='disabled')

        elif not url_matching_remotes:
            # No matches but we have successfully autoenabled ORA remotes. Could
            # be the same store accessed by different method (cloning via HTTP
            # but special remote access via SSH). We can confidently set
            # publication dependency if the store knows the UUID.
            org_uuid = get_uuid_from_store(props['giturl'])
            uuid_matching_remotes = [r for r in ora_remotes
                                     if r['annex-uuid'] == org_uuid]
            if uuid_matching_remotes:
                # Multiple uuid matches are actually possible via same-as.
                # However, in that case we can't decide which one is supposed to
                # be used with publishing to `remote`.
                if len(uuid_matching_remotes) == 1:
                    yield from ds.siblings(
                        'configure',
                        name=remote,
                        publish_depends=uuid_matching_remotes[0]['name'],
                        result_filter=None,
                        result_renderer='disabled')
                else:
                    lgr.warning(
                        "Found multiple matching ORA remotes. Couldn't decide "
                        "which one publishing to '%s' should depend on: %s."
                        " Consider running 'datalad siblings configure -s "
                        "%s --publish-depends ORAREMOTENAME' to set "
                        "publication dependency manually.",
                        remote,
                        [r['name'] for r in uuid_matching_remotes],
                        remote)

        else:
            # We have multiple ORA remotes with the same store URL we cloned
            # from.
            lgr.warning("Found multiple matching ORA remotes. Couldn't decide "
                        "which one publishing to '%s' should depend on: %s."
                        " Consider running 'datalad siblings configure -s "
                        "%s --publish-depends ORAREMOTENAME' to set "
                        "publication dependency manually.",
                        remote,
                        [r['name'] for r in url_matching_remotes],
                        remote)


def postclonecfg_annexdataset(ds, reckless, description=None, remote="origin"):
    """If ds "knows annex" -- annex init it, set into reckless etc

    Provides additional tune up to a possibly an annex repo, e.g.
    "enables" reckless mode, sets up description
    """
    # in any case check whether we need to annex-init the installed thing:
    if not knows_annex(ds.path):
        # not for us
        return

    # init annex when traces of a remote annex can be detected
    if reckless == 'auto':
        lgr.debug(
            "Instruct annex to hardlink content in %s from local "
            "sources, if possible (reckless)", ds.path)
        ds.config.set(
            'annex.hardlink', 'true', scope='local', reload=True)
    elif reckless == 'ephemeral':
        # In ephemeral clones we set annex.private=true. This would prevent the
        # location itself being recorded in uuid.log. With a private repo,
        # declaring dead (see below after annex-init) seems somewhat
        # superfluous, but on the other hand:
        # If an older annex that doesn't support private yet touches the
        # repo, the entire purpose of ephemeral would be sabotaged if we did
        # not declare dead in addition. Hence, keep it regardless of annex
        # version.
        ds.config.set('annex.private', 'true', scope='local')

    lgr.debug("Initializing annex repo at %s", ds.path)
    # Note, that we cannot enforce annex-init via AnnexRepo().
    # If such an instance already exists, its __init__ will not be executed.
    # Therefore do quick test once we have an object and decide whether to call
    # its _init().
    #
    # Additionally, call init if we need to add a description (see #1403),
    # since AnnexRepo.__init__ can only do it with create=True
    repo = AnnexRepo(ds.path, init=True)
    if not repo.is_initialized() or description:
        repo._init(description=description)
    if reckless == 'auto' or (reckless and reckless.startswith('shared-')):
        repo.call_annex(['untrust', 'here'])

    elif reckless == 'ephemeral':
        # with ephemeral we declare 'here' as 'dead' right away, whenever
        # we symlink the remote's annex, since availability from 'here' should
        # not be propagated for an ephemeral clone when we publish back to
        # the remote.
        # This will cause stuff like this for a locally present annexed file:
        # % git annex whereis d1
        # whereis d1 (0 copies) failed
        # BUT this works:
        # % git annex find . --not --in here
        # % git annex find . --in here
        # d1

        # we don't want annex copy-to <remote>
        ds.config.set(
            f'remote.{remote}.annex-ignore', 'true',
            scope='local')
        ds.repo.set_remote_dead('here')

        if check_symlink_capability(ds.repo.dot_git / 'dl_link_test',
                                    ds.repo.dot_git / 'dl_target_test'):
            # symlink the annex to avoid needless copies in an ephemeral clone
            annex_dir = ds.repo.dot_git / 'annex'
            origin_annex_url = ds.config.get(f"remote.{remote}.url", None)
            origin_git_path = None
            if origin_annex_url:
                try:
                    # Deal with file:// scheme URLs as well as plain paths.
                    # If origin isn't local, we have nothing to do.
                    origin_git_path = Path(RI(origin_annex_url).localpath)

                    # we are local; check for a bare repo first to not mess w/
                    # the path
                    if GitRepo(origin_git_path, create=False).bare:
                        # origin is a bare repo -> use path as is
                        pass
                    elif origin_git_path.name != '.git':
                        origin_git_path /= '.git'
                except ValueError as e:
                    CapturedException(e)
                    # Note, that accessing localpath on a non-local RI throws
                    # ValueError rather than resulting in an AttributeError.
                    # TODO: Warning level okay or is info level sufficient?
                    # Note, that setting annex-dead is independent of
                    # symlinking .git/annex. It might still make sense to
                    # have an ephemeral clone that doesn't propagate its avail.
                    # info. Therefore don't fail altogether.
                    lgr.warning("reckless=ephemeral mode: %s doesn't seem "
                                "local: %s\nno symlinks being used",
                                remote, origin_annex_url)
            if origin_git_path:
                # TODO make sure that we do not delete any unique data
                rmtree(str(annex_dir)) \
                    if not annex_dir.is_symlink() else annex_dir.unlink()
                annex_dir.symlink_to(origin_git_path / 'annex',
                                     target_is_directory=True)
        else:
            # TODO: What level? + note, that annex-dead is independent
            lgr.warning("reckless=ephemeral mode: Unable to create symlinks on "
                        "this file system.")

    srs = {True: [], False: []}  # special remotes by "autoenable" key
    remote_uuids = None  # might be necessary to discover known UUIDs

    repo_config = repo.config
    # Note: The purpose of this function is to inform the user. So if something
    # looks misconfigured, we'll warn and move on to the next item.
    for uuid, config in repo.get_special_remotes().items():
        sr_name = config.get('name', None)
        if sr_name is None:
            lgr.warning(
                'Ignoring special remote %s because it does not have a name. '
                'Known information: %s',
                uuid, config)
            continue
        sr_autoenable = config.get('autoenable', False)
        try:
            sr_autoenable = ensure_bool(sr_autoenable)
        except ValueError as e:
            CapturedException(e)
            lgr.warning(
                'Failed to process "autoenable" value %r for sibling %s in '
                'dataset %s as bool.'
                'You might need to enable it later manually and/or fix it up to'
                ' avoid this message in the future.',
                sr_autoenable, sr_name, ds.path)
            continue

        # If it looks like a type=git special remote, make sure we have up to
        # date information. See gh-2897.
        if sr_autoenable and repo_config.get("remote.{}.fetch".format(sr_name)):
            try:
                repo.fetch(remote=sr_name)
            except CommandError as exc:
                ce = CapturedException(exc)
                lgr.warning("Failed to fetch type=git special remote %s: %s",
                            sr_name, exc)

        # determine whether there is a registered remote with matching UUID
        if uuid:
            if remote_uuids is None:
                remote_uuids = {
                    # Check annex-config-uuid first. For sameas annex remotes,
                    # this will point to the UUID for the configuration (i.e.
                    # the key returned by get_special_remotes) rather than the
                    # shared UUID.
                    (repo_config.get('remote.%s.annex-config-uuid' % r) or
                     repo_config.get('remote.%s.annex-uuid' % r))
                    for r in repo.get_remotes()
                }
            if uuid not in remote_uuids:
                srs[sr_autoenable].append(sr_name)

    if srs[True]:
        lgr.debug(
            "configuration for %s %s added because of autoenable,"
            " but no UUIDs for them yet known for dataset %s",
            # since we are only at debug level, we could call things their
            # proper names
            single_or_plural("special remote",
                             "special remotes", len(srs[True]), True),
            ", ".join(srs[True]),
            ds.path
        )

    if srs[False]:
        # if has no auto-enable special remotes
        lgr.info(
            'access to %s %s not auto-enabled, enable with:\n'
            '\t\tdatalad siblings -d "%s" enable -s %s',
            # but since humans might read it, we better confuse them with our
            # own terms!
            single_or_plural("dataset sibling",
                             "dataset siblings", len(srs[False]), True),
            ", ".join(srs[False]),
            ds.path,
            srs[False][0] if len(srs[False]) == 1 else "SIBLING",
        )

    # we have just cloned the repo, so it has a remote `remote`, configure any
    # reachable origin of origins
    yield from configure_origins(ds, ds, remote=remote)


_handle_possible_annex_dataset = postclonecfg_annexdataset


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
    yield from configure_origins(
        cfgds,
        Dataset(probeds.pathobj / origin_url),
        label=label + 1,
        remote=remote)


def _get_tracking_source(ds):
    """Returns name and url of a potential configured source
    tracking remote"""
    vcs = ds.repo
    # if we have a remote, let's check the location of that remote
    # for the presence of the desired submodule

    remote_name, tracking_branch = vcs.get_tracking_branch()
    if not remote_name and isinstance(vcs, AnnexRepo):
        # maybe cloned from a source repo that was in adjusted mode
        # https://github.com/datalad/datalad/issues/3969
        remote_name, tracking_branch = vcs.get_tracking_branch(
            corresponding=False)
    # TODO: better default `None`? Check where we might rely on '':
    remote_url = ''
    if remote_name:
        remote_url = vcs.get_remote_url(remote_name, push=False)

    return remote_name, remote_url


def _get_installationpath_from_url(url):
    """Returns a relative path derived from the trailing end of a URL

    This can be used to determine an installation path of a Dataset
    from a URL, analog to what `git clone` does.
    """
    ri = RI(url)
    if isinstance(ri, (URL, DataLadRI, SSHRI)):  # decode only if URL
        path = ri.path.rstrip('/')
        path = urlunquote(path) if path else ri.hostname
        if '/' in path:
            path = path.split('/')
            if path[-1] == '.git':
                path = path[-2]
            else:
                path = path[-1]
    else:
        path = Path(url).parts[-1]
    if path.endswith('.git'):
        path = path[:-4]
    return path


def decode_source_spec(spec, cfg=None):
    """Decode information from a clone source specification

    Parameters
    ----------
    spec : str
      Any supported clone source specification
    cfg : ConfigManager, optional
      Configuration will be queried from the instance (i.e. from a particular
      dataset). If None is given, the global DataLad configuration will be
      queried.

    Returns
    -------
    dict
      The value of each decoded property is stored under its own key in this
      dict. By default the following keys are return: 'type', a specification
      type label {'giturl', 'dataladri', 'ria'}; 'source' the original
      source specification; 'giturl' a URL for the source that is a suitable
      source argument for git-clone; 'version' a version-identifer, if present
      (None else); 'default_destpath' a relative path that that can be used as
      a clone destination.
    """
    if cfg is None:
        from datalad import cfg
    # standard property dict composition
    props = dict(
        source=spec,
        version=None,
    )

    # Git never gets to see these URLs, so let's manually apply any
    # rewrite configuration Git might know about.
    # Note: We need to rewrite before parsing, otherwise parsing might go wrong.
    # This is particularly true for insteadOf labels replacing even the URL
    # scheme.
    spec = cfg.rewrite_url(spec)
    # common starting point is a RI instance, support for accepting an RI
    # instance is kept for backward-compatibility reasons.
    # this conversion will raise ValueError for any unrecognized RI
    source_ri = RI(spec) if not isinstance(spec, RI) else spec

    # scenario switch, each case must set 'giturl' at the very minimum
    if isinstance(source_ri, DataLadRI):
        # we have got our DataLadRI as the source, so expand it
        props['type'] = 'dataladri'
        props['giturl'] = source_ri.as_git_url()
    elif isinstance(source_ri, URL) and source_ri.scheme.startswith('ria+'):
        # parse a RIA URI
        dsid, version = source_ri.fragment.split('@', maxsplit=1) \
            if '@' in source_ri.fragment else (source_ri.fragment, None)
        uuid_regex = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
        if re.match(uuid_regex, dsid):
            trace = '{}/{}'.format(dsid[:3], dsid[3:])
            default_destpath = dsid
        elif dsid.startswith('~'):
            trace = 'alias/{}'.format(dsid[1:])
            default_destpath = dsid[1:]
        else:
            raise ValueError(
                'RIA URI not recognized, no valid dataset ID or other supported '
                'scheme: {}'.format(spec))
        # now we cancel the fragment in the original URL, but keep everything else
        # in order to be able to support the various combinations of ports, paths,
        # and everything else
        source_ri.fragment = ''
        # strip the custom protocol and go with standard one
        source_ri.scheme = source_ri.scheme[4:]
        # take any existing path, and add trace to dataset within the store
        source_ri.path = '{urlpath}{urldelim}{trace}'.format(
            urlpath=source_ri.path if source_ri.path else '',
            urldelim='' if not source_ri.path or source_ri.path.endswith('/') else '/',
            trace=trace,
        )
        props.update(
            type='ria',
            giturl=str(source_ri),
            version=version,
            default_destpath=default_destpath,
        )
    else:
        # let's assume that anything else is a URI that Git can handle
        props['type'] = 'giturl'
        # use original input verbatim
        props['giturl'] = spec

    if 'default_destpath' not in props:
        # if we still have no good idea on where a dataset could be cloned to if no
        # path was given, do something similar to git clone and derive the path from
        # the source
        props['default_destpath'] = _get_installationpath_from_url(props['giturl'])

    return props
