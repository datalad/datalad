# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""

__docformat__ = 'restructuredtext'

import logging
from glob import glob
import re
from os.path import join as opj, basename, dirname
from os import curdir
import inspect

from datalad import cfg
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.dochelpers import exc_str

from datalad.interface.base import Interface
from datalad.interface.base import dedent_docstring
from datalad.interface.base import build_doc
from datalad.interface.utils import eval_results
from datalad.ui import ui

lgr = logging.getLogger('datalad.plugin')

argspec = re.compile(r'^([a-zA-z][a-zA-Z0-9_]*)=(.*)$')


def _get_plugins():
    locations = (
        dirname(__file__),
        cfg.obtain('datalad.locations.system-plugins'),
        cfg.obtain('datalad.locations.user-plugins'))
    return {basename(e)[:-3]: {'file': e}
            for plugindir in locations
            for e in glob(opj(plugindir, '[!_]*.py'))}


def _load_plugin(filepath):
    locals = {}
    globals = {}
    try:
        exec(compile(open(filepath, "rb").read(),
                     filepath, 'exec'),
             globals,
             locals)
    except Exception as e:
        # any exception means full stop
        raise ValueError('plugin at {} is broken: {}'.format(
            filepath, exc_str(e)))
    if not len(locals) or 'dlplugin' not in locals:
        raise ValueError(
            "loading plugin '%s' did not yield a 'dlplugin' symbol, found: %s",
            filepath, locals.keys() if len(locals) else None)
    return locals['dlplugin']


@build_doc
class Plugin(Interface):
    """Generic plugin interface

    Using this command, arbitrary DataLad plugins can be executed. Plugins in
    three different locations are available

    1. official plugins that are part of the local DataLad installation

    2. system-wide plugins, location configuration::

         datalad.locations.system-plugins

    3. user-supplied plugins, location configuration::

         datalad.locations.user-plugins

    Identically named plugins in latter location replace those in locations
    searched before.

    *Using plugins*

    A list of all available plugins can be obtained by running this command
    without arguments::

      datalad plugin

    To run a specific plugin, provide the plugin name as an argument::

      datalad plugin export_tarball

    A plugin may come with its own documentation which can be displayed upon
    request::

      datalad plugin export_tarball -H

    If a plugin supports (optional) arguments, they can be passed to the plugin
    as key=value pairs with the name and the respective value of an argument,
    e.g.::

      datalad plugin export_tarball output=myfile

    Any number of arguments can be given. Only arguments with names supported
    by the respective plugin are passed to the plugin. If unsupported arguments
    are given, a warning is issued.

    When an argument is given multiple times, all values are passed as a list
    to the respective argument (order of value matches the order in the
    plugin call)::

      datalad plugin fancy_plugin input=this input=that

    Like in most commands, a dedicated --dataset option is supported that
    can be used to identify a specific dataset to be passed to a plugin's
    ``dataset`` argument. If a plugin requires such an argument, and no
    dataset was given, and none was found in the current working directory,
    the plugin call will fail. A dataset argument can also be passed alongside
    all other plugin arguments without using --dataset.

    """
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset for the plugin to operate on
            If no dataset is given, but a plugin take a dataset as an argument,
            an attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        plugin=Parameter(
            args=("plugin",),
            nargs='*',
            metavar='PLUGINSPEC',
            doc="""plugin name plus an optional list of `key=value` pairs with
            arguments for the plugin call"""),
        showpluginhelp=Parameter(
            args=('-H', '--show-plugin-help',),
            dest='showpluginhelp',
            action='store_true',
            doc="""show help for a particular"""),
        showplugininfo=Parameter(
            args=('--show-plugin-info',),
            dest='showplugininfo',
            action='store_true',
            doc="""show additional information in plugin overview (e.g. plugin file
            location"""),
    )

    @staticmethod
    @datasetmethod(name='plugin')
    @eval_results
    def __call__(plugin=None, dataset=None, showpluginhelp=False, showplugininfo=False, **kwargs):
        plugins = _get_plugins()
        if not plugin:
            max_name_len = max(len(k) for k in plugins.keys())
            for plname, plinfo in sorted(plugins.items(), key=lambda x: x[0]):
                spacer = ' ' * (max_name_len - len(plname))
                synopsis = None
                try:
                    with open(plinfo['file']) as plf:
                        for line in plf:
                            if line.startswith('"""'):
                                synopsis = line.strip().strip('"').strip()
                                break
                except Exception as e:
                    ui.message('{}{} [BROKEN] {}'.format(
                        plname, spacer, exc_str(e)))
                    continue
                if synopsis:
                    msg = '{}{} - {}'.format(
                        plname, spacer, synopsis)
                else:
                    msg = '{}{} [no synopsis]'.format(plname, spacer)
                if showplugininfo:
                    msg = '{} ({})'.format(msg, plinfo['file'])
                ui.message(msg)
            return
        args = None
        if isinstance(plugin, (list, tuple)):
            args = plugin[1:]
            plugin = plugin[0]
        if plugin not in plugins:
            raise ValueError("unknown plugin '{}', available: {}".format(
                plugin, ','.join(plugins.keys())))
        user_supplied_args = set()
        if args:
            # we got some arguments in the plugin spec, parse them and add to
            # kwargs
            for arg in args:
                if isinstance(arg, tuple):
                    # came from python item-style
                    argname, argval = arg
                else:
                    parsed = argspec.match(arg)
                    if parsed is None:
                        raise ValueError("invalid plugin argument: '{}'".format(arg))
                    argname, argval = parsed.groups()
                if argname in kwargs:
                    # argument was seen at least once before -> make list
                    existing_val = kwargs[argname]
                    if not isinstance(existing_val, list):
                        existing_val = [existing_val]
                    existing_val.append(argval)
                    argval = existing_val
                kwargs[argname] = argval
                user_supplied_args.add(argname)
        plugin_call = _load_plugin(plugins[plugin]['file'])

        if showpluginhelp:
            # we don't need special docs for the cmdline, standard python ones
            # should be comprehensible enough
            ui.message(
                dedent_docstring(plugin_call.__doc__)
                if plugin_call.__doc__
                else 'This plugin has no documentation')
            return

        #
        # argument preprocessing
        #
        # check the plugin signature and filter out all unsupported args
        plugin_args, _, _, arg_defaults = inspect.getargspec(plugin_call)
        supported_args = {k: v for k, v in kwargs.items() if k in plugin_args}
        excluded_args = user_supplied_args.difference(supported_args.keys())
        if excluded_args:
            lgr.warning('ignoring plugin argument(s) %s, not supported by plugin',
                        excluded_args)
        # always overwrite the dataset arg if one is needed
        if 'dataset' in plugin_args:
            supported_args['dataset'] = require_dataset(
                # use dedicated arg if given, also anything the came with the plugin args
                # or curdir as the last resort
                dataset if dataset else kwargs.get('dataset', curdir),
                # note 'dataset' arg is always first, if we have defaults for all args
                # we have a default for 'dataset' to -> it is optional
                check_installed=len(arg_defaults) != len(plugin_args),
                purpose='handover to plugin')

        # call as a generator
        for res in plugin_call(**supported_args):
            if not res:
                continue
            if dataset:
                # enforce standard regardless of what plugin did
                res['refds'] = getattr(dataset, 'path', dataset)
            elif 'refds' in res:
                # no base dataset, results must not have them either
                del res['refds']
            if 'logger' not in res:
                # make sure we have a logger
                res['logger'] = lgr
            yield res
