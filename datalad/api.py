# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

import datalad
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

    groups = get_interface_groups()
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


if not datalad.in_librarymode():
    __doc__ += "\n\n{}".format(_command_summary())


def _generate_extension_api():
    """Auto detect all available extensions and generate an API from them
    """
    from datalad.support.entrypoints import iter_entrypoints
    from datalad.interface.base import (
        get_api_name,
        load_interface,
    )

    import logging
    lgr = logging.getLogger('datalad.api')

    for ename, _, (grp_descr, interfaces) in iter_entrypoints(
            'datalad.extensions', load=True):
        for intfspec in interfaces:
            # turn the interface spec into an instance
            intf = load_interface(intfspec[:2])
            if intf is None:
                lgr.error(
                    "Skipping unusable command interface '%s.%s' from extension %r",
                    intfspec[0], intfspec[1], ename)
                continue
            api_name = get_api_name(intfspec)
            if api_name in globals():
                lgr.debug(
                    'Command %s from extension %s is replacing a previously loaded implementation',
                    api_name,
                    ename)
            globals()[api_name] = intf.__call__


_generate_extension_api()

# Be nice and clean up the namespace properly
del _generate_extension_api
del _command_summary
