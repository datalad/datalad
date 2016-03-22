# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test install action

"""

import os
from os.path import join as opj
from ..dataset import Dataset
from datalad.api import install
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import ok_, eq_, assert_false, assert_equal, assert_true
from datalad.tests.utils import with_tempfile, assert_in, with_tree, with_testrepos
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module


@with_tempfile
def test_create(path):
    # only needs a path
    ds = install(path)
    assert_true(ds.is_installed())

    # TODO: create within another ds


@with_tree(tree={'test.txt': 'some',
                 'dir': {'testindir': 'someother',
                         'testindir2': 'none'}})
def test_install_files(path):
    ds = install(path)
    # install a single file
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install it again, should given same result
    eq_(ds.install('test.txt'), opj(path, 'test.txt'))
    # install multiple files in a dir
    eq_(ds.install('dir', recursive=True),
        [opj(path, 'dir', 'testindir'),
         opj(path, 'dir', 'testindir2')])
    # TODO: check git


@with_testrepos(flavors=['local-url', 'network'])  # + 'local'?
def test_install_dataset_from(url):
    raise SkipTest("TODO")


def test_install_subdataset():
    raise SkipTest("TODO")


def test_install_into_dataset():
    raise SkipTest("TODO")


# TODO: Is there a way to test result renderer?

