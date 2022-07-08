# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..support.strings import apply_replacement_rules
from .utils_pytest import *


def test_apply_replacement_rules():
    # replacement rule should be at least 3 char long
    assert_raises(ValueError, apply_replacement_rules, '/', 'some')
    assert_raises(ValueError, apply_replacement_rules, ['/a/b', '/'], 'some')
    # and pattern should have the separator only twice
    assert_raises(ValueError, apply_replacement_rules, '/ab', 'some')
    assert_raises(ValueError, apply_replacement_rules, '/a/b/', 'some')

    eq_(apply_replacement_rules('/a/b', 'abab'), 'bbbb')
    eq_(apply_replacement_rules('/a/', 'abab'), 'bb')
    eq_(apply_replacement_rules(['/a/b'], 'abab'), 'bbbb')
    eq_(apply_replacement_rules(['/a/b', ',b,ab'], 'abab'), 'abababab')

    # with regular expression groups
    eq_(apply_replacement_rules(r'/st(.*)n(.*)$/\1-\2', 'string'), 'ri-g')
