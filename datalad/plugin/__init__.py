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
from os.path import join as opj, basename, dirname

import datalad
from datalad import cfg
from datalad.dochelpers import exc_str

lgr = logging.getLogger('datalad.plugin')

BUILTIN_PLUGINS_PATH = dirname(__file__)
magic_plugin_symbol = '__datalad_plugin__'


def _get_plugins():
    lgr.debug("Discovering plugins")
    locations = (
        BUILTIN_PLUGINS_PATH,
        cfg.obtain('datalad.locations.system-plugins'),
        cfg.obtain('datalad.locations.user-plugins'))
    for plugindir in locations:
        for e in glob(opj(plugindir, '[!_]*.py')):
            yield basename(e)[:-3], {'file': e}


def _load_plugin(filepath, fail=True):
    from datalad.utils import import_module_from_file
    try:
        mod = import_module_from_file(filepath, pkg=datalad)
    except Exception as e:
        # any exception means full stop
        raise ValueError('plugin at {} is broken: {}'.format(
            filepath, exc_str(e)))
    # TODO check all symbols whether they are derived from Interface
    if not hasattr(mod, magic_plugin_symbol):
        msg = "loading plugin '%s' did not yield a '%s' symbol, found: %s", \
              filepath, magic_plugin_symbol, dir(mod)
        if fail:
            raise ValueError(*msg)
        else:
            lgr.debug(*msg)
            return
    return getattr(mod, magic_plugin_symbol)
