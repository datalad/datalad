# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Core utilities"""

import logging
import sys

from datalad.support.exceptions import CapturedException

lgr = logging.getLogger('datalad.core.utils')


def iter_entrypoints(group, load=True):
    lgr.debug("Processing entrypoints")

    if sys.version_info < (3, 10):
        from importlib_metadata import entry_points
    else:
        from importlib.metadata import entry_points
    for ep in entry_points(group=group):
        if not load:
            yield ep
            continue

        try:
            lgr.debug('Loading entrypoint %s from %s', ep.name, group)
            yield ep.load()
            lgr.debug('Loaded entrypoint %s from %s', ep.name, group)
        except Exception as e:
            ce = CapturedException(e)
            lgr.warning(
                'Failed to load entrypoint %s from %s: %s',
                entry_point.name, group, ce)
            continue
    lgr.debug("Done processing entrypoints")


def import_interface(modname, clsname):
    from importlib import import_module
    mod = import_module(modname)
    intf = getattr(mod, clsname)
    return intf

