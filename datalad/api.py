# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

from .distribution.dataset import Dataset


def _generate_func_api():
    """Auto detect all available interfaces and generate a function-based
       API from them
    """
    from importlib import import_module
    from .interface.base import update_docstring_with_parameters
    from .interface.base import get_interface_groups
    from .interface.base import get_api_name
    from .interface.base import alter_interface_docs_for_api

    for grp_name, grp_descr, interfaces in get_interface_groups():
        for intfspec in interfaces:
            # turn the interface spec into an instance
            mod = import_module(intfspec[0], package='datalad')
            intf = getattr(mod, intfspec[1])
            spec = getattr(intf, '_params_', dict())

            # FIXME no longer using an interface class instance
            # convert the parameter SPEC into a docstring for the function
            update_docstring_with_parameters(
                intf.__call__, spec,
                prefix=alter_interface_docs_for_api(
                    intf.__doc__),
                suffix=alter_interface_docs_for_api(
                    intf.__call__.__doc__)
            )
            globals()[get_api_name(intfspec)] = intf.__call__


def _fix_datasetmethod_docs():
    """Fix up dataset methods docstrings which didn't get proper docs
    """
    from six import PY2
    for attr in dir(Dataset):
        try:
            func = getattr(Dataset, attr)
            orig_func = getattr(func, '__orig_func__')
        except AttributeError:
            continue
        if PY2:
            func = func.__func__
        orig__doc__ = func.__doc__
        if orig__doc__ and orig__doc__.strip():  # pragma: no cover
            raise RuntimeError(
                "No meaningful docstring should have been assigned before now. Got %r"
                % orig__doc__
            )
        func.__doc__ = orig_func.__doc__


# Invoke above helpers
_generate_func_api()
_fix_datasetmethod_docs()

# Be nice and clean up the namespace properly
del _generate_func_api
del _fix_datasetmethod_docs
