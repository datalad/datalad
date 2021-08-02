# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
import os.path as op

from datalad.utils import get_home_envvars

from datalad.tests.utils import (
    assert_in,
    assert_raises,
    chpwd,
    get_dataset_root,
    ok_file_has_content,
    SkipTest,
    swallow_logs,
    with_tree,
)

from unittest.mock import patch


# verify that any target platform can deal with forward slashes
# as os.path.sep, regardless of its native preferences
@with_tree(tree={'subdir': {'testfile': 'testcontent'}})
def test_paths_with_forward_slashes(path):
    # access file with native absolute path spec
    print(path)
    ok_file_has_content(op.join(path, 'subdir', 'testfile'), 'testcontent')
    with chpwd(path):
        # native relative path spec
        ok_file_has_content(op.join('subdir', 'testfile'), 'testcontent')
        # posix relative path spec
        ok_file_has_content('subdir/testfile', 'testcontent')
    # abspath with forward slash path sep char
    ok_file_has_content(
        op.join(path, 'subdir', 'testfile').replace(op.sep, '/'),
        'testcontent')


#@with_tempfile(mkdir=True)
# with_tempfile dereferences tempdir, so does not trigger the failure
# on Yarik's laptop where TMPDIR=~/.tmp and ~/.tmp -> /tmp.
# with_tree in turn just passes that ~/.tmp/ directory
@with_tree(tree={})
def test_not_under_git(path):
    from datalad.distribution.dataset import require_dataset
    dsroot = get_dataset_root(path)
    assert dsroot is None, "There must be no dataset above tmp %s. Got: %s" % (path, dsroot)
    with chpwd(path):
        # And require_dataset must puke also
        assert_raises(
            Exception,
            require_dataset,
            None, check_installed=True, purpose='test'
        )


def test_no_empty_http_proxy():
    # in __init__ we might prune http_proxy if it is empty, so it must not be
    # empty if present
    assert os.environ.get('http_proxy', 'default')
    assert os.environ.get('https_proxy', 'default')


@with_tree(tree={})
def test_git_config_warning(path):
    if 'GIT_AUTHOR_NAME' in os.environ:
        raise SkipTest("Found existing explicit identity config")
    with chpwd(path), \
            patch.dict('os.environ', get_home_envvars(path)), \
            swallow_logs(new_level=30) as cml:
        # no configs in that empty HOME
        from datalad.api import Dataset
        from datalad.config import ConfigManager
        # reach into the class and disable the "checked" flag that
        # has already been tripped before we get here
        ConfigManager._checked_git_identity = False
        Dataset(path).config.reload()
        assert_in("configure Git before", cml.out)
