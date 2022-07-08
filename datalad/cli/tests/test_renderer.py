from datalad.tests.utils_pytest import eq_

from ..renderer import (
    NA_STRING,
    nadict,
    nagen,
)


def test_nagen():
    na = nagen()
    eq_(str(na), NA_STRING)
    eq_(repr(na), 'nagen()')
    assert na.unknown is na
    assert na['unknown'] is na

    eq_(str(nagen('-')), '-')


def test_nadict():
    d = nadict({1: 2})
    eq_(d[1], 2)
    eq_(str(d[2]), NA_STRING)



