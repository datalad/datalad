# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create action

"""



import os
import shutil
from os.path import join as opj, abspath, isdir
from os.path import exists
from os.path import realpath

from mock import patch

from ..dataset import Dataset
from datalad.api import create
from datalad.api import install
from datalad.consts import DATASETS_TOPURL
from datalad.distribution.install import get_containing_subdataset
from datalad.distribution.install import _get_installationpath_from_url
from datalad.distribution.install import _get_git_url_from_source
from datalad.utils import chpwd
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import FileInGitError
from datalad.support.gitrepo import GitRepo
from datalad.support.gitrepo import GitCommandError
from datalad.cmd import Runner

from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner

from nose.tools import ok_, eq_, assert_false
from datalad.tests.utils import with_tempfile, assert_in, with_tree,\
    with_testrepos, assert_equal, assert_true
from datalad.tests.utils import SkipTest
from datalad.tests.utils import assert_cwd_unchanged, skip_if_on_windows
from datalad.tests.utils import assure_dict_from_str, assure_list_from_str
from datalad.tests.utils import ok_generator
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import ok_startswith
from datalad.tests.utils import skip_if_no_module
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import swallow_logs


@with_tempfile
def test_create_curdir(path):
    with chpwd(path, mkdir=True):
        create()
    ds = Dataset(path)
    ok_(ds.is_installed())

    # simple addition to create and add a subdataset
    # TODO: Move this test

    subds = Dataset(opj(path, "some/what/deeper")).create(add_to_super=True)
    ok_(isinstance(subds, Dataset))
    ok_(subds.is_installed())
    ok_clean_git(subds.path, annex=True)

    # subdataset is known to superdataset:
    assert_in("some/what/deeper", ds.get_subdatasets())
    # but wasn't committed:
    ok_(ds.repo.dirty)

    ok_(subds.get_superdataset() == ds)


@with_tempfile
def test_create(path):
    # install doesn't create anymore
    assert_raises(RuntimeError, Dataset(path).install)
    # only needs a path
    ds = create(path, no_annex=True)
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)
    ok_(isinstance(ds.repo, GitRepo))

    ds = create(path, description="funny")
    ok_(ds.is_installed())
    ok_clean_git(path, annex=False)
    # any dataset created from scratch has an annex
    ok_(isinstance(ds.repo, AnnexRepo))
    # check default backend
    assert_equal(
        ds.repo.repo.config_reader().get_value("annex", "backends"),
        'MD5E')
    runner = Runner()
    # check description in `info`
    cmd = ['git-annex', 'info']
    cmlout = runner.run(cmd, cwd=path)
    assert_in('funny [here]', cmlout[0])


    sub_path_1 = opj(path, "sub")
    subds1 = create(sub_path_1)
    ok_(subds1.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    # wasn't installed into ds:
    assert_not_in("sub", ds.get_subdatasets())

    # add it inplace:
    added_subds = ds.install("sub", source=sub_path_1)
    ok_(added_subds.is_installed())
    ok_clean_git(sub_path_1, annex=False)
    eq_(added_subds.path, sub_path_1)
    assert_true(isdir(opj(added_subds.path, '.git')))
    ok_(ds.repo.dirty)  # not committed yet
    assert_in("sub", ds.get_subdatasets())
    ds.save("added submodule")
    # now for reals
    open(opj(added_subds.path, 'somecontent'), 'w').write('stupid')
    # next one will auto-annex the new file
    added_subds.save('initial commit', auto_add_changes=True)
    # as the submodule never entered the index, even this one won't work
    # ben: it currently does, since 'save' was changed to call git add as well
    # as git annex add. Therefore outcommenting. Please review, whether this is
    # intended behaviour. I think so.
    # MIH: Now it need a flag to perform this (see #546)
    ds.save('submodule with content', auto_add_changes=True)
    # assert_not_in("sub", ds.get_subdatasets())
    # # we need to install the submodule again in the parent
    # # an actual final commit is not required
    # added_subds = ds.install("sub", source=sub_path_1)
    assert_in("sub", ds.get_subdatasets())

    # next one directly created within ds:
    sub_path_2 = opj(path, "sub2")
    # installing something without a source into a dataset at a path
    # that has no present content should not work
    assert_raises(InsufficientArgumentsError, install, ds, path=sub_path_2)