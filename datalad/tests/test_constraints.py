# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
'''Unit tests for basic constraints functionality.'''


from datalad.tests.utils_pytest import (
    assert_equal,
    assert_raises,
)

from ..support import constraints as ct


def test_int():
    c = ct.EnsureInt()
    # this should always work
    assert_equal(c(7), 7)
    assert_equal(c(7.0), 7)
    assert_equal(c('7'), 7)
    assert_equal(c([7, 3]), [7, 3])
    # this should always fail
    assert_raises(ValueError, lambda: c('fail'))
    assert_raises(ValueError, lambda: c([3, 'fail']))
    # this will also fail
    assert_raises(ValueError, lambda: c('17.0'))
    assert_equal(c.short_description(), 'int')


def test_float():
    c = ct.EnsureFloat()
    # this should always work
    assert_equal(c(7.0), 7.0)
    assert_equal(c(7), 7.0)
    assert_equal(c('7'), 7.0)
    assert_equal(c([7.0, '3.0']), [7.0, 3.0])
    # this should always fail
    assert_raises(ValueError, lambda: c('fail'))
    assert_raises(ValueError, lambda: c([3.0, 'fail']))


def test_bool():
    c = ct.EnsureBool()
    # this should always work
    assert_equal(c(True), True)
    assert_equal(c(False), False)
    # all that results in True
    assert_equal(c('True'), True)
    assert_equal(c('true'), True)
    assert_equal(c('1'), True)
    assert_equal(c('yes'), True)
    assert_equal(c('on'), True)
    assert_equal(c('enable'), True)
    # all that results in False
    assert_equal(c('false'), False)
    assert_equal(c('False'), False)
    assert_equal(c('0'), False)
    assert_equal(c('no'), False)
    assert_equal(c('off'), False)
    assert_equal(c('disable'), False)
    # this should always fail
    assert_raises(ValueError, c, 0)
    assert_raises(ValueError, c, 1)


def test_str():
    c = ct.EnsureStr()
    # this should always work
    assert_equal(c('hello'), 'hello')
    assert_equal(c('7.0'), '7.0')
    # this should always fail
    assert_raises(ValueError, lambda: c(['ab']))
    assert_raises(ValueError, lambda: c(['a', 'b']))
    assert_raises(ValueError, lambda: c(('a', 'b')))
    # no automatic conversion attempted
    assert_raises(ValueError, lambda: c(7.0))
    assert_equal(c.short_description(), 'str')

def test_str_min_len():
    c = ct.EnsureStr(min_len=1)
    assert_equal(c('hello'), 'hello')
    assert_equal(c('h'), 'h')
    assert_raises(ValueError, c, '')

    c = ct.EnsureStr(min_len=2)
    assert_equal(c('hello'), 'hello')
    assert_raises(ValueError, c, 'h')


def test_none():
    c = ct.EnsureNone()
    # this should always work
    assert_equal(c(None), None)
    # instance of NoneDeprecated is also None
    assert_equal(c(ct.NoneDeprecated), None)
    # this should always fail
    assert_raises(ValueError, lambda: c('None'))
    assert_raises(ValueError, lambda: c([]))


def test_callable():
    c = ct.EnsureCallable()
    # this should always work
    assert_equal(c(range), range)
    assert_raises(ValueError, c, 'range')


def test_choice():
    c = ct.EnsureChoice('choice1', 'choice2', None)
    # this should always work
    assert_equal(c('choice1'), 'choice1')
    assert_equal(c(None), None)
    # this should always fail
    assert_raises(ValueError, lambda: c('fail'))
    assert_raises(ValueError, lambda: c('None'))


def test_keychoice():
    c = ct.EnsureKeyChoice(key='some', values=('choice1', 'choice2', None))
    assert_equal(c({'some': 'choice1'}), {'some': 'choice1'})
    assert_equal(c({'some': None}), {'some': None})
    assert_equal(c({'some': None, 'ign': 'ore'}), {'some': None, 'ign': 'ore'})
    assert_raises(ValueError, c, 'fail')
    assert_raises(ValueError, c, 'None')
    assert_raises(ValueError, c, {'nope': 'None'})
    assert_raises(ValueError, c, {'some': 'None'})
    assert_raises(ValueError, c, {'some': ('a', 'b')})


def test_range():
    c = ct.EnsureRange(min=3, max=7)
    # this should always work
    assert_equal(c(3.0), 3.0)

    # this should always fail
    assert_raises(ValueError, lambda: c(2.9999999))
    assert_raises(ValueError, lambda: c(77))
    assert_raises(TypeError, lambda: c('fail'))
    assert_raises(TypeError, lambda: c((3, 4)))
    # since no type checks are performed
    assert_raises(TypeError, lambda: c('7'))

    # Range doesn't have to be numeric
    c = ct.EnsureRange(min="e", max="qqq")
    assert_equal(c('e'), 'e')
    assert_equal(c('fa'), 'fa')
    assert_equal(c('qq'), 'qq')
    assert_raises(ValueError, c, 'a')
    assert_raises(ValueError, c, 'qqqa')


def test_listof():
    c = ct.EnsureListOf(str)
    assert_equal(c(['a', 'b']), ['a', 'b'])
    assert_equal(c(['a1', 'b2']), ['a1', 'b2'])
    assert_equal(c('a1 b2'), ['a1 b2'])


def test_tupleof():
    c = ct.EnsureTupleOf(str)
    assert_equal(c(('a', 'b')), ('a', 'b'))
    assert_equal(c(('a1', 'b2')), ('a1', 'b2'))
    assert_equal(c('a1 b2'), ('a1 b2',))


def test_constraints():
    # this should always work
    c = ct.Constraints(ct.EnsureFloat())
    assert_equal(c(7.0), 7.0)
    c = ct.Constraints(ct.EnsureFloat(), ct.EnsureRange(min=4.0))
    assert_equal(c(7.0), 7.0)
    # __and__ form
    c = ct.EnsureFloat() & ct.EnsureRange(min=4.0)
    assert_equal(c(7.0), 7.0)
    assert_raises(ValueError, c, 3.9)
    c = ct.Constraints(ct.EnsureFloat(), ct.EnsureRange(min=4), ct.EnsureRange(max=9))
    assert_equal(c(7.0), 7.0)
    assert_raises(ValueError, c, 3.9)
    assert_raises(ValueError, c, 9.01)
    # __and__ form
    c = ct.EnsureFloat() & ct.EnsureRange(min=4) & ct.EnsureRange(max=9)
    assert_equal(c(7.0), 7.0)
    assert_raises(ValueError, c, 3.99)
    assert_raises(ValueError, c, 9.01)
    # and reordering should not have any effect
    c = ct.Constraints(ct.EnsureRange(max=4), ct.EnsureRange(min=9), ct.EnsureFloat())
    assert_raises(ValueError, c, 3.99)
    assert_raises(ValueError, c, 9.01)


def test_altconstraints():
    # this should always work
    c = ct.AltConstraints(ct.EnsureFloat())
    assert_equal(c(7.0), 7.0)
    c = ct.AltConstraints(ct.EnsureFloat(), ct.EnsureNone())
    assert_equal(c.short_description(), '(float or None)')
    assert_equal(c(7.0), 7.0)
    assert_equal(c(None), None)
    # __or__ form
    c = ct.EnsureFloat() | ct.EnsureNone()
    assert_equal(c(7.0), 7.0)
    assert_equal(c(None), None)

    # this should always fail
    c = ct.Constraints(ct.EnsureRange(min=0, max=4), ct.EnsureRange(min=9, max=11))
    assert_raises(ValueError, c, 7.0)
    c = ct.EnsureRange(min=0, max=4) | ct.EnsureRange(min=9, max=11)
    assert_equal(c(3.0), 3.0)
    assert_equal(c(9.0), 9.0)
    assert_raises(ValueError, c, 7.0)
    assert_raises(ValueError, c, -1.0)


def test_both():
    # this should always work
    c = ct.AltConstraints(
        ct.Constraints(
            ct.EnsureFloat(),
            ct.EnsureRange(min=7.0, max=44.0)),
        ct.EnsureNone())
    assert_equal(c(7.0), 7.0)
    assert_equal(c(None), None)
    # this should always fail
    assert_raises(ValueError, lambda: c(77.0))

def test_type_str():
    assert_equal(ct._type_str((str,)), 'str')
    assert_equal(ct._type_str(str), 'str')
