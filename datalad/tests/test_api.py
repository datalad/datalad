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
from nose.tools import assert_true, assert_false


def test_basic_setup():
    # the import alone will verify that all default values match their
    # constraints
    from datalad import api
    # random pick of something that should be there
    assert_true(hasattr(api, 'install'))
    assert_true(hasattr(api, 'test'))
    assert_true(hasattr(api, 'crawl'))
    # make sure all helper utilities do not pollute the namespace
    # and we end up only with __...__ attributes
    assert_false(list(filter(lambda s: s.startswith('_') and not re.match('__.*__', s), dir(api))))
