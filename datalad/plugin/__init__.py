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

from datalad import cfg
from datalad.support.param import Parameter
from datalad.support.constraints import EnsureNone
from datalad.distribution.dataset import EnsureDataset
from datalad.distribution.dataset import datasetmethod
from datalad.distribution.dataset import require_dataset
from datalad.dochelpers import exc_str

from datalad.interface.base import Interface
from datalad.interface.utils import build_doc
from datalad.ui import ui

lgr = logging.getLogger('datalad.plugin')

argspec = re.compile(r'^([a-zA-z][a-zA-Z0-9_]*)=(.*)$')


def _get_plugins():
    # search three locations:
    # 1. datalad installation
    # 2. system config
    # 3. user config
    # plugins in a latter location replace plugins in an earlier one
    # this allows users/admins to replace datalad's own plugins with
    # different ones
    locations = (
        dirname(__file__),
        cfg.obtain('datalad.locations.system-plugins'),
        cfg.obtain('datalad.locations.user-plugins'))
    return {basename(e)[9:-3]: {'file': e}
            for plugindir in locations
            for e in glob(opj(plugindir, 'dlplugin_*.py'))}


def _load_plugin(filepath):
    locals = {}
    globals = {}
    exec(compile(open(filepath, "rb").read(), filepath, 'exec'), globals, locals)
    if not len(locals):
        raise ValueError(
            "loading plugin '%s' did not create at least one object" % filepath)
    elif len(locals) > 1 and 'datalad_plugin' not in locals:
        raise ValueError(
            "loading plugin '%s' did not yield a 'datalad_plugin' symbol, found: %s",
            filepath, locals.keys())
    if len(locals) == 1:
        return locals.values()[0]
    else:
        return locals['datalad_plugin']


@build_doc
class Plugin(Interface):
    """Export a dataset to another representation
    """
    # XXX prevent common args from being added to the docstring
    _no_eval_results = True

    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to export. If
            no dataset is given, an attempt is made to identify the dataset
            based on the current working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
        plugin=Parameter(
            args=("plugin",),
            nargs='*',
            metavar=('NAME', 'ARG=VAL'),
            doc="""label of the type or format the dataset shall be exported
            to."""),
        showpluginhelp=Parameter(
            args=('-H', '--show-plugin-help',),
            dest='showpluginhelp',
            action='store_true',
            doc="""show help for a specific plugin"""),
    )

    @staticmethod
    @datasetmethod(name='plugin')
    def __call__(plugin=None, dataset=None, showpluginhelp=False, **kwargs):
        plugins = _get_plugins()
        if not plugin:
            for plname, plinfo in sorted(plugins.items(), key=lambda x: x[0]):
                synopsis = None
                try:
                    with open(plinfo['file']) as plf:
                        for line in plf:
                            if line.startswith('#PLUGINSYNOPSIS:'):
                                synopsis = line[17:].strip()
                                break
                except Exception as e:
                    ui.message('{} [BROKEN] {}'.format(plname, exc_str(e)))
                    continue
                if synopsis:
                    ui.message('{} -- {}'.format(plname, synopsis))
                else:
                    ui.message('{} [no synopsis]'.format(plname))
            return
        if isinstance(plugin, (list, tuple)):
            args = plugin[1:]
            plugin = plugin[0]
        if plugin not in plugins:
            raise ValueError("unknown plugin '{}', available: {}".format(
                plugin, ','.join(plugins.keys())))
        if args:
            # we got some arguments in the plugin spec, parse them and add to
            # kwargs
            for arg in args:
                parsed = argspec.match(arg)
                if parsed is None:
                    raise ValueError("invalid plugin argument: '{}'".format(arg))
                argname, argval = parsed.groups()
                kwargs[argname] = argval
        plugin_call = _load_plugin(plugins[plugin]['file'])

        if showpluginhelp:
            ui.message(
                plugin_call.__doc__
                if plugin_call.__doc__
                else 'This plugin has no documentation')
            return

        return
        # TODO
        # - filter kwargs by function signature?
        ds = require_dataset(dataset, check_installed=True, purpose='plugin')
        # call the plugin, either with the argv array from the cmdline call
        # or directly with the kwargs
        if 'datalad_unparsed_args' in kwargs:
            result = pluginmod._datalad_plugin_call(
                ds, argv=kwargs['datalad_unparsed_args'], output=output)
        else:
            result = pluginmod._datalad_plugin_call(
                ds, output=output, **kwargs)
        return (pluginmod, result)

    @staticmethod
    def result_renderer_cmdline(res, args):
        if res is None:
            return
        pluginmod, result = res
        if args.showpluginhelp:
            # the function that prints the help was returned as result
            if not hasattr(pluginmod, '_datalad_get_plugin_help'):
                lgr.error("plugin '{}' does not provide help".format(pluginmod))
                return
            replacement = []
            help = pluginmod._datalad_get_plugin_help()
            if isinstance(help, tuple):
                help, replacement = help
            if replacement:
                for in_s, out_s in replacement:
                    help = help.replace(in_s, out_s + ' ' * max(0, len(in_s) - len(out_s)))
            print(help)
            return
        # TODO call exporter function (if any)
