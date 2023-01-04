# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test foreach-dataset command"""

import os.path as op
import sys
from pathlib import Path

import pytest

from datalad.api import create
from datalad.distribution.dataset import Dataset
from datalad.tests.utils_pytest import (
    assert_false,
    assert_greater,
    assert_in,
    assert_not_in,
    assert_status,
    eq_,
    get_deeply_nested_structure,
    ok_clean_git,
    swallow_outputs,
    with_tempfile,
)


def _without_command(results):
    """A helper to tune up results so that they lack 'command'
    which is guaranteed to differ between different cmd types
    """
    out = []
    for r in results:
        r = r.copy()
        r.pop('command')
        out.append(r)
    return out


@with_tempfile(mkdir=True)
def check_basic_resilience(populator, path=None):
    ds = populator(path)
    ds.save()
    kwargs = dict(recursive=True)

    res_external = ds.foreach_dataset(
        [sys.executable, '-c', 'from datalad.distribution.dataset import Dataset; ds=Dataset("."); print(ds.path)'],
        **kwargs)
    res_python = ds.foreach_dataset("ds.path", cmd_type='eval', **kwargs)

    # a sample python function to pass to foreach
    def get_path(ds, **kwargs):
        return ds.path

    res_python_func = ds.foreach_dataset(get_path, **kwargs)

    assert_status('ok', res_external)
    assert_status('ok', res_python)

    # consistency checks
    eq_(len(res_external), len(res_python))
    eq_(len(res_external), len(res_python_func))
    eq_(_without_command(res_python), _without_command(res_python_func))

    # Test correct order for bottom-up vs top-down
    topdown_dss = [ds.path] + ds.subdatasets(result_xfm='paths', bottomup=False, **kwargs)
    eq_(topdown_dss, [_['result'] for _ in res_python])

    bottomup_dss = ds.subdatasets(result_xfm='paths', recursive=True, bottomup=True) + [ds.path]
    eq_(bottomup_dss, [_['result'] for _ in ds.foreach_dataset("ds.path", bottomup=True, cmd_type='eval', **kwargs)])

    # more radical example - cleanup
    # Make all datasets dirty
    for d in bottomup_dss:
        (Path(d) / "dirt").write_text("")
    res_clean = ds.foreach_dataset(['git', 'clean', '-f'], jobs=10, **kwargs)
    assert_status('ok', res_clean)
    # no dirt should be left
    for d in bottomup_dss:
        assert_false((Path(d) / "dirt").exists())

    if populator is get_deeply_nested_structure:
        ok_clean_git(ds.path, index_modified=[ds.pathobj / 'subds_modified'])
    else:
        ok_clean_git(ds.path)


@pytest.mark.parametrize("populator", [
    # empty dataset
    create,
    # ver much not empty dataset
    get_deeply_nested_structure,
])
def test_basic_resilience(populator):
    check_basic_resilience(populator)


@with_tempfile(mkdir=True)
def check_python_eval(cmd, path):
    ds = Dataset(path).create()
    res = ds.foreach_dataset(cmd, cmd_type='eval')
    eq_(len(res), 1)
    expected_variables = {'ds', 'pwd', 'refds'}
    eq_(expected_variables.intersection(res[0]['result']), expected_variables)
    # besides expected, there could be few more ATM, +5 arbitrarily just to test
    # that we are not leaking too much
    assert_greater(len(expected_variables) + 5, len(res[0]['result']))


@with_tempfile(mkdir=True)
def check_python_exec(cmd, path):
    ds = Dataset(path).create()
    sub = ds.create('sub')  # create subdataset for better coverage etc

    # but exec has no result
    res = ds.foreach_dataset(cmd, cmd_type='exec')
    assert_not_in('result', res[0])

    # but allows for more complete/interesting setups in which we could import modules etc
    cmd2 = 'import os, sys; print(f"DIR: {os.linesep.join(dir())}")'
    with swallow_outputs() as cmo:
        res1 = ds.foreach_dataset(cmd2, output_streams='capture', cmd_type='exec')
        assert_in('ds', res1[0]['stdout'])
        assert_in('sys', res1[0]['stdout'])
        eq_(res1[0]['stderr'], '')
        # default renderer for each dataset
        assert cmo.out.startswith(f'foreach-dataset(ok): {path}')
        assert f'foreach-dataset(ok): {sub.path}' in cmo.out

    with swallow_outputs() as cmo:
        res2 = ds.foreach_dataset(cmd2, output_streams='relpath', cmd_type='exec')
        # still have the same res
        assert res1 == res2
        # but we have "fancier" output
        assert cmo.out.startswith(f'DIR: ')
        # 2nd half should be identical to 1st half but with lines prefixed with sub/ path
        lines = cmo.out.splitlines()
        half = len(lines) // 2
        assert [op.join('sub', l) for l in lines[:half]] == lines[half:]
        assert 'foreach-dataset(ok)' not in cmo.out


def test_python():
    check_python_eval("dir()")
    check_python_exec("dir()")

    def dummy_dir(*args, **kwargs):
        """Ensure that we pass all placeholders as kwargs"""
        assert not args
        return kwargs

    check_python_eval(dummy_dir)  # direct function invocation
