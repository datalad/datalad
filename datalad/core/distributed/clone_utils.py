"""Helpers used in the clone.py patch"""

__docformat__ = 'restructuredtext'

import logging
import re
from os.path import expanduser
from pathlib import Path
from typing import (
    Dict,
    List,
    Tuple,
)
from urllib.parse import unquote as urlunquote

from datalad.cmd import (
    CommandError,
    GitWitlessRunner,
    StdOutCapture,
)
from datalad.config import ConfigManager
from datalad.distributed.ora_remote import (
    LocalIO,
    RIARemoteError,
    SSHRemoteIO,
)
from datalad.distribution.dataset import Dataset
from datalad.distribution.utils import _get_flexible_source_candidates
from datalad.dochelpers import single_or_plural
from datalad.log import log_progress
from datalad.runner.exception import CommandError
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    CapturedException,
    DownloadError,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.network import (
    RI,
    SSHRI,
    URL,
    DataLadRI,
    download_url,
    get_local_file_url,
    is_url,
)
from datalad.support.strings import get_replacement_dict
from datalad.utils import (
    Path,
    PurePosixPath,
    ensure_bool,
    ensure_list,
    make_tempfile,
    rmtree,
)

__docformat__ = 'restructuredtext'

lgr = logging.getLogger('datalad.core.distributed.clone')


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
            runner = GitWitlessRunner()
            try:
                # "git config -f -" can read from stdin; this spares us a
                # temp file
                result = runner.run(
                    ['git', 'config', '-f', '-', 'datalad.ora-remote.uuid'],
                    stdin=config_content.encode(encoding='utf-8'),
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
                    # local config to overwrite committed URL
                    repo.config.set(
                        f"remote.{srs[org_uuid]['name']}.ora-url",
                        new_url, scope='local')
                    repo.enable_remote(srs[org_uuid]['name'])
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
                    repo.config.unset(f"remote.{srs[org_uuid]['name']}.ora-url",
                                      scope='local')
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


def _generate_candidate_clone_sources(
        destds: Dataset,
        srcs: List,
        cfg: ConfigManager or None) -> List:
    """Convert "raw" clone source specs to candidate URLs

    Returns
    -------
    Each item in the list is a dictionary with clone candidate properties.
    At minimum each dictionary contains a 'giturl' property, with a URL
    value suitable for passing to `git-clone`. Other properties are
    provided by `decode_source_spec()` and are documented there.
    """
    # check for configured URL mappings, either in the given config manager
    # or in the one of the destination dataset, which is typically not existent
    # yet and the process config is then used effectively
    srcs = _map_urls(cfg or destds.config, srcs)

    # decode all source candidate specifications
    # use a given config or pass None to make it use the process config
    # manager. Theoretically, we could also do
    # `cfg or destds.config` as done above, but some tests patch
    # the process config manager
    candidate_sources = [decode_source_spec(s, cfg=cfg) for s in srcs]

    # now expand the candidate sources with additional variants of the decoded
    # giturl, while duplicating the other properties in the additional records
    # for simplicity. The hope is to overcome a few corner cases and be more
    # robust than git clone
    return [
        dict(props, giturl=s) for props in candidate_sources
        for s in _get_flexible_source_candidates(props['giturl'])
    ]


def _test_existing_clone_target(
        destds: Dataset,
        candidate_sources: List) -> Tuple:
    """Check if the clone target exists, inspect it, if so

    Returns
    -------
    (bool, dict or None)
      A flag whether the target exists, and either a dict with properties
      of a result that should be yielded before an immediate return, or
      None, if the processing can continue
    """
    # important test! based on this `rmtree` will happen below after
    # failed clone
    dest_path = destds.pathobj
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
                # this should never happen, because Path() will let any non-path
                # stringification pass through unmodified, but we do not want any
                # potential crash due to pathlib behavior changes
                lgr.debug("Unexpected behavior of pathlib!")
                track_path = None
            for cand in candidate_sources:
                src = cand['giturl']
                if track_url == src \
                        or (not is_url(track_url)
                            and get_local_file_url(
                                track_url, compatibility='git') == src) \
                        or track_path == expanduser(src):
                    return dest_path_existed, dict(
                        status='notneeded',
                        message=("dataset %s was already cloned from '%s'",
                                 destds,
                                 src),
                    )
        # anything else is an error
        return dest_path_existed, dict(
            status='error',
            message='target path already exists and not empty, '
                    'refuse to clone into target path',
        )
    # found no reason to stop, i.e. empty target dir
    return dest_path_existed, None


def _try_clone_candidates(
        *,
        destds: Dataset,
        candidate_sources: List,
        clone_opts: List,
        dest_path_existed: bool) -> Tuple:
    """Iterate over candidate URLs and attempt a clone

    Parameters
    ----------
    destds: Dataset
      The target dataset the clone should materialize at.
    candidate_sources: list
      Each value is a dict with properties, as returned by
      `_generate_candidate_clone_sources()`
    clone_opts: list
      Options to be passed on to `_try_clone_candidate()`
    dest_path_existed: bool
      Flag whether the target path existed before attempting a clone.

    Returns
    -------
    (dict or None, dict, dict or None)
      The candidate record of the last clone attempt,
      a mapping of candidate URLs to potential error messages they yielded,
      and either a dict with properties of a result that should be yielded
      before an immediate return, or None, if the processing can continue
    """
    log_progress(
        lgr.info,
        'cloneds',
        'Attempting a clone into %s', destds.path,
        unit=' candidates',
        label='Cloning',
        total=len(candidate_sources),
    )
    error_msgs = dict()  # accumulate all error messages formatted per each url
    for cand in candidate_sources:
        log_progress(
            lgr.info,
            'cloneds',
            'Attempting to clone from %s to %s', cand['giturl'], destds.path,
            update=1,
            increment=True)

        tried_url, error, fatal = _try_clone_candidate(
            destds=destds,
            cand=cand,
            clone_opts=clone_opts,
        )

        if error is not None:
            lgr.debug("Failed to clone from URL: %s (%s)",
                      tried_url, error)

            error_msgs[tried_url] = error

            # ready playing field for the next attempt
            if destds.pathobj.exists():
                lgr.debug("Wiping out unsuccessful clone attempt at: %s",
                          destds.path)
                # We must not just rmtree since it might be curdir etc
                # we should remove all files/directories under it
                # TODO stringification can be removed once patlib compatible
                # or if PY35 is no longer supported
                rmtree(destds.path, children_only=dest_path_existed)

        if fatal:
            # cancel progress bar
            log_progress(
                lgr.info,
                'cloneds',
                'Completed clone attempts for %s', destds
            )
            return cand, error_msgs, fatal

        if error is None:
            # do not bother with other sources if succeeded
            break

    log_progress(
        lgr.info,
        'cloneds',
        'Completed clone attempts for %s', destds
    )
    return cand, error_msgs, None


def _try_clone_candidate(
        *,
        destds: Dataset,
        cand: Dict,
        clone_opts: List) -> Tuple:
    """Attempt a clone from a single candidate

    destds: Dataset
      The target dataset the clone should materialize at.
    candidate_sources: list
      Each value is a dict with properties, as returned by
      `_generate_candidate_clone_sources()`
    clone_opts: list
      Options to be passed on to `_try_clone_candidate()`

    Returns
    -------
    (str, str or None, dict or None)
      The first item is the effective URL a clone was attempted from.
      The second item is `None` if the clone was successful, or an
      error message, detailing the failure for the specific URL.
      If the third item is not `None`, it must be a result dict that
      should be yielded, and no further clone attempt (even when
      other candidates remain) will be attempted.
    """
    # right now, we only know git-clone based approaches
    return _try_git_clone_candidate(
        destds=destds,
        cand=cand,
        clone_opts=clone_opts,
    )


def _try_git_clone_candidate(
        *,
        destds: Dataset,
        cand: Dict,
        clone_opts: List) -> Tuple:
    """_try_clone_candidate() using `git-clone`

    Parameters and return value behavior is as described in
    `_try_clone_candidate()`.
    """
    if cand.get('version', None):
        opts = clone_opts + ["--branch=" + cand['version']]
    else:
        opts = clone_opts

    try:
        GitRepo.clone(
            path=destds.path,
            url=cand['giturl'],
            clone_options=opts,
            create=True)

    except CommandError as e:
        ce = CapturedException(e)
        e_stderr = e.stderr

        # MIH thinks this should rather use any of ce's message generating
        # methods, but kept it to avoid behavior changes
        error_msg = e

        if e_stderr and 'could not create work tree' in e_stderr.lower():
            # this cannot be fixed by trying another URL
            re_match = re.match(r".*fatal: (.*)$", e_stderr,
                                flags=re.MULTILINE | re.DOTALL)
            # existential failure
            return cand['giturl'], error_msg, dict(
                status='error',
                message=re_match.group(1).strip()
                if re_match else "stderr: " + e_stderr,
            )

        # failure for this URL
        return cand['giturl'], error_msg, None

    # success
    return cand['giturl'], None, None


def _format_clone_errors(
        destds: Dataset,
        error_msgs: List,
        last_clone_url: str) -> Tuple:
    """Format all accumulated clone errors across candidates into one message

    Returns
    -------
    (str, list)
      Message body and string formatting arguments for it.
    """
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
        error_args = (destds.path, last_clone_url)
    return error_msg, error_args


def _get_remote(repo: GitRepo) -> str:
    """Return the name of the remote of a freshly clones repo

    Raises
    ------
    RuntimeError
      In case there is no remote, which should never happen.
    """
    remotes = repo.get_remotes(with_urls_only=True)
    nremotes = len(remotes)
    if nremotes == 1:
        remote = remotes[0]
        lgr.debug("Determined %s to be remote of %s", remote, repo)
    elif remotes > 1:
        lgr.warning(
            "Fresh clone %s unexpected has multiple remotes: %s. Using %s",
            repo.path, remotes, remotes[0])
        remote = remotes[0]
    else:
        raise RuntimeError("bug: fresh clone has zero remotes")
    return remote


def _check_autoenable_special_remotes(repo: AnnexRepo):
    """Check and report on misconfigured/dysfunctional special remotes
    """
    srs = {True: [], False: []}  # special remotes by "autoenable" key
    remote_uuids = None  # might be necessary to discover known UUIDs

    repo_config = repo.config
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
                'dataset %s as bool. '
                'You might need to enable it later manually and/or fix it up '
                'to avoid this message in the future.',
                sr_autoenable, sr_name, repo.path)
            continue

        # If it looks like a type=git special remote, make sure we have up to
        # date information. See gh-2897.
        if sr_autoenable and repo_config.get(
                "remote.{}.fetch".format(sr_name)):
            try:
                repo.fetch(remote=sr_name)
            except CommandError as exc:
                ce = CapturedException(exc)
                lgr.warning("Failed to fetch type=git special remote %s: %s",
                            sr_name, ce)

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
            repo.path
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
            repo.path,
            srs[False][0] if len(srs[False]) == 1 else "SIBLING",
        )
