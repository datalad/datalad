# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Python DataLad API exposing user-oriented commands (also available via CLI)"""

# Should have no spurious imports/definitions at the module leve
from .distribution.dataset import Dataset


def _generate_func_api():
    """Auto detect all available interfaces and generate a function-based
       API from them
    """
    from importlib import import_module
    from inspect import isgenerator
    from collections import namedtuple
    from collections import OrderedDict
    from functools import wraps

    from datalad import cfg

    from .interface.base import update_docstring_with_parameters
    from .interface.base import get_interface_groups
    from .interface.base import get_api_name
    from .interface.base import alter_interface_docs_for_api

    def _kwargs_to_namespace(call, args, kwargs):
        """
        Given a __call__, args and kwargs passed, prepare a cmdlineargs-like
        thing
        """
        from inspect import getargspec
        argspec = getargspec(call)
        defaults = argspec.defaults
        nargs = len(argspec.args)
        assert (nargs >= len(defaults))
        # map any args to their name
        argmap = list(zip(argspec.args[:len(args)], args))
        # map defaults of kwargs to their names (update below)
        argmap += list(zip(argspec.args[-len(defaults):], defaults))
        kwargs_ = OrderedDict(argmap)
        # update with provided kwarg args
        kwargs_.update(kwargs)
        assert (nargs == len(kwargs_))
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

    always_render = cfg.obtain('datalad.api.alwaysrender')
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
            # And the one with '_' suffix which would use cmdline results
            # renderer
            if hasattr(intf, 'result_renderer_cmdline'):
                intf__ = call_gen(intf.__call__, intf.result_renderer_cmdline)
                globals()[get_api_name(intfspec) + '_'] = intf__
                if always_render:
                    globals()[get_api_name(intfspec)] = intf__


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
