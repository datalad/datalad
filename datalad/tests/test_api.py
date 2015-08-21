# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
'''Unit tests for Python API functionality.'''

from nose.tools import assert_true, assert_false


def test_basic_setup():
    # the import alone will verify that all default values match their
    # constraints
    from datalad import api
    # random pick of something that should be there
    assert_true(hasattr(api, 'create_collection'))
    # make sure all helper utilities do not pollute the namespace
    assert_false(hasattr(api, '_update_docstring'))
    assert_false(hasattr(api, '_interfaces'))
    assert_false(hasattr(api, '_get_interface_groups'))
