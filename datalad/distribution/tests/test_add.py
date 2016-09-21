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
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import CommandError
from datalad.tests.utils import ok_
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false
from datalad.tests.utils import assert_in
from datalad.tests.utils import serve_path_via_http
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
    assert_raises(FileNotInRepositoryError, ds.add,
                  opj(pardir, 'path', 'outside'))


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

    test_list_1 = ['test_annex.txt']
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
            result = ds.add('dir', to_git=arg[1], save=False, if_dirty='ignore')
        else:
            result = ds.add(arg[0], to_git=arg[1], save=False, if_dirty='ignore')
        # TODO eq_(result, arg[0])
        # added, but not committed:
        ok_(ds.repo.dirty)

        # get sets for comparison:
        annexed = set(ds.repo.get_annexed_files())
        indexed = set(ds.repo.get_indexed_files())
        # ignore the initial config file in index:
        indexed.remove('.datalad/config')
        if isinstance(arg[0], list):
            for x in arg[0]:
                unstaged.remove(x)
                staged.add(x)
        else:
            unstaged.remove(arg[0])
            staged.add(arg[0])

        # added, but nothing else was:
        eq_(staged, indexed)
        ok_(unstaged.isdisjoint(annexed))
        ok_(unstaged.isdisjoint(indexed))


@with_tree(**tree_arg)
def test_add_recursive(path):
    ds = Dataset(path)
    ds.create(force=True, save=False)
    ds.create('dir', force=True, if_dirty='ignore')
    ds.save("Submodule added.")

    # TODO: CommandError to something meaningful
    # fail without recursive:
    assert_raises(CommandError, ds.add, opj('dir', 'testindir'), recursive=False)
    # fail with recursion limit too low:
    assert_raises(CommandError, ds.add, opj('dir', 'testindir'),
                  recursive=True, recursion_limit=0)

    ds.add(opj('dir', 'testindir'), recursive=True)
    assert_in('testindir', Dataset(opj(path, 'dir')).repo.get_annexed_files())

    ds.add(opj('dir', 'testindir2'), recursive=True, to_git=True)
    assert_in('testindir2', Dataset(opj(path, 'dir')).repo.get_indexed_files())

    subds = ds.create('git-sub', no_annex=True)
    with open(opj(subds.path, 'somefile.txt'), "w") as f:
        f.write("bla bla")
    result = ds.add(opj('git-sub', 'somefile.txt'), recursive=True, to_git=False)
    eq_(result, [{'file': opj(subds.path, 'somefile.txt'),
                  'note': "no annex at %s" % subds.path,
                  'success': False}])


@with_tree(**tree_arg)
def test_relpath_add(path):
    ds = Dataset(path).create(force=True)
    with chpwd(opj(path, 'dir')):
        eq_(add('testindir', if_dirty='ignore')[0]['file'],
            opj('dir', 'testindir'))
        # and now add all
        add('..')
    # auto-save enabled
    assert_false(ds.repo.dirty)


@with_tree(tree={'file1.txt': 'whatever 1',
                 'file2.txt': 'whatever 2',
                 'file3.txt': 'whatever 3',
                 'file4.txt': 'whatever 4',
                 'file5.txt': 'whatever 5',
                 'file6.txt': 'whatever 6',
                 'file7.txt': 'whatever 7'})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_add_source(path, url, ds_dir):
    from os import listdir
    from datalad.support.network import RI

    urls = [RI(url + f) for f in listdir(path)]
    ds = Dataset(ds_dir).create()
    eq_(len(ds.repo.get_annexed_files()), 0)

    # add a remote source to git => fail:
    assert_raises(NotImplementedError, ds.add, source=urls[0], to_git=True)
    # annex add a remote source:
    ds.add(source=urls[0])
    eq_(len(ds.repo.get_annexed_files()), 1)

    # add two remote source an give local names:
    ds.add(path=['local1.dat', 'local2.dat'], source=urls[1:3])
    annexed = ds.repo.get_annexed_files()
    eq_(len(annexed), 3)
    assert_in('local1.dat', annexed)
    assert_in('local2.dat', annexed)

    # add a second source for one of them
    ds.add(path='local1.dat', source=urls[3])
    eq_(len(annexed), 3)
    whereis_dict = ds.repo.whereis('local1.dat', output='full')
    reg_urls = [whereis_dict[uuid]['urls'] for uuid in whereis_dict
                if not whereis_dict[uuid]['here']]
    eq_(len(reg_urls), 1)  # one remote for 'local1.dat', that is not "here"
    eq_({str(urls[1]), str(urls[3])},
        set(reg_urls[0]))

    # just to be sure compare to 'local2.dat':
    whereis_dict = ds.repo.whereis('local2.dat', output='full')
    reg_urls = [whereis_dict[uuid]['urls'] for uuid in whereis_dict
                if not whereis_dict[uuid]['here']]
    eq_(len(reg_urls), 1)  # one remote for 'local2.dat', that is not "here"
    eq_([urls[2]], reg_urls[0])

    # provide more paths than sources:
    # report failure on non-existing 'local4.dat':
    result = ds.add(path=['local3.dat', 'local4.dat'], source=urls[4])
    ok_(all([r['success'] is False and r['note'] == 'not found'
             for r in result if r['file'] == 'local4.dat']))

    with open(opj(ds.path, 'local4.dat'), 'w') as f:
        f.write('local4 content')

    ds.add(path=['local3.dat', 'local4.dat'], source=urls[4])
    annexed = ds.repo.get_annexed_files()
    eq_(len(annexed), 5)
    assert_in('local3.dat', annexed)
    assert_in('local4.dat', annexed)

    # 'local3.dat' has a remote source
    whereis_dict = ds.repo.whereis('local3.dat', output='full')
    reg_urls = [whereis_dict[uuid]['urls'] for uuid in whereis_dict
                if not whereis_dict[uuid]['here']]
    eq_(len(reg_urls), 1)  # one remote for 'local3.dat', that is not "here"
    eq_([urls[4]], reg_urls[0])

    # 'local4.dat' has no remote source
    whereis_dict = ds.repo.whereis('local4.dat', output='full')
    reg_urls = [whereis_dict[uuid]['urls'] for uuid in whereis_dict
                if not whereis_dict[uuid]['here']]
    eq_(len(reg_urls), 0)

    # provide more sources than paths:
    ds.add('local5.dat', source=urls[5:])
    annexed = ds.repo.get_annexed_files()
    assert_in('local5.dat', annexed)
    eq_(len(annexed), 5 + len(urls[5:]))

    # Note: local4.dat didn't come from an url,
    # but 'local1.dat' consumes two urls
    eq_(len(annexed), len(urls))
    # all files annexed (-2 for '.git' and '.datalad'):
    eq_(len(annexed), len(listdir(ds.path)) - 2)
