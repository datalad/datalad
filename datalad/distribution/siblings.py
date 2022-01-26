# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for managing sibling configuration"""

__docformat__ = 'restructuredtext'


import logging
import os
import os.path as op
from urllib.parse import urlparse

import datalad.support.ansi_colors as ac
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.distribution.update import Update
from datalad.downloaders.credentials import UserPassword
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    annex_group_opt,
    annex_groupwanted_opt,
    annex_required_opt,
    annex_wanted_opt,
    as_common_datasrc,
    inherit_opt,
    location_description,
    publish_by_default,
    publish_depends,
    recursion_flag,
    recursion_limit,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import (
    generic_result_renderer,
    eval_results,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureBool,
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import (
    AccessDeniedError,
    AccessFailedError,
    CapturedException,
    CommandError,
    DownloadError,
    InsufficientArgumentsError,
    RemoteNotAvailableError,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.network import (
    RI,
    URL,
    PathRI,
)
from datalad.support.param import Parameter
from datalad.utils import (
    Path,
    ensure_list,
    slash_join,
)

from .dataset import (
    EnsureDataset,
    datasetmethod,
)

lgr = logging.getLogger('datalad.distribution.siblings')


def _mangle_urls(url, ds_name):
    if not url:
        return url
    return url.replace("%NAME", ds_name.replace("/", "-"))


@build_doc
class Siblings(Interface):
    """Manage sibling configuration

    This command offers four different actions: 'query', 'add', 'remove',
    'configure', 'enable'. 'query' is the default action and can be used to obtain
    information about (all) known siblings. 'add' and 'configure' are highly
    similar actions, the only difference being that adding a sibling
    with a name that is already registered will fail, whereas
    re-configuring a (different) sibling under a known name will not
    be considered an error. 'enable' can be used to complete access
    configuration for non-Git sibling (aka git-annex special remotes).
    Lastly, the 'remove' action allows for the
    removal (or de-configuration) of a registered sibling.

    For each sibling (added, configured, or queried) all known sibling
    properties are reported. This includes:

    "name"
        Name of the sibling

    "path"
        Absolute path of the dataset

    "url"
        For regular siblings at minimum a "fetch" URL, possibly also a
        "pushurl"

    Additionally, any further configuration will also be reported using
    a key that matches that in the Git configuration.

    By default, sibling information is rendered as one line per sibling
    following this scheme::

      <dataset_path>: <sibling_name>(<+|->) [<access_specification]

    where the `+` and `-` labels indicate the presence or absence of a
    remote data annex at a particular remote, and `access_specification`
    contains either a URL and/or a type label for the sibling.
    """
    # make the custom renderer the default, path reporting isn't the top
    # priority here
    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to configure.  If
            no dataset is given, an attempt is made to identify the dataset
            based on the input and/or the current working directory""",
            constraints=EnsureDataset() | EnsureNone()),
        name=Parameter(
            args=('-s', '--name',),
            metavar='NAME',
            doc="""name of the sibling. For addition with path "URLs" and
            sibling removal this option is mandatory, otherwise the hostname
            part of a given URL is used as a default. This option can be used
            to limit 'query' to a specific sibling.""",
            constraints=EnsureStr() | EnsureNone()),
        action=Parameter(
            args=('action',),
            nargs='?',
            doc="""command action selection (see general documentation)""",
            constraints=EnsureChoice('query', 'add', 'remove', 'configure', 'enable')),
        url=Parameter(
            args=('--url',),
            doc="""the URL of or path to the dataset sibling named by
                `name`. For recursive operation it is required that
                a template string for building subdataset sibling URLs
                is given.\n List of currently available placeholders:\n
                %%NAME\tthe name of the dataset, where slashes are replaced by
                dashes.""",
            constraints=EnsureStr() | EnsureNone(),
            nargs="?"),
        pushurl=Parameter(
            args=('--pushurl',),
            doc="""in case the `url` cannot be used to publish to the dataset
                sibling, this option specifies a URL to be used instead.\nIf no
                `url` is given, `pushurl` serves as `url` as well.""",
            constraints=EnsureStr() | EnsureNone()),
        description=location_description,

        ## info options
        # --template/cfgfrom gh-1462 (maybe also for a one-time inherit)
        # --wanted gh-925 (also see below for add_sibling approach)

        fetch=Parameter(
            args=("--fetch",),
            action="store_true",
            doc="""fetch the sibling after configuration"""),
        as_common_datasrc=Parameter(
            args=("--as-common-datasrc",),
            metavar='NAME',
            doc="""configure a sibling as a common data source of the
            dataset that can be automatically used by all consumers of the
            dataset. The sibling must be a regular Git remote with a
            configured HTTP(S) URL."""),
        publish_depends=publish_depends,
        publish_by_default=publish_by_default,
        annex_wanted=annex_wanted_opt,
        annex_required=annex_required_opt,
        annex_group=annex_group_opt,
        annex_groupwanted=annex_groupwanted_opt,
        inherit=inherit_opt,
        get_annex_info=Parameter(
            args=("--no-annex-info",),
            dest='get_annex_info',
            action="store_false",
            doc="""Whether to query all information about the annex configurations
            of siblings. Can be disabled if speed is a concern"""),
        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='siblings')
    @eval_results
    def __call__(
            action='query',
            *,
            dataset=None,
            name=None,
            url=None,
            pushurl=None,
            description=None,
            # TODO consider true, for now like add_sibling
            fetch=False,
            as_common_datasrc=None,
            publish_depends=None,
            publish_by_default=None,
            annex_wanted=None,
            annex_required=None,
            annex_group=None,
            annex_groupwanted=None,
            inherit=False,
            get_annex_info=True,
            recursive=False,
            recursion_limit=None):

        # TODO: Detect malformed URL and fail?
        # XXX possibly fail if fetch is False and as_common_datasrc

        if annex_groupwanted and not annex_group:
            raise InsufficientArgumentsError(
                "To set groupwanted, you need to provide annex_group option")

        # TODO catch invalid action specified
        action_worker_map = {
            'query': _query_remotes,
            'add': _add_remote,
            'configure': _configure_remote,
            'remove': _remove_remote,
            'enable': _enable_remote,
        }
        # all worker strictly operate on a single dataset
        # anything that deals with hierarchies and/or dataset
        # relationships in general should be dealt with in here
        # at the top-level and vice versa
        worker = action_worker_map[action]

        ds = require_dataset(
            dataset,
            # it makes no sense to use this command without a dataset
            check_installed=True,
            purpose='configure sibling')
        refds_path = ds.path

        res_kwargs = dict(refds=refds_path, logger=lgr)

        ds_name = op.basename(ds.path)

        # do not form single list of datasets (with recursion results) to
        # give fastest possible response, for the precise of a long-all
        # function call

        # minimize expensive calls to .repo
        ds_repo = ds.repo

        # prepare common parameterization package for all worker calls
        worker_kwargs = dict(
            name=name,
            fetch=fetch,
            description=description,
            as_common_datasrc=as_common_datasrc,
            publish_depends=publish_depends,
            publish_by_default=publish_by_default,
            annex_wanted=annex_wanted,
            annex_required=annex_required,
            annex_group=annex_group,
            annex_groupwanted=annex_groupwanted,
            inherit=inherit,
            get_annex_info=get_annex_info,
            res_kwargs=res_kwargs,
        )
        yield from worker(
            ds=ds,
            repo=ds_repo,
            known_remotes=ds_repo.get_remotes(),
            # for top-level dataset there is no layout questions
            url=_mangle_urls(url, ds_name),
            pushurl=_mangle_urls(pushurl, ds_name),
            **worker_kwargs)
        if not recursive:
            return

        # do we have instructions to register siblings with some alternative
        # layout?
        replicate_local_structure = url and "%NAME" not in url

        subds_pushurl = None
        for subds in ds.subdatasets(
                state='present',
                recursive=recursive, recursion_limit=recursion_limit,
                result_xfm='datasets'):
            subds_repo = subds.repo
            subds_name = op.relpath(subds.path, start=ds.path)
            if replicate_local_structure:
                subds_url = slash_join(url, subds_name)
                if pushurl:
                    subds_pushurl = slash_join(pushurl, subds_name)
            else:
                subds_url = \
                    _mangle_urls(url, '/'.join([ds_name, subds_name]))
                subds_pushurl = \
                    _mangle_urls(pushurl, '/'.join([ds_name, subds_name]))
            yield from worker(
                ds=subds,
                repo=subds_repo,
                known_remotes=subds_repo.get_remotes(),
                url=subds_url,
                pushurl=subds_pushurl,
                **worker_kwargs)

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui

        # should we attempt to remove an unknown sibling, complain like Git does
        if res['status'] == 'notneeded' and res['action'] == 'remove-sibling':
            ui.message(
                '{warn}: No sibling "{name}" in dataset {path}'.format(
                    warn=ac.color_word('Warning', ac.LOG_LEVEL_COLORS['WARNING']),
                    **res)
            )
            return
        if res['status'] != 'ok' or not res.get('action', '').endswith('-sibling') :
            generic_result_renderer(res)
            return
        path = op.relpath(res['path'],
                       res['refds']) if res.get('refds', None) else res['path']
        got_url = 'url' in res
        spec = '{}{}{}{}'.format(
            res.get('url', ''),
            ' (' if got_url else '',
            res.get('annex-externaltype', 'git'),
            ')' if got_url else '')
        ui.message('{path}: {name}({with_annex}) [{spec}]'.format(
            **dict(
                res,
                path=path,
                # TODO report '+' for special remotes
                with_annex='+' if 'annex-uuid' in res \
                    else ('-' if res.get('annex-ignore', None) else '?'),
                spec=spec)))


# always copy signature from above to avoid bugs
def _add_remote(ds, repo, name, known_remotes, url, pushurl, as_common_datasrc,
                res_kwargs, **unused_kwargs):
    # TODO: allow for no url if 'inherit' and deduce from the super ds
    #       create-sibling already does it -- generalize/use
    #  Actually we could even inherit/deduce name from the super by checking
    #  which remote it is actively tracking in current branch... but may be
    #  would be too much magic

    # it seems that the only difference is that `add` should fail if a remote
    # already exists
    if (url is None and pushurl is None):
        raise InsufficientArgumentsError(
            """insufficient information to add a sibling
            (needs at least a dataset, and any URL).""")

    # a pushurl should always be able to fill in for a not
    # specified url, however, only when adding new remotes,
    # not when configuring existing remotes (to avoid undesired
    # overwriting of configurations), hence done here only
    if url is None:
        url = pushurl

    if not name:
        urlri = RI(url)
        # use the hostname as default remote name
        try:
            name = urlri.hostname
        except AttributeError:
            raise InsufficientArgumentsError(
                "cannot derive a default remote name from '{}', "
                "please specify a name.".format(url))
        lgr.debug(
            "No sibling name given, use URL hostname '%s' as sibling name",
            name)

    if not name:
        raise InsufficientArgumentsError("no sibling name given")
    if name in known_remotes:
        yield get_status_dict(
            action='add-sibling',
            status='error',
            path=ds.path,
            type='sibling',
            name=name,
            message=("sibling is already known: %s, use `configure` instead?", name),
            **res_kwargs)
        return
    # XXX this check better be done in configure too
    # see https://github.com/datalad/datalad/issues/5914
    if as_common_datasrc == name:
        raise ValueError('Sibling name ({}) and common data source name ({}) '
                         'can not be identical.'.format(name, as_common_datasrc))
    if isinstance(RI(url), PathRI):
        # make sure any path URL is stored in POSIX conventions for consistency
        # with git's behavior (e.g. origin configured by clone)
        url = Path(url).as_posix()
    # this remote is fresh: make it known
    # just minimalistic name and URL, the rest is coming from `configure`
    repo.add_remote(name, url)
    known_remotes.append(name)
    # always copy signature from above to avoid bugs
    for r in _configure_remote(
            ds=ds, repo=repo, name=name, known_remotes=known_remotes, url=url,
            pushurl=pushurl, as_common_datasrc=as_common_datasrc,
            res_kwargs=res_kwargs, **unused_kwargs):
        if r['action'] == 'configure-sibling':
            r['action'] = 'add-sibling'
        yield r


def _configure_remote(
        ds, repo, name, known_remotes, url, pushurl, fetch, description,
        as_common_datasrc, publish_depends, publish_by_default,
        annex_wanted, annex_required, annex_group, annex_groupwanted,
        inherit, res_kwargs, **unused_kwargs):
    result_props = dict(
        action='configure-sibling',
        path=ds.path,
        type='sibling',
        name=name,
        **res_kwargs)
    if name is None:
        result_props['status'] = 'error'
        result_props['message'] = 'need sibling `name` for configuration'
        yield result_props
        return

    if name != 'here':
        # do all configure steps that are not meaningful for the 'here' sibling
        # AKA the local repo
        if name not in known_remotes and url:
            # this remote is fresh: make it known
            # just minimalistic name and URL, the rest is coming from `configure`
            repo.add_remote(name, url)
            known_remotes.append(name)
        elif url:
            # not new, override URl if given
            repo.set_remote_url(name, url)

        # make sure we have a configured fetch expression at this point
        fetchvar = 'remote.{}.fetch'.format(name)
        if fetchvar not in repo.config:
            # place default fetch refspec in config
            # same as `git remote add` would have added
            repo.config.add(
                fetchvar,
                '+refs/heads/*:refs/remotes/{}/*'.format(name),
                scope='local')

        if pushurl:
            repo.set_remote_url(name, pushurl, push=True)

        if publish_depends:
            # Check if all `deps` remotes are known to the `repo`
            unknown_deps = set(ensure_list(publish_depends)).difference(
                known_remotes)
            if unknown_deps:
                result_props['status'] = 'error'
                result_props['message'] = (
                    'unknown sibling(s) specified as publication dependency: %s',
                    unknown_deps)
                yield result_props
                return

        # define config var name for potential publication dependencies
        depvar = 'remote.{}.datalad-publish-depends'.format(name)
        # and default pushes
        dfltvar = "remote.{}.push".format(name)

        if fetch:
            # fetch the remote so we are up to date
            for r in Update.__call__(
                    dataset=ds.path,
                    sibling=name,
                    merge=False,
                    recursive=False,
                    on_failure='ignore',
                    return_type='generator',
                    result_xfm=None):
                # fixup refds
                r.update(res_kwargs)
                yield r

        delayed_super = _DelayedSuper(repo)
        if inherit and delayed_super.super is not None:
            # Adjust variables which we should inherit
            publish_depends = _inherit_config_var(
                delayed_super, depvar, publish_depends)
            publish_by_default = _inherit_config_var(
                delayed_super, dfltvar, publish_by_default)
            # Copy relevant annex settings for the sibling
            # makes sense only if current AND super are annexes, so it is
            # kinda a boomer, since then forbids having a super a pure git
            if isinstance(repo, AnnexRepo) and \
                    isinstance(delayed_super.repo, AnnexRepo) and \
                    name in delayed_super.repo.get_remotes():
                if annex_wanted is None:
                    annex_wanted = _inherit_annex_var(
                        delayed_super, name, 'wanted')
                if annex_required is None:
                    annex_required = _inherit_annex_var(
                        delayed_super, name, 'required')
                if annex_group is None:
                    # I think it might be worth inheritting group regardless what
                    # value is
                    #if annex_wanted in {'groupwanted', 'standard'}:
                    annex_group = _inherit_annex_var(
                        delayed_super, name, 'group'
                    )
                if annex_wanted == 'groupwanted' and annex_groupwanted is None:
                    # we better have a value for the expression for that group
                    annex_groupwanted = _inherit_annex_var(
                        delayed_super, name, 'groupwanted'
                    )

        if publish_depends:
            if depvar in ds.config:
                # config vars are incremental, so make sure we start from
                # scratch
                ds.config.unset(depvar, scope='local', reload=False)
            for d in ensure_list(publish_depends):
                lgr.info(
                    'Configure additional publication dependency on "%s"',
                    d)
                ds.config.add(depvar, d, scope='local', reload=False)
            ds.config.reload()

        if publish_by_default:
            if dfltvar in ds.config:
                ds.config.unset(dfltvar, scope='local', reload=False)
            for refspec in ensure_list(publish_by_default):
                lgr.info(
                    'Configure additional default publication refspec "%s"',
                    refspec)
                ds.config.add(dfltvar, refspec, 'local')
            ds.config.reload()

        assert isinstance(repo, GitRepo)  # just against silly code
        if isinstance(repo, AnnexRepo):
            # we need to check if added sibling an annex, and try to enable it
            # another part of the fix for #463 and #432
            try:
                exc = None
                if not ds.config.obtain(
                        'remote.{}.annex-ignore'.format(name),
                        default=False,
                        valtype=EnsureBool(),
                        store=False):
                    repo.enable_remote(name)
            except (CommandError, DownloadError) as exc:
                ce = CapturedException(exc)
                # TODO yield
                # this is unlikely to ever happen, now done for AnnexRepo
                # instances only
                # Note: CommandError happens with git-annex
                # 6.20180416+gitg86b18966f-1~ndall+1 (prior 6.20180510, from
                # which starts to fail with AccessFailedError) if URL is bogus,
                # so enableremote fails. E.g. as "tested" in test_siblings
                lgr.info(
                    "Could not enable annex remote %s. This is expected if %s "
                    "is a pure Git remote, or happens if it is not accessible.",
                    name, name)
                lgr.debug("Exception was: %s", ce)

            if as_common_datasrc:
                # we need a fully configured remote here
                # do not re-use `url`, but ask for the remote config
                # that git-annex will use too
                remote_url = repo.config.get(f'remote.{name}.url')
                ri = RI(remote_url)
                if isinstance(ri, URL) and ri.scheme in ('http', 'https'):
                    # XXX what if there is already a special remote
                    # of this name? Above check for remotes ignores special
                    # remotes. we need to `git annex dead REMOTE` on reconfigure
                    # before we can init a new one
                    # XXX except it is not enough

                    # make special remote of type=git (see #335)
                    repo.call_annex([
                        'initremote',
                        as_common_datasrc,
                        'type=git',
                        'location={}'.format(remote_url),
                        'autoenable=true'])
                else:
                    yield dict(
                        status='impossible',
                        message='cannot configure as a common data source, '
                                'URL protocol is not http or https',
                        **result_props)
    #
    # place configure steps that also work for 'here' below
    #
    if isinstance(repo, AnnexRepo):
        for prop, var in (('wanted', annex_wanted),
                          ('required', annex_required),
                          ('group', annex_group)):
            if var is not None:
                repo.set_preferred_content(prop, var, '.' if name =='here' else name)
        if annex_groupwanted:
            repo.set_groupwanted(annex_group, annex_groupwanted)

    if description:
        if not isinstance(repo, AnnexRepo):
            result_props['status'] = 'impossible'
            result_props['message'] = 'cannot set description of a plain Git repository'
            yield result_props
            return
        repo.call_annex(['describe', name, description])

    # report all we know at once
    info = list(_query_remotes(ds, repo, name, known_remotes, **unused_kwargs))[0]
    info.update(dict(status='ok', **result_props))
    yield info


def _query_remotes(ds, repo, name, known_remotes, get_annex_info=True,
                   res_kwargs=None, **unused_kwargs):
    res_kwargs = res_kwargs or {}
    annex_info = {}
    available_space = None
    want_annex_info = get_annex_info and isinstance(repo, AnnexRepo)
    if want_annex_info:
        # pull repo info from annex
        try:
            # need to do in safety net because of gh-1560
            raw_info = repo.repo_info(fast=True)
        except CommandError:
            raw_info = {}
        available_space = raw_info.get('available local disk space', None)
        for trust in ('trusted', 'semitrusted', 'untrusted'):
            ri = raw_info.get('{} repositories'.format(trust), [])
            for r in ri:
                uuid = r.get('uuid', '00000000-0000-0000-0000-00000000000')
                if uuid.startswith('00000000-0000-0000-0000-00000000000'):
                    continue
                ainfo = annex_info.get(uuid, {})
                ainfo['description'] = r.get('description', None)
                annex_info[uuid] = ainfo
    # treat the local repo as any other remote using 'here' as a label
    remotes = [name] if name else ['here'] + known_remotes
    special_remote_info = None
    if want_annex_info:
        # query it once here, and inspect per-remote further down
        special_remote_info = repo.get_special_remotes()

    for remote in remotes:
        info = get_status_dict(
            action='query-sibling',
            path=ds.path,
            type='sibling',
            name=remote,
            **res_kwargs)
        if remote != 'here' and remote not in known_remotes:
            info['status'] = 'error'
            info['message'] = 'unknown sibling name'
            yield info
            continue
        # now pull everything we know out of the config
        # simply because it is cheap and we don't have to go through
        # tons of API layers to be able to work with it
        if remote == 'here':
            # special case: this repo
            # aim to provide info using the same keys as for remotes
            # (see below)
            for src, dst in (('annex.uuid', 'annex-uuid'),
                             ('core.bare', 'annex-bare'),
                             ('annex.version', 'annex-version')):
                val = ds.config.get(src, None)
                if val is None:
                    continue
                info[dst] = val
            if available_space is not None:
                info['available_local_disk_space'] = available_space
        else:
            # common case: actual remotes
            for remotecfg in [k for k in ds.config.keys()
                              if k.startswith('remote.{}.'.format(remote))]:
                info[remotecfg[8 + len(remote):]] = ds.config[remotecfg]
        if get_annex_info and info.get('annex-uuid', None):
            ainfo = annex_info.get(info['annex-uuid'], {})
            annex_description = ainfo.get('description', None)
            if annex_description is not None:
                info['annex-description'] = annex_description
        if want_annex_info:
            if not repo.is_remote_annex_ignored(remote):
                try:
                    for prop in ('wanted', 'required', 'group'):
                        var = repo.get_preferred_content(
                            prop, '.' if remote == 'here' else remote)
                        if var:
                            info['annex-{}'.format(prop)] = var
                    groupwanted = repo.get_groupwanted(remote)
                    if groupwanted:
                        info['annex-groupwanted'] = groupwanted
                except CommandError as exc:
                    if 'cannot determine uuid' in exc.stderr:
                        # not an annex (or no connection), would be marked as
                        #  annex-ignore
                        msg = "Could not detect whether %s carries an annex. " \
                              "If %s is a pure Git remote, this is expected. " %\
                              (remote, remote)
                        repo.config.reload()
                        if repo.is_remote_annex_ignored(remote):
                            msg += "Remote was marked by annex as annex-ignore. " \
                                   "Edit .git/config to reset if you think that was done by mistake due to absent connection etc"
                        lgr.warning(msg)
                        info['annex-ignore'] = True
                    else:
                        raise
            else:
                info['annex-ignore'] = True

        if special_remote_info:
            # pull out special remote info for this remote, if there is any
            for k, v in special_remote_info.get(
                    info.get('annex-uuid'), {}).items():
                info[f'annex-{k}'] = v

        info['status'] = 'ok'
        yield info


def _remove_remote(ds, repo, name, res_kwargs, **unused_kwargs):
    if not name:
        # TODO we could do ALL instead, but that sounds dangerous
        raise InsufficientArgumentsError("no sibling name given")
    result_props = dict(
        action='remove-sibling',
        path=ds.path,
        type='sibling',
        name=name,
        **res_kwargs)
    try:
        # failure can happen and is OK
        repo.remove_remote(name)
    except RemoteNotAvailableError as e:
        yield get_status_dict(
            # result-oriented! given remote is absent already
            status='notneeded',
            **result_props)
        return

    yield get_status_dict(
        status='ok',
        **result_props)


def _enable_remote(ds, repo, name, res_kwargs, **unused_kwargs):
    result_props = dict(
        action='enable-sibling',
        path=ds.path,
        type='sibling',
        name=name,
        **res_kwargs)

    if not isinstance(repo, AnnexRepo):
        yield dict(
            result_props,
            status='impossible',
            message='cannot enable sibling of non-annex dataset')
        return

    if name is None:
        yield dict(
            result_props,
            status='error',
            message='require `name` of sibling to enable')
        return

    # get info on special remote
    sp_remotes = {v['name']: dict(v, uuid=k) for k, v in repo.get_special_remotes().items()}
    remote_info = sp_remotes.get(name, None)

    if remote_info is None:
        yield dict(
            result_props,
            status='impossible',
            message=("cannot enable sibling '%s', not known", name))
        return

    env = None
    cred = None
    if remote_info.get('type', None) == 'webdav':
        # a webdav special remote -> we need to supply a username and password
        if not ('WEBDAV_USERNAME' in os.environ and 'WEBDAV_PASSWORD' in os.environ):
            # nothing user-supplied
            # let's consult the credential store
            hostname = urlparse(remote_info.get('url', '')).netloc
            if not hostname:
                yield dict(
                    result_props,
                    status='impossible',
                    message="cannot determine remote host, credential lookup for webdav access is not possible, and not credentials were supplied")
            cred = UserPassword('webdav:{}'.format(hostname))
            if not cred.is_known:
                try:
                    cred.enter_new(
                        instructions="Enter credentials for authentication with WEBDAV server at {}".format(hostname),
                        user=os.environ.get('WEBDAV_USERNAME', None),
                        password=os.environ.get('WEBDAV_PASSWORD', None))
                except KeyboardInterrupt:
                    # user hit Ctrl-C
                    yield dict(
                        result_props,
                        status='impossible',
                        message="credentials are required for sibling access, abort")
                    return
            creds = cred()
            # update the env with the two necessary variable
            # we need to pass a complete env because of #1776
            env = dict(
                os.environ,
                WEBDAV_USERNAME=creds['user'],
                WEBDAV_PASSWORD=creds['password'])

    try:
        repo.enable_remote(name, env=env)
        result_props['status'] = 'ok'
    except AccessDeniedError as e:
        # credentials are wrong, wipe them out
        if cred and cred.is_known:
            cred.delete()
        result_props['status'] = 'error'
        result_props['message'] = str(e)
    except AccessFailedError as e:
        # some kind of connection issue
        result_props['status'] = 'error'
        result_props['message'] = str(e)
    except Exception as e:
        # something unexpected
        raise e

    yield result_props


def _inherit_annex_var(ds, remote, cfgvar):
    if cfgvar == 'groupwanted':
        var = getattr(ds.repo, 'get_%s' % cfgvar)(remote)
    else:
        var = ds.repo.get_preferred_content(cfgvar, remote)
    if var:
        lgr.info("Inherited annex config from %s %s = %s",
                 ds, cfgvar, var)
    return var


def _inherit_config_var(ds, cfgvar, var):
    if var is None:
        var = ds.config.get(cfgvar)
        if var:
            lgr.info(
                'Inherited publish_depends from %s: %s',
                ds, var)
    return var


class _DelayedSuper(object):
    """A helper to delay deduction on super dataset until needed

    But if asked and not found -- would return None for everything
    """

    def __init__(self, repo):
        self._child_dataset = Dataset(repo.path)
        self._super = None
        self._super_tried = False

    def __str__(self):
        return str(self.super)

    @property
    def super(self):
        if not self._super_tried:
            self._super_tried = True
            # here we must analyze current_ds's super, not the super_ds
            self._super = self._child_dataset.get_superdataset()
            if not self._super:
                lgr.warning(
                    "Cannot determine super dataset for %s, thus "
                    "probably nothing would be inherited where desired"
                    % self._child_dataset
                )
        return self._super

    # Lean proxies going through .super
    @property
    def config(self):
        return self.super.config if self.super else None

    @property
    def repo(self):
        return self.super.repo if self.super else None
