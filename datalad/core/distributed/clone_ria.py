""""""

__docformat__ = 'restructuredtext'

import logging
from typing import Dict

from datalad.distribution.dataset import Dataset
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
from datalad.support.exceptions import (
    CapturedException,
    DownloadError,
)
from datalad.support.network import (
    URL,
    download_url,
)
from datalad.utils import (
    Path,
    PurePosixPath,
    make_tempfile,
)

from . import clone as mod_clone

# we need to preserve the original functions to be able to call them
# in the patch
orig_post_git_init_processing_ = mod_clone._post_git_init_processing_
orig_pre_final_processing_ = mod_clone._pre_final_processing_


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


def _post_git_init_processing_(
    *,
    destds: Dataset,
    gitclonerec: Dict,
    remote: str,
    **kwargs
):
    yield from orig_post_git_init_processing_(
        destds=destds, gitclonerec=gitclonerec, remote=remote,
        **kwargs)

    # In case of RIA stores we need to prepare *before* annex is called at all
    if gitclonerec['type'] == 'ria':
        postclone_preannex_cfg_ria(destds, remote=remote)


def _pre_final_processing_(
        *,
        destds: Dataset,
        gitclonerec: Dict,
        remote: str,
        **kwargs
):
    if gitclonerec['type'] == 'ria':
        yield from postclonecfg_ria(destds, gitclonerec,
                                    remote=remote)

    yield from orig_pre_final_processing_(
        destds=destds, gitclonerec=gitclonerec, remote=remote,
        **kwargs)


def _apply():
    # apply patch in a function, to be able to easily patch it out
    # and turn off the patch
    lgr.debug(
        'Apply RIA patch to clone.py:_post_git_init_processing_')
    mod_clone._post_git_init_processing_ = _post_git_init_processing_
    lgr.debug(
        'Apply RIA patch to clone.py:_pre_final_processing_')
    mod_clone._pre_final_processing_ = _pre_final_processing_


_apply()
