# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test foreach command"""

import sys

from datalad.distribution.dataset import Dataset
from datalad.tests.utils import (
    get_deeply_nested_structure,
    assert_in,
    assert_not_in,
    assert_greater,
    eq_,
    with_tempfile,
)


@with_tempfile(mkdir=True)
def check_basic_resilience(populator, path):
    ds = populator(path)
    kwargs = dict(recursive=True)

    res_external = ds.foreach(
        [sys.executable, '-c', 'from datalad.distribution.dataset import Dataset; ds=Dataset("."); print(ds.path)'],
        **kwargs)
    res_python = ds.foreach("ds.path", cmd_type='eval', **kwargs)

    # consistency checks
    eq_(len(res_external), len(res_python))

    # Test correct order for bottom-up vs top-down
    eq_([ds.path] + ds.subdatasets(result_xfm='paths', recursive=True, bottomup=False),
        [_['result'] for _ in res_python])

    eq_(ds.subdatasets(result_xfm='paths', recursive=True, bottomup=True) + [ds.path],
        [_['result'] for _ in ds.foreach("ds.path", bottomup=True, cmd_type='eval', **kwargs)])
    pass


def test_basic_resilience():
    yield check_basic_resilience, get_deeply_nested_structure


@with_tempfile(mkdir=True)
def test_python(path):
    ds = Dataset(path).create()
    res = ds.foreach("dir()", cmd_type='eval')
    eq_(len(res), 1)
    expected_variables = {'ds', 'pwd', 'refds'}
    eq_(expected_variables.intersection(res[0]['result']), expected_variables)
    # besides expected, there could be few more ATM, +5 arbitrarily just to test
    # that we are not leaking too much
    assert_greater(len(expected_variables) + 5, len(res[0]['result']))
    # but exec has no result
    res = ds.foreach("dir()", cmd_type='exec')
    assert_not_in('result', res[0])
    # but allows for more complete/interesting setups in which we could import modules etc
    res = ds.foreach('import sys; print("DIR: %s" % str(dir()))', output_streams='capture', cmd_type='exec')
    assert_in('ds', res[0]['stdout'])
    assert_in('sys', res[0]['stdout'])
    eq_(res[0]['stderr'], '')
