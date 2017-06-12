# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Plumbing command for managing sibling configuration"""

__docformat__ = 'restructuredtext'


import logging

from os.path import basename
from os.path import relpath

# XXX confusing: we have urljoin, _urljoin, dlurljoin
from datalad.distribution.add_sibling import _urljoin

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.utils import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import EnsureStr
from datalad.support.constraints import EnsureChoice
from datalad.support.constraints import EnsureNone
from datalad.support.param import Parameter
from datalad.support.exceptions import CommandError
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.network import RI
from datalad.interface.common_opts import recursion_flag
from datalad.interface.common_opts import recursion_limit
from datalad.interface.common_opts import as_common_datasrc
from datalad.interface.common_opts import publish_depends
from datalad.interface.common_opts import publish_by_default
from datalad.interface.common_opts import annex_wanted_opt
from datalad.interface.common_opts import annex_group_opt
from datalad.interface.common_opts import annex_groupwanted_opt
from datalad.interface.common_opts import inherit_opt
from datalad.interface.common_opts import location_description
from datalad.distribution.dataset import require_dataset
from datalad.utils import swallow_logs
from datalad.dochelpers import exc_str

from .dataset import EnsureDataset
from .dataset import datasetmethod

lgr = logging.getLogger('datalad.distribution.siblings')


def _mangle_urls(url, ds_name):
    if not url:
        return url
    return url.replace("%NAME", ds_name.replace("/", "-"))


@build_doc
class Siblings(Interface):
    """Manage sibling configuration

    This command offers four different modes: 'query', 'add', 'remove',
    'configure'. 'query' is the default mode and can be used to obtain
    information about (all) known siblings. `add` and `configure` are highly
    similar modes, the only difference being that adding a sibling
    with a name that is already registered will fail, whereas
    re-configuring a (different) sibling under a known name will not
    be considered an error. Lastly, the `remove` mode allows for the
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
            doc="""name of the sibling. For sibling removal this option is
            mandatory, otherwise the hostname part of a given URL is used as a
            default. This option can be used to limit 'query' to a specific
            sibling.""",
            constraints=EnsureStr() | EnsureNone()),
        mode=Parameter(
            ## actions
            # add gh-1235
            # remove gh-1483
            # query (implied)
            # configure gh-1235
            args=('mode',),
            nargs='?',
            metavar='MODE',
            doc="""mode""",
            constraints=EnsureChoice('query', 'add', 'remove', 'configure') | EnsureNone()),
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
        as_common_datasrc=as_common_datasrc,
        publish_depends=publish_depends,
        publish_by_default=publish_by_default,
        annex_wanted=annex_wanted_opt,
        annex_group=annex_group_opt,
        annex_groupwanted=annex_groupwanted_opt,
        inherit=inherit_opt,

        recursive=recursion_flag,
        recursion_limit=recursion_limit)

    @staticmethod
    @datasetmethod(name='siblings')
    @eval_results
    def __call__(
            mode='query',
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
            annex_group=None,
            annex_groupwanted=None,
            inherit=False,
            recursive=False,
            recursion_limit=None):

        # TODO catch invalid mode specified
        mode_worker_map = {
            'query': _query_remotes,
            'add': _add_remote,
            'configure': _configure_remote,
            'remove': _remove_remote,
        }
        # all worker strictly operate on a single dataset
        # anything that deals with hierarchies and/or dataset
        # relationships in general should be dealt with in here
        # at the top-level and vice versa
        worker = mode_worker_map[mode]

        dataset = require_dataset(
            dataset, check_installed=False, purpose='sibling configuration')
        refds_path = dataset.path

        res_kwargs = dict(refds=refds_path, logger=lgr)

        ds_name = basename(dataset.path)

        # do not form single list of datasets (with recursion results) to
        # give fastest possible response, for the precise of a long-all
        # function call
        ds = dataset
        for r in worker(
                # always copy signature to below to avoid bugs!
                ds, name,
                # for top-level dataset there is no layout questions
                _mangle_urls(url, ds_name),
                _mangle_urls(pushurl, ds_name),
                fetch, description,
                as_common_datasrc, publish_depends, publish_by_default,
                annex_wanted, annex_group, annex_groupwanted,
                inherit,
                **res_kwargs):
            yield r
        if not recursive:
            return

        # do we have instructions to register siblings with some alternative
        # layout?
        replicate_local_structure = url and "%NAME" not in url

        for subds in dataset.subdatasets(
                fulfilled=True,
                recursive=recursive, recursion_limit=recursion_limit,
                result_xfm='datasets'):
            subds_name = relpath(subds.path, start=dataset.path)
            if replicate_local_structure:
                subds_url = _urljoin(url, subds_name)
                subds_pushurl = _urljoin(pushurl, subds_name)
            else:
                subds_url = \
                    _mangle_urls(url, '/'.join([ds_name, subds_name]))
                subds_pushurl = \
                    _mangle_urls(pushurl, '/'.join([ds_name, subds_name]))
            for r in worker(
                    # always copy signature from above to avoid bugs
                    subds, name,
                    subds_url,
                    subds_pushurl,
                    fetch,
                    description,
                    as_common_datasrc, publish_depends, publish_by_default,
                    annex_wanted, annex_group, annex_groupwanted,
                    inherit,
                    **res_kwargs):
                yield r

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        from datalad.ui import ui
        if res['status'] != 'ok':
            # logging complained about this already
            return
        path = relpath(res['path'],
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
                with_annex='+' if 'annex-uuid' in res else '-',
                spec=spec)))


# always copy signature from above to avoid bugs
def _add_remote(
        ds, name, url, pushurl, fetch, description,
        as_common_datasrc, publish_depends, publish_by_default,
        annex_wanted, annex_group, annex_groupwanted,
        inherit,
        **res_kwargs):
    # it seems that the only difference is that `add` should fail if a remote
    # already exists
    if (url is None and pushurl is None):
        raise InsufficientArgumentsError(
            """insufficient information to add a sibling
            (needs at least a dataset, and any URL).""")
    if url is None:
        url = pushurl

    if not name:
        urlri = RI(url)
        # use the hostname as default remote name
        name = urlri.hostname
        lgr.debug(
            "No sibling name given, use URL hostname '%s' as sibling name",
            name)

    if not name:
        raise InsufficientArgumentsError("no sibling name given")
    if name in ds.repo.get_remotes():
        yield get_status_dict(
            action='add-sibling',
            status='error',
            path=ds.path,
            type='sibling',
            name=name,
            message=("sibling is already known: %s, use `configure` instead?", name),
            **res_kwargs)
        return
    # always copy signature from above to avoid bugs
    for r in _configure_remote(
            ds, name, url, pushurl, fetch, description,
            as_common_datasrc, publish_depends, publish_by_default,
            annex_wanted, annex_group, annex_groupwanted,
            inherit,
            **res_kwargs):
        if r['action'] == 'configure-sibling':
            r['action'] = 'add-sibling'
        yield r


# always copy signature from above to avoid bugs
def _configure_remote(
        ds, name, url, pushurl, fetch, description,
        as_common_datasrc, publish_depends, publish_by_default,
        annex_wanted, annex_group, annex_groupwanted,
        inherit,
        **res_kwargs):
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
    # cheat and pretend it is all new and shiny already
    if url: # poor AddSibling blows otherwise
        try:
            from datalad.distribution.add_sibling import AddSibling
            added = AddSibling.__call__(
                dataset=ds,
                name=name,
                url=url,
                pushurl=pushurl,
                as_common_datasrc=as_common_datasrc,
                publish_depends=publish_depends,
                publish_by_default=publish_by_default,
                annex_wanted=annex_wanted,
                annex_group=annex_group,
                annex_groupwanted=annex_groupwanted,
                inherit=inherit,
                # never recursive, done outside
                recursive=False,
                # we want to do this in our wrapper code
                fetch=False,
                # configure is what `force` was used for previously
                force=True)
            # just make sure the legacy code doesn't surprise us
            assert(len(added) == 1)
        except Exception as e:
            yield get_status_dict(
                status='error',
                message=exc_str(e),
                **result_props)
            return

    if fetch:
        # fetch the remote so we are up to date
        lgr.debug("Fetching sibling %s of %s", name, ds)
        # TODO better use `ds.update`
        ds.repo.fetch(name)

    if description:
        if not isinstance(ds.repo, AnnexRepo):
            result_props['status'] = 'impossible'
            result_props['message'] = 'cannot set description of a plain Git repository'
            yield result_props
            return
        ds.repo._run_annex_command('describe', annex_options=[name, description])
    # report all we know at once
    info = list(_query_remotes(ds, name))[0]
    info.update(dict(status='ok', **result_props))
    yield info


# always copy signature from above to avoid bugs
def _query_remotes(
        ds, name, url=None, pushurl=None, fetch=None, description=None,
        as_common_datasrc=None, publish_depends=None, publish_by_default=None,
        annex_wanted=None, annex_group=None, annex_groupwanted=None,
        inherit=None,
        **res_kwargs):
    annex_info = {}
    available_space = None
    if isinstance(ds.repo, AnnexRepo):
        # pull repo info from annex
        # TODO maybe we should make this step optional to save the call
        # in some cases. Would need an additional flag...
        try:
            # need to do in safety net because of gh-1560
            raw_info = ds.repo.repo_info(fast=True)
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
    known_remotes = ds.repo.get_remotes()
    # treat the local repo as any other remote using 'here' as a label
    remotes = [name] if name else ['here'] + known_remotes
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
            if not available_space is None:
                info['available_local_disk_space'] = available_space
        else:
            # common case: actual remotes
            for remotecfg in [k for k in ds.config.keys()
                              if k.startswith('remote.{}.'.format(remote))]:
                info[remotecfg[8 + len(remote):]] = ds.config[remotecfg]
        if 'annex-uuid' in info:
            ainfo = annex_info.get(info['annex-uuid'])
            annex_description = ainfo.get('description', None)
            if annex_description is not None:
                info['annex-description'] = annex_description

        info['status'] = 'ok'
        yield info


def _remove_remote(
        ds, name, url, pushurl, fetch, description,
        as_common_datasrc, publish_depends, publish_by_default,
        annex_wanted, annex_group, annex_groupwanted,
        inherit,
        **res_kwargs):
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
        with swallow_logs():
            ds.repo.remove_remote(name)
    except CommandError as e:
        if 'fatal: No such remote' in e.stderr:
            yield get_status_dict(
                # result-oriented! given remote is absent already
                status='notneeded',
                **result_props)
            return
        else:
            raise e

    yield get_status_dict(
        status='ok',
        **result_props)
