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


def iter_extensions(load=False):
    """Iterate over all entrypoints of the 'datalad.extensions' group

    By default, iterates over all extensions. 'datalad.extensions.load'
    configuration item can be used to configure which specific
    extensions to consider. An explicitly set empty value avoids
    considering any extension.

    Logs a warning in case a requested extension is not available, or if
    an extension fails on load.

    Parameters
    ----------
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

    from datalad import cfg
    load_extensions_cfg = cfg.get('datalad.extensions.load', get_all=True)
    all_extensions = []
    if load_extensions_cfg == '':
        # empty value is an explicit way to disable loading any extension
        lgr.debug("Not considering any extensions as requested")
        return
    elif load_extensions_cfg is not None:
        from datalad.utils import ensure_iter
        load_extensions_cfg = ensure_iter(load_extensions_cfg, set)

    # We will do loading here to mimic prior behavior/logging better
    for ename, mod, eload in iter_entrypoints('datalad.extensions', load=False):
        all_extensions.append(ename)
        if not (load_extensions_cfg is None or ename in load_extensions_cfg):
            continue
        if load:
            try:
                yield ename, mod, eload()
            except Exception as e:
                ce = CapturedException(e)
                lgr.warning('Could not load extension %r: %s', el, ce)
        else:
            yield ename, mod, eload

    if load_extensions_cfg:
        for ext in load_extensions_cfg.difference(all_extensions):
            lgr.warning('Requested extension %r is not available', ext)


def load_extensions():
    """Load DataLad extensions entrypoints.

    A convenience and compatibility helper over
    :py:func:`datalad.support.entrypoints.iter_extensions`.
    """
    for _ in iter_extensions(load=True):
        pass
