# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test result handling"""

from datalad.interface.utils import generic_result_renderer
from datalad.tests.utils_pytest import (
    assert_in,
    swallow_outputs,
)
from datalad.utils import on_windows


def test_generic_result_renderer():
    # a bunch of bad cases of results
    testcases = [
        # an empty result will surface
        ({}, ['<action-unspecified>(<status-unspecified>)']),
        # non-standard status makes it out again
        (dict(status='funky'), ['<action-unspecified>(funky)']),
        # just an action result is enough to get some output
        (dict(action='funky'), ['funky(<status-unspecified>)']),
        # a plain path produces output, although
        (dict(path='funky'), ['<action-unspecified>(<status-unspecified>): funky']),
        # plain type makes it through
        (dict(type='funky'),
         ['<action-unspecified>(<status-unspecified>): (funky)']),
        # plain message makes it through
        (dict(message='funky', error_message='extra-funky'),
         ['<action-unspecified>(<status-unspecified>): [funky] [extra-funky]']),
    ]
    if on_windows:
        testcases.extend([
            # if relpath'ing is not possible, takes the path verbatim
            (dict(path='C:\\funky', refds='D:\\medina'),
             ['<action-unspecified>(<status-unspecified>): C:\\funky']),
        ])
    else:
        testcases.extend([
            (dict(path='/funky/cold/medina', refds='/funky'),
             ['<action-unspecified>(<status-unspecified>): cold/medina']),
        ])
    for result, contenttests in testcases:
        with swallow_outputs() as cmo:
            generic_result_renderer(result)
            for ctest in contenttests:
                assert_in(ctest, cmo.out)
