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
from datalad.interface.utils import build_doc
from datalad.interface.utils import eval_results
from datalad.ui import ui

lgr = logging.getLogger('datalad.plugin')

argspec = re.compile(r'^([a-zA-z][a-zA-Z0-9_]*)=(.*)$')


def _get_plugins():
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
    by the respective plugin are passed to the plugin.

    Like in most commands, a dedicated ``--dataset`` option is supported that
    can be used to identify a specific dataset to be passed to a plugin's
    ``dataset`` argument.


    *Writing plugins*

    Plugins are written in Python. In order for DataLad to be able to find
    them, plugins need to be placed in one of the supported locations described
    above. Plugin file names have to match the pattern::

      dlplugin_<pluginname>.py

    Plugin source files must define a function named::

      datalad_plugin

    This function is executed as the plugin. It can have any number of
    arguments (positional, or keyword arguments with defaults), or none at
    all. All arguments, except ``dataset`` must expect any value to
    be a string.

    The plugin function must be self-contained, i.e. all needed imports
    of definitions must be done within the body of the function.

    The doc string of the plugin function is displayed when the plugin
    documentation is requested. A plugin file should contain a line
    starting with the string '#PLUGINSYNOPSIS:' anywhere in its source code.
    The text on this line (after the prefix) is displayed as the plugin
    synopsis in the plugin overview list.

    Plugin functions must either return None or yield their results as
    generator. Results are DataLad status dictionaries. There are no
    constraints on the number and nature of result properties. However,
    conventions exists and must be followed for compatibility with the
    result evaluation and rendering performed by DataLad.

    The following keys must exist:

    "status"
        {'ok', 'notneeded', 'impossible', 'error'}

    "action"
        label for the action performed by the plugin. In many cases this
        could be the plugin's name.

    The following keys should exists if possible:

    "path"
        absolute path to a result on the file system

    "type"
        label indicating the nature of a result (e.g. 'file', 'dataset',
        'directory', etc.)

    "message"
        string message annotating the result, particularly important for
        non-ok results. This can be a tuple with 'logging'-style string
        expansion.

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
                            if line.startswith('#PLUGINSYNOPSIS:'):
                                synopsis = line[17:].strip()
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
        # now check the plugin signature and filter out all unsupported args
        plugin_args, _, _, _ = inspect.getargspec(plugin_call)
        # always overwrite the dataset arg if one is needed
        if 'dataset' in plugin_args:
            kwargs['dataset'] = require_dataset(
                dataset if dataset else curdir,
                check_installed=True,
                purpose='handover to plugin')

        # call as a generator
        for res in plugin_call(**{k: v for k, v in kwargs.items() if k in plugin_args}):
            # enforce standard regardless of what plugin did
            res['refds'] = dataset
            if 'logger' not in res:
                # make sure we have a logger
                res['logger'] = lgr
            yield res
