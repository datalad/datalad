# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test add action

"""

from os import pardir
from os.path import join as opj

from datalad.api import create
from datalad.api import add
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_in
from datalad.utils import chpwd

from ..dataset import Dataset


@with_tempfile(mkdir=True)
def test_add_insufficient_args(path):
    # no argument:
    assert_raises(InsufficientArgumentsError, add)
    # no `path`, no `source`:
    assert_raises(InsufficientArgumentsError, add, dataset=path)
    # not in a dataset, no dataset given:
    with chpwd(path):
        assert_raises(InsufficientArgumentsError, add, path="some")

    ds = Dataset(path)
    ds.create()
    assert_raises(ValueError, ds.add, opj(pardir, 'path', 'outside'))
    assert_raises(ValueError, ds.add, opj('not', 'existing'))


tree_arg = dict(tree={'test.txt': 'some',
                 'test_annex.txt': 'some annex',
                 'test1.dat': 'test file 1',
                 'test2.dat': 'test file 2',
                 'dir': {'testindir': 'someother',
                         'testindir2': 'none'}})


@with_tree(**tree_arg)
def test_add_files(path):
    ds = Dataset(path)
    ds.create(force=True)

    test_list_1 = ['test_annex.dat']
    test_list_2 = ['test.txt']
    test_list_3 = ['test1.dat', 'test2.dat']
    test_list_4 = [opj('dir', 'testindir'), opj('dir', 'testindir2')]
    all_files = test_list_1 + test_list_2 + test_list_3 + test_list_4
    unstaged = set(all_files)
    staged = set()

    for arg in [(test_list_1[0], False),
                (test_list_2[0], True),
                (test_list_3, False),
                (test_list_4, False)]:
        # special case 4: give the dir:
        if arg[0] == test_list_4:
            result = ds.add('dir', to_git=arg[1])
        else:
            result = ds.add(arg[0], to_git=arg[1])
        eq_(result, arg[0])
        # added, but not committed:
        ok_(ds.repo.dirty)

        # get sets for comparison:
        annexed = set(ds.repo.get_annexed_files())
        indexed = set(ds.repo.get_indexed_files())
        if isinstance(arg[0], list):
            for x in arg[0]:
                unstaged.remove(x)
            staged += set(arg[0])
        else:
            unstaged.remove(arg[0])
            staged += {arg[0]}

        # added, but nothing else was:
        ok_(staged.issubset(indexed if arg[1] else annexed))
        ok_(staged.isdisjoint(annexed if arg[1] else indexed))
        ok_(set(unstaged).isdisjoint(set(annexed)))
        ok_(set(unstaged).isdisjoint(set(indexed)))


@with_tree(**tree_arg)
def test_add_recursive(path):
    ds = Dataset(path)
    ds.create(force=True)
    ds.create_subdataset('dir', force=True)

    # fail without recursive:
    assert_raises(ValueError, ds.add, opj('dir', 'testindir'), recursive=False)
    # fail with recursion limit too low:
    assert_raises(ValueError, ds.add, opj('dir', 'testindir'),
                  recursive=True, recursion_limit=0)

    ds.add(opj('dir', 'testindir'), recursive=True)
    assert_in('testindir', Dataset(opj(path, 'dir')).repo.get_annexed_files())

    ds.add(opj('dir', 'testindir2'), recursive=True, to_git=True)
    assert_in('testindir2', Dataset(opj(path, 'dir')).repo.get_indexed_files())


def test_add_source():
    # ???
    raise SkipTest("TODO")
#
# source <=> path paired by order
#
# source => RI  => addurl
#
#             dataset=None,
#             path=None,
#             source=None,
#             to_git=False,
#             recursive=False,
#             recursion_limit=None,
#             git_opts=None,
#             annex_opts=None,
#             annex_add_opts=None





