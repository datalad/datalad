# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test add action

"""
from os.path import join as opj, abspath, relpath, pardir, isabs, isdir, \
    exists, islink, sep, realpath


from ..dataset import Dataset
from datalad.api import create
from datalad.api import add
from datalad.api import install
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileInGitError

from nose.tools import ok_, eq_, assert_false
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_equal, assert_true
from datalad.tests.utils import SkipTest
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import swallow_logs


def test_insufficient_args():
    assert_raises(InsufficientArgumentsError, add)


@with_tree(tree={'test.txt': 'some',
                 'dir': {'testindir': 'someother',
                         'testindir2': 'none'}})
def test_install_files(path):
    ds = create(path)
    # install a single file
    eq_(ds.add('test.txt'), opj(path, 'test.txt'))
    # install it again, should given same result
    eq_(ds.add('test.txt'), opj(path, 'test.txt'))
    # install multiple files in a dir
    eq_(ds.add('dir'),
        [opj(path, 'dir', 'testindir'),
         opj(path, 'dir', 'testindir2')])
    # TODO: check git


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_into_dataset(source, top_path):
    ds = create(top_path)
    subds = ds.add(path="sub", source=source)
    assert_true(isdir(opj(subds.path, '.git')))
    ok_(subds.is_installed())
    # sub is clean:
    ok_clean_git(subds.path, annex=False)
    # top is not:
    assert_raises(AssertionError, ok_clean_git, ds.path, annex=False)
    # unless committed the subds should not show up in the parent
    # this is the same behavior that 'git submodule status' implements
    assert_not_in('sub', ds.get_subdatasets())
    ds.save('addsub')
    assert_in('sub', ds.get_subdatasets())


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_subdataset(src, path):
    # get the superdataset:
    ds = install(path=path, source=src)

    # subdataset not installed:
    subds = Dataset(opj(path, 'sub1'))
    assert_false(subds.is_installed())

    # install it:
    ds.add('sub1')
    assert_true(isdir(opj(subds.path, '.git')))

    ok_(subds.is_installed())
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    assert_equal(set(subds.repo.get_indexed_files()),
                 {'test.dat', 'INFO.txt', 'test-annex.dat'})

    # Now the obnoxious install an annex file within not yet
    # initialized repository!
    with swallow_outputs():  # progress bar
        ds.add(opj('sub2', 'test-annex.dat'))
    subds2 = Dataset(opj(path, 'sub2'))
    assert(subds2.is_installed())
    assert(subds2.repo.file_has_content('test-annex.dat'))
    # we shouldn't be able silently ignore attempt to provide source while
    # "installing" file under git
    assert_raises(FileInGitError, ds.add, opj('sub2', 'INFO.txt'), source="http://bogusbogus")
