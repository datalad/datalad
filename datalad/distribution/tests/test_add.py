# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test add action

"""

import logging
from os import pardir
from os.path import join as opj

from datalad.api import create
from datalad.api import add
from datalad.api import install
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import CommandError
from datalad.tests.utils import ok_
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_file_under_git
from datalad.tests.utils import eq_
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_false
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import SkipTest
from datalad.utils import chpwd
from datalad.utils import _path_

from ..dataset import Dataset


@with_tempfile(mkdir=True)
def test_add_insufficient_args(path):
    # no argument:
    assert_raises(InsufficientArgumentsError, add)
    # no `path`, no `source`:
    assert_raises(InsufficientArgumentsError, add, dataset=path)
    with chpwd(path):
        res = add(path="some", on_failure='ignore')
        assert_status('impossible', res)
    ds = Dataset(opj(path, 'ds'))
    ds.create()
    # non-existing path outside
    assert_status('impossible', ds.add(opj(path, 'outside'), on_failure='ignore'))
    # existing path outside
    with open(opj(path, 'outside'), 'w') as f:
        f.write('doesnt matter')
    assert_status('impossible', ds.add(opj(path, 'outside'), on_failure='ignore'))


tree_arg = dict(tree={'test.txt': 'some',
                      'test_annex.txt': 'some annex',
                      'test1.dat': 'test file 1',
                      'test2.dat': 'test file 2',
                      'dir': {'testindir': 'someother',
                              'testindir2': 'none'},
                      'dir2': {'testindir3': 'someother3'}})


@with_tree(**tree_arg)
def test_add_files(path):
    ds = Dataset(path)
    ds.create(force=True)
    ok_(ds.repo.dirty)

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
            result = ds.add('dir', to_git=arg[1], save=False)
        else:
            result = ds.add(arg[0], to_git=arg[1], save=False, result_xfm='relpaths',
                            return_type='item-or-list')
            # order depends on how annex processes it, so let's sort
            eq_(sorted(result), sorted(arg[0]))
        # added, but not committed:
        ok_(ds.repo.dirty)

        # get sets for comparison:
        annexed = set(ds.repo.get_annexed_files())
        indexed = set(ds.repo.get_indexed_files())
        # ignore the initial config file in index:
        indexed.remove(opj('.datalad', 'config'))
        indexed.remove(opj('.datalad', '.gitattributes'))
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
    subds = ds.create('dir', force=True)
    ok_(subds.repo.dirty)

    # no subds without recursive:
    ds.add('.', recursive=False)
    ok_(subds.repo.dirty)
    # nosubds with recursion limit too low:
    ds.add('.', recursive=True, recursion_limit=0)
    ok_(subds.repo.dirty)

    # add while also instructing annex to add in parallel 2 jobs (smoke testing
    # for that effect ATM)
    added1 = ds.add(opj('dir', 'testindir'), jobs=2)
    # added to annex, so annex output record
    assert_result_count(
        added1, 1,
        path=opj(ds.path, 'dir', 'testindir'), action='add',
        annexkey='MD5E-s9--3f0f870d18d6ba60a79d9463ff3827ea',
        status='ok')
    assert_in('testindir', Dataset(opj(path, 'dir')).repo.get_annexed_files())
    ok_(subds.repo.dirty)

    # this tests wants to add the content to subdir before updating the
    # parent, now we can finally say that explicitly
    added2 = ds.add('dir/.', to_git=True)
    # added to git, so parsed git output record
    assert_result_count(
        added2, 1,
        path=opj(ds.path, 'dir', 'testindir2'), action='add',
        message='non-large file; adding content to git repository',
        status='ok')
    assert_in('testindir2', Dataset(opj(path, 'dir')).repo.get_indexed_files())
    ok_clean_git(ds.path)

    # We used to fail to add to pure git repository, but now it should all be
    # just fine
    subds = ds.create('git-sub', no_annex=True)
    with open(opj(subds.path, 'somefile.txt'), "w") as f:
        f.write("bla bla")
    result = ds.add(opj('git-sub', 'somefile.txt'), to_git=False)
    # adds the file
    assert_result_count(
        result, 1,
        action='add', path=opj(subds.path, 'somefile.txt'), status='ok')
    # but also saves both datasets
    assert_result_count(
        result, 2,
        action='save', status='ok', type='dataset')


@with_tree(**tree_arg)
def test_relpath_add(path):
    ds = Dataset(path).create(force=True)
    with chpwd(opj(path, 'dir')):
        eq_(add('testindir')[0]['path'],
            opj(ds.path, 'dir', 'testindir'))
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
    raise SkipTest('functionality is not supported ATM')
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


@with_tree(**tree_arg)
@with_tempfile(mkdir=True)
def test_add_subdataset(path, other):
    subds = create(opj(path, 'dir'), force=True)
    ds = create(path, force=True)
    ok_(subds.repo.dirty)
    ok_(ds.repo.dirty)
    assert_not_in('dir', ds.subdatasets(result_xfm='relpaths'))
    # without a base dataset the next is interpreted as "add everything
    # in subds to subds"
    add(subds.path)
    ok_clean_git(subds.path)
    assert_not_in('dir', ds.subdatasets(result_xfm='relpaths'))
    # but with a base directory we add the dataset subds as a subdataset
    # to ds
    ds.add(subds.path)
    assert_in('dir', ds.subdatasets(result_xfm='relpaths'))
    #  create another one
    other = create(other)
    # install into superdataset, but don't add
    other_clone = install(source=other.path, path=opj(ds.path, 'other'))
    ok_(other_clone.is_installed)
    assert_not_in('other', ds.subdatasets(result_xfm='relpaths'))
    # now add, it should pick up the source URL
    ds.add('other')
    # and that is why, we can reobtain it from origin
    ds.uninstall('other')
    ok_(other_clone.is_installed)
    ds.get('other')
    ok_(other_clone.is_installed)


@with_tree(tree={
    'file.txt': 'some text',
    'empty': '',
    '.gitattributes': '* annex.largefiles=(not(mimetype=text/*))'}
)
def test_add_mimetypes(path):
    # XXX apparently there is symlinks dereferencing going on while deducing repo
    #    type there!!!! so can't use following invocation  -- TODO separately
    import os
    path = os.path.realpath(path)  # yoh gives up for now
    ds = Dataset(path).create(force=True)
    ds.repo.add('.gitattributes')
    ds.repo.commit('added attributes to git explicitly')
    # now test that those files will go into git/annex correspondingly
    __not_tested__ = ds.add(['file.txt', 'empty'])
    ok_clean_git(path)
    # Empty one considered to be  application/octet-stream  i.e. non-text
    ok_file_under_git(path, 'empty', annexed=True)
    ok_file_under_git(path, 'file.txt', annexed=False)
