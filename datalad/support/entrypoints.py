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

lgr = logging.getLogger('datalad.support.entrypoints')


def iter_entrypoints(group, load=False):
    """Iterate over all entrypoints of a given group

    Parameters
    ----------
    group: str
      Name of the entry point group to iterator over, such as
      'datalad.extensions'.
    load: bool, optional
      Whether to execute the entry point loader internally in a
      protected manner that only logs a possible exception and emits
      a warning, but otherwise skips over "broken" entrypoints.
      If False, the loader callable is returned unexecuted.

    Yields
    -------
    (name, module, load(r|d))
      The first item in each yielded tuple is the entry point name (str).
      The second is the name of the module that contains the entry point
      (str). The type of the third items depends on the load parameter.
      It is either a callable that can be used to load the entrypoint
      (this is the default behavior), or the outcome of executing the
      entry point loader.
    """
    lgr.debug("Processing entrypoints")

    if sys.version_info < (3, 10):
        # 3.10 is when it was no longer provisional
        from importlib_metadata import entry_points
    else:
        from importlib.metadata import entry_points
    for ep in entry_points(group=group):
        if not load:
            yield ep.name, ep.module, ep.load
            continue

        try:
            lgr.debug('Loading entrypoint %s from %s', ep.name, group)
            yield ep.name, ep.module, ep.load()
            lgr.debug('Loaded entrypoint %s from %s', ep.name, group)
        except Exception as e:
            ce = CapturedException(e)
            lgr.warning(
                'Failed to load entrypoint %s from %s: %s',
                ep.name, group, ce)
            continue
    lgr.debug("Done processing entrypoints")


def load_extensions():
    """Load entrypoint for any configured extension package

    Log a warning in case a requested extension is not available, or if
    a requested extension fails on load.

    Extensions to load are taken from the 'datalad.extensions.load'
    configuration item.
    """
    from datalad import cfg
    load_extensions = cfg.get('datalad.extensions.load', get_all=True)
    if load_extensions:
        from datalad.utils import ensure_list
        exts = {
            ename: eload
            for ename, _, eload in iter_entrypoints('datalad.extensions')
        }
        for el in ensure_list(load_extensions):
            if el not in exts:
                lgr.warning('Requested extension %r is not available', el)
                continue
            try:
                exts[el]()
            except Exception as e:
                ce = CapturedException(e)
                lgr.warning('Could not load extension %r: %s', el, ce)
