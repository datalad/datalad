# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Frontend for the DataLad config"""

__docformat__ = 'restructuredtext'


import logging
from textwrap import wrap

from datalad import cfg as dlcfg
from datalad.distribution.dataset import (
    Dataset,
    EnsureDataset,
    datasetmethod,
    require_dataset,
)
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.common_opts import (
    recursion_limit,
    recursion_flag,
)
from datalad.interface.common_cfg import definitions as cfg_defs
from datalad.interface.results import get_status_dict
from datalad.interface.utils import (
    eval_results,
    default_result_renderer,
)
import datalad.support.ansi_colors as ac
from datalad.support.exceptions import CommandError
from datalad.support.param import Parameter
from datalad.support.constraints import (
    EnsureChoice,
    EnsureNone,
    EnsureStr,
)
from datalad.utils import (
    ensure_list,
    Path,
)


lgr = logging.getLogger('datalad.core.local.configuration')

config_actions = ('dump', 'get', 'set', 'unset')


@build_doc
class Configuration(Interface):
    """Get and set dataset, dataset-clone-local, or global configuration

    .. note::
      This command was introduced with DataLad 0.14 and might still see
      API and behavior changes in future releases.

    This command works similar to git-config, but some features are not
    supported (e.g., modifying system configuration), while other features
    are not available in git-config (e.g., multi-configuration queries).

    Query and modification of three distinct configuration scopes is
    supported:

    - 'dataset': the persistent configuration in .datalad/config of a dataset
    - 'local': a dataset clone's Git repository configuration in .git/config
    - 'global': non-dataset-specific configuration (usually in $USER/.gitconfig)

    Modifications of the persistent 'dataset' configuration will not be saved
    by this command, but have to be committed with a subsequent `save`
    call.

    Rules of precedence regarding different configuration scopes are the same
    as in Git, with two exceptions: 1) environment variables can be used to
    override any datalad configuration, and have precedence over any other
    configuration scope (see below). 2) the 'dataset' scope is considered in
    addition to the standard git configuration scopes. Its content has lower
    precedence than Git configuration scopes, but it is committed to a dataset,
    hence can be used to ship (default and branch-specific) configuration with
    a dataset.

    Any DATALAD_* environment variable is also mapped to a configuration item.
    Their values take precedence over any other specification. In variable
    names '_' encodes a '.' in the configuration name, and '__' encodes a '-',
    such that 'DATALAD_SOME__VAR' is mapped to 'datalad.some-var'.

    Recursive operation is supported for querying and modifying configuration
    across a hierarchy of datasets.
    """
    _examples_ = [
        dict(text="Dump the effective configuration, including an annotation for common items",
             code_py="configuration()",
             code_cmd="datalad configuration"),
        dict(text="Query two configuration items",
             code_py="configuration('get', ['user.name', 'user.email'])",
             code_cmd="datalad configuration get user.name user.email"),
        dict(text="Recursively set configuration in all (sub)dataset repositories",
             code_py="configuration('set', [('my.config.name', 'value')], recursive=True)",
             code_cmd="datalad configuration -r set my.config=value"),
        dict(text="Modify the persistent dataset configuration (changes are not committed)",
             code_py="configuration('set', [('my.config.name', 'value')], scope='dataset')",
             code_cmd="datalad configuration --scope dataset set my.config=value"),
    ]

    result_renderer = 'tailored'

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to query or to configure""",
            constraints=EnsureDataset() | EnsureNone()),
        action=Parameter(
            args=("action",),
            nargs='?',
            doc="""which action to perform""",
            constraints=EnsureChoice(*config_actions)),
        scope=Parameter(
            args=("--scope",),
            doc="""scope for getting or setting
            configuration. If no scope is declared for a query, all
            configuration sources (including overrides via environment
            variables) are considered according to the normal
            rules of precedence. For action 'get' only 'dataset' and 'local'
            (with include 'global' here) are supported. For action 'dump',
            a scope selection is ignored and all scopes are considered.""",
            constraints=EnsureChoice('global', 'local', 'dataset', None)),
        spec=Parameter(
            args=("spec",),
            doc="""configuration name (for actions 'get' and 'unset'),
            or name/value pair (for action 'set')""",
            nargs='*',
            metavar='name[=value]'),
        recursive=recursion_flag,
        recursion_limit=recursion_limit,
    )

    # @staticmethod
    # @datasetmethod(name='config', bind=False)
    @eval_results
    def __call__(
            self,
            action='dump',
            spec=None,
            scope=None,
            dataset=None,
            recursive=False,
            recursion_limit=None):

        # check conditions
        # - global and recursion makes no sense

        if action == 'dump':
            if spec:
                raise ValueError(
                    'Configuration selection is not supported for dumping')
            if scope:
                raise ValueError(
                    'Scope selection is not supported for dumping')

        # normalize variable specificatons
        specs = []
        for s in ensure_list(spec):
            if isinstance(s, tuple):
                specs.append((str(s[0]), str(s[1])))
            elif '=' not in s:
                specs.append((str(s),))
            else:
                specs.append(tuple(s.split('=', 1)))

        if action == 'set':
            missing_values = [s[0] for s in specs if len(s) < 2]
            if missing_values:
                raise ValueError(
                    'Values must be provided for all configuration '
                    'settings. Missing: {}'.format(missing_values))
            invalid_names = [s[0] for s in specs if '.' not in s[0]]
            if invalid_names:
                raise ValueError(
                    'Name must contain a section (i.e. "section.name"). '
                    'Invalid: {}'.format(invalid_names))

        # ConfigManager's constructor takes a dataset as an argument:
        #      def __init__(self, dataset=None, overrides=None, source='any'):
        # but doesn't bind it inside -- just uses to figure things out and possibly (ab)use its Runner.
        # So, the only way to instantiate a proper "Mule" (joint ConfigManager + Configuration)
        # is to pass `dataset` to ConfigManager constructor, which of cause our interface'ing code
        # does not do ATM.
        ds = None
        if scope != 'global' or recursive:
            ds = require_dataset(
                dataset,
                check_installed=True,
                purpose='configuration')
            if ds and scope != 'global':
                import pdb; pdb.set_trace()
                # map scope ('local', 'dataset', None)  of configuration (excluding global) to source
                #           {'any', 'local', 'branch', 'branch-local'}
                # see also https://github.com/datalad/datalad/pull/5969
                # which maps
                source = {None: 'any', 'local': 'local', 'dataset': 'branch'}[scope]
                # self.setup(dataset=ds, source=source)

        res_kwargs = dict(
            action='configuration',
            logger=lgr,
        )
        if ds:
            res_kwargs['refds'] = ds.path
        yield from configuration(action, scope, specs, res_kwargs, ds)

        if not recursive:
            return

        for subds in ds.subdatasets(
                fulfilled=True,
                recursive=True,
                recursion_limit=recursion_limit,
                on_failure='ignore',
                result_renderer='disabled'):
            yield from configuration(
                action, scope, specs, res_kwargs, Dataset(subds['path']))

    @staticmethod
    def custom_result_renderer(res, **kwargs):
        if (res['status'] != 'ok' or
                res['action'] not in ('get_configuration',
                                      'dump_configuration')):
            if 'message' not in res and 'name' in res:
                suffix = '={}'.format(res['value']) if 'value' in res else ''
                res['message'] = '{}{}'.format(
                    res['name'],
                    suffix)
            default_result_renderer(res)
            return
        # TODO source
        from datalad.ui import ui
        name = res['name']
        if res['action'] == 'dump_configuration':
            for key in ('purpose', 'description'):
                s = res.get(key)
                if s:
                    ui.message('\n'.join(wrap(
                        s,
                        initial_indent='# ',
                        subsequent_indent='# ',
                    )))

        if kwargs.get('recursive', False):
            have_subds = res['path'] != res['refds']
            # we need to mark up from which dataset results are reported
            prefix = '<ds>{}{}:'.format(
                '/' if have_subds else '',
                Path(res['path']).relative_to(res['refds']).as_posix()
                if have_subds else '',
            )
        else:
            prefix = ''

        if kwargs.get('action', None) == 'dump':
            ui.message('{}{}={}'.format(
                prefix,
                ac.color_word(name, ac.BOLD),
                res['value'] if res['value'] is not None else '',
            ))
        else:
            ui.message('{}{}'.format(
                prefix,
                res['value'] if res['value'] is not None else '',
            ))


def configuration(action, scope, specs, res_kwargs, ds=None):
    if scope == 'global':
        cfg = dlcfg
    else:
        cfg = ds.config

    if action not in config_actions:
        raise ValueError("Unsupported action '{}'".format(action))

    if action == 'dump':
        # dumping is querying for all known keys
        specs = [(n,) for n in sorted(set(cfg_defs.keys()).union(cfg.keys()))]
        # ??? Yarik is not sure why scope would not mapper while dumping?!
        # I could have different values in different scopes
        scope = None

    for spec in specs:
        if '.' not in spec[0]:
            yield get_status_dict(
                ds=ds,
                status='error',
                message=(
                    "Configuration key without a section: '%s'",
                    spec[0],
                ),
                **res_kwargs)
            continue
        # TODO without get-all there is little sense in having add
        #if action == 'add':
        #    res = _add(cfg, scope, spec)
        if action == 'get':
            res = _get(cfg, scope, spec[0])
        elif action == 'dump':
            res = _dump(cfg, spec[0])
        # TODO this should be there, if we want to be comprehensive
        # however, we turned this off by default in the config manager
        # because we hardly use it, and the handling in ConfigManager
        # is not really well done.
        #elif action == 'get-all':
        #    res = _get_all(cfg, scope, spec)
        elif action == 'set':
            res = _set(cfg, scope, *spec)
        elif action == 'unset':
            res = _unset(cfg, scope, spec[0])

        if ds:
            res['path'] = ds.path

        if 'status' not in res:
            res['status'] = 'ok'

        yield dict(res_kwargs, **res)

    if action in ('add', 'set', 'unset'):
        # we perform a single reload, rather than one for each modification
        # TODO: can we detect a call from cmdline? We could skip the reload.
        cfg.reload(force=True)


def _dump(cfg, name):
    value = cfg.get(
        name,
        # pull a default from the config definitions
        # if we have no value, but a key
        cfg_defs.get(name, {}).get('default', None))

    res = dict(
        action='dump_configuration',
        name=name,
        value=value,
    )
    if name in cfg_defs:
        ui_def = cfg_defs[name].get('ui', [None, {}])[1]
        for s, key in ((ui_def.get('title'), 'purpose'),
                  (ui_def.get('text'), 'description')):
            if s:
                res[key] = s
    return res


def _get(cfg, scope, name):
    value = cfg.get_from_source(scope, name) \
        if scope else cfg.get(
            name,
            # pull a default from the config definitions
            # if we have no value, but a key (i.e. in dump mode)
            cfg_defs.get(name, {}).get('default', None))
    return dict(
        action='get_configuration',
        name=name,
        value=value,
    )


def _set(cfg, scope, name, value):
    cfg.set(name, value, where=scope, force=True, reload=False)
    return dict(
        action='set_configuration',
        name=name,
        value=value,
    )


def _unset(cfg, scope, name):
    try:
        cfg.unset(name, where=scope, reload=False)
    except CommandError as e:
        # we could also check if the option exists in the merged/effective
        # config first, but then we would have to make sure that there could
        # be no valid way of overriding a setting in a particular scope.
        # seems safer to do it this way
        if e.code == 5:
            return dict(
                status='error',
                action='unset_configuration',
                name=name,
                message=("configuration '%s' does not exist (%s)", name, e),
            )
    return dict(
        action='unset_configuration',
        name=name,
    )
