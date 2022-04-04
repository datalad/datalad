# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad core API exposing essential command used by other DataLad commands"""

# Should have no spurious imports/definitions at the module level
from .distribution.dataset import Dataset


def _generate_func_api():
    """Auto detect all available interfaces and generate a function-based
       API from them
    """
    from importlib import import_module

    # load extensions requested by configuration
    import datalad
    if datalad.get_apimode() == 'python':
        # only do this in Python API mode, because the CLI main
        # will have done this already
        from datalad.support.entrypoints import load_extensions
        load_extensions()

    from .interface.base import get_interface_groups
    from .interface.base import get_api_name

    for grp_name, grp_descr, interfaces in get_interface_groups():
        for intfspec in interfaces:
            # turn the interface spec into an instance
            mod = import_module(intfspec[0], package='datalad')
            intf = getattr(mod, intfspec[1])
            api_name = get_api_name(intfspec)
            globals()[api_name] = intf.__call__


# Invoke above helper
_generate_func_api()

# Be nice and clean up the namespace properly
del _generate_func_api
