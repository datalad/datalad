# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test remove command"""

import os.path as op

from datalad.tests.utils import (
    assert_in_results,
    assert_result_count,
    assert_true,
    assert_false,
    get_deeply_nested_structure,
    with_tempfile,
)


@with_tempfile
def test_remove_file(path):
    # see docstring for test data structure
    ds = get_deeply_nested_structure(path)
    gitfile = op.join("subdir", "git_file.txt")

    assert_true((ds.pathobj / gitfile).exists())
    res = ds.remove(gitfile)
    assert_result_count(res, 3)
    # git file needs no dropping
    assert_in_results(
        res,
        action='drop',
        path=str(ds.pathobj / gitfile),
        status='notneeded',
        type='file',
    )
    # removed from working tree
    assert_in_results(
        res,
        action='remove',
        path=str(ds.pathobj / gitfile),
        status='ok',
        type='file',
    )
    # saved removal in dataset
    assert_in_results(
        res,
        action='save',
        path=ds.path,
        type='dataset',
        status='ok',
    )
    assert_false((ds.pathobj / gitfile).exists())
