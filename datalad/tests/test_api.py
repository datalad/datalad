# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
'''Unit tests for Python API functionality.'''

import re

from datalad.tests.utils_pytest import (
    SkipTest,
    assert_false,
    assert_in,
    assert_true,
    eq_,
)
from datalad.utils import get_sig_param_names


def test_basic_setup():
    # the import alone will verify that all default values match their
    # constraints
    from datalad import api

    # random pick of something that should be there
    assert_true(hasattr(api, 'install'))
    assert_true(hasattr(api, 'create'))
    # make sure all helper utilities do not pollute the namespace
    # and we end up only with __...__ attributes
    assert_false(list(filter(lambda s: s.startswith('_') and not re.match('__.*__', s), dir(api))))

    assert_in('Parameters', api.Dataset.install.__doc__)
    assert_in('Parameters', api.Dataset.create.__doc__)


def _test_consistent_order_of_args(intf, spec_posargs):
    f = getattr(intf, '__call__')
    args, kw_only = get_sig_param_names(f, ('pos_any', 'kw_only'))
    # now verify that those spec_posargs are first among args
    # TODO*: The last odd one left from "plugins" era. Decided to leave alone
    if intf.__name__ in ('ExtractMetadata',):
        return

    # if we had used * to instruct to have keyword only args, then all
    # args should actually be matched entirely
    if kw_only:
        # "special cases/exclusions"
        if intf.__name__ == 'CreateSiblingRia':
            # -s|--name is a mandatory option (for uniformity), so allowed to be used as posarg #2
            eq_(set(args), spec_posargs.union({'name'}))
        else:
            eq_(set(args), spec_posargs)
    else:
        # and if no kw_only -- only those which are known to be positional
        eq_(set(args[:len(spec_posargs)]), spec_posargs)
        if spec_posargs:
            # and really -- we should not even get here if there are some spec_posargs --
            # new interfaces should use * to separate pos args from kwargs per our now
            # accepted design doc:
            # http://docs.datalad.org/en/latest/design/pos_vs_kw_parameters.html
            assert False


# TODO?: make parametric again instead of invoking
def test_consistent_order_of_args():
    from importlib import import_module

    from datalad.interface.base import get_interface_groups

    for grp_name, grp_descr, interfaces in get_interface_groups():
        for intfspec in interfaces:
            # turn the interface spec into an instance
            mod = import_module(intfspec[0], package='datalad')
            intf = getattr(mod, intfspec[1])
            spec = getattr(intf, '_params_', dict())

            # figure out which of the specs are "positional"
            spec_posargs = {
                name
                for name, param in spec.items()
                if param.cmd_args and not param.cmd_args[0].startswith('-')
            }
            # we have information about positional args
            _test_consistent_order_of_args(intf, spec_posargs)
