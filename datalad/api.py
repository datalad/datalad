# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

# Should have no spurious imports/definitions at the module level
from .distribution.dataset import Dataset


def _generate_func_api():
    """Auto detect all available interfaces and generate a function-based
       API from them
    """
    from importlib import import_module
    from inspect import isgenerator
    from collections import namedtuple
    from functools import wraps

    from .interface.base import get_interface_groups
    from .interface.base import get_api_name
    from .interface.base import get_allargs_as_kwargs

    def _kwargs_to_namespace(call, args, kwargs):
        """
        Given a __call__, args and kwargs passed, prepare a cmdlineargs-like
        thing
        """
        kwargs_ = get_allargs_as_kwargs(call, args, kwargs)
        # Get all arguments removing those possible ones used internally and
        # which shouldn't be exposed outside anyways
        [kwargs_.pop(k) for k in kwargs_ if k.startswith('_')]
        namespace = namedtuple("smth", kwargs_.keys())(**kwargs_)
        return namespace

    def call_gen(call, renderer):
        """Helper to generate a call_ for call, to use provided renderer"""

        @wraps(call)
        def call_(*args, **kwargs):
            ret1 = ret = call(*args, **kwargs)
            if isgenerator(ret):
                # At first I thought we might just rerun it for output
                # at the end, but that wouldn't work if command actually
                # has a side-effect, i.e. actually doing something
                # so we actually need to memoize all generated output and output
                # it instead
                from datalad.utils import saved_generator
                ret, ret1 = saved_generator(ret)

            renderer(ret, _kwargs_to_namespace(call, args, kwargs))
            return ret1

        # TODO: see if we could proxy the "signature" of function
        # call from the original one
        call_.__doc__ += \
            "\nNote\n----\n\n" \
            "This version of a function uses cmdline results renderer before " \
            "returning the result"
        return call_

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
