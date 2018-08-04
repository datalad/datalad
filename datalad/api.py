# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

from datalad.coreapi import *


def _command_summary():
    # Import here to avoid polluting the datalad.api namespace.
    from collections import defaultdict
    from datalad.interface.base import alter_interface_docs_for_api
    from datalad.interface.base import get_api_name
    from datalad.interface.base import get_cmd_doc
    from datalad.interface.base import get_cmd_summaries
    from datalad.interface.base import get_interface_groups
    from datalad.interface.base import load_interface

    groups = get_interface_groups(include_plugins=True)
    grp_short_descriptions = defaultdict(list)
    for group, _, specs in sorted(groups, key=lambda x: x[1]):
        for spec in specs:
            intf = load_interface(spec)
            if intf is None:
                continue
            sdescr = getattr(intf, "short_description", None) or \
                alter_interface_docs_for_api(get_cmd_doc(intf)).split("\n")[0]
            grp_short_descriptions[group].append(
                (get_api_name(spec), sdescr))
    return "\n".join(get_cmd_summaries(grp_short_descriptions, groups))


__doc__ += "\n\n{}".format(_command_summary())


def _load_plugins():
    from datalad.plugin import _get_plugins
    from datalad.plugin import _load_plugin
    import re

    camel = re.compile(r'([a-z])([A-Z])')

    for pname, props in _get_plugins():
        pi = _load_plugin(props['file'], fail=False)
        if pi is None:
            continue
        globals()[camel.sub('\\1_\\2', pi.__name__).lower()] = pi.__call__


def _generate_extension_api():
    """Auto detect all available extensions and generate an API from them
    """
    from importlib import import_module
    from pkg_resources import iter_entry_points
    from .interface.base import get_api_name

    from datalad.dochelpers import exc_str
    import logging
    lgr = logging.getLogger('datalad.api')

    for entry_point in iter_entry_points('datalad.extensions'):
        try:
            lgr.debug(
                'Loading entrypoint %s from datalad.extensions for API building',
                entry_point.name)
            grp_descr, interfaces = entry_point.load()
            lgr.debug(
                'Loaded entrypoint %s from datalad.extensions',
                entry_point.name)
        except Exception as e:
            lgr.warning('Failed to load entrypoint %s: %s', entry_point.name, exc_str(e))
            continue

        for intfspec in interfaces:
            # turn the interface spec into an instance
            mod = import_module(intfspec[0])
            intf = getattr(mod, intfspec[1])
            api_name = get_api_name(intfspec)
            if api_name in globals():
                lgr.debug(
                    'Command %s from extension %s is replacing a previously loaded implementation',
                    api_name,
                    entry_point.name)
            globals()[api_name] = intf.__call__


_generate_extension_api()
_load_plugins()

# Be nice and clean up the namespace properly
del _load_plugins
del _generate_extension_api
del _command_summary
