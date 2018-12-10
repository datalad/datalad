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

from .utils import (
    chpwd,
    get_dataset_root,
    with_tree,
    swallow_logs,

    assert_raises,
    assert_equal,
    assert_in,
    ok_file_has_content,
)
from datalad.support.gitrepo import check_git_configured

from mock import patch


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


def test_git_config_fixture():
    # in the setup_package we setup a new HOME with custom config
    if 'GIT_HOME' not in os.environ:
        assert_equal(
            check_git_configured(),
            {
                'user.name': 'DataLad Tester',
                'user.email': 'test@example.com'
             }
        )
    else:
        # we pick up the ones in the 'GIT_HOME' which might differ
        assert_equal(sorted(check_git_configured()), ['user.email', 'user.name'])


def test_no_empty_http_proxy():
    # in __init__ we might prune http_proxy if it is empty, so it must not be
    # empty if present
    assert os.environ.get('http_proxy', 'default')
    assert os.environ.get('https_proxy', 'default')


@with_tree(tree={})
def test_git_config_warning(path):
    with chpwd(path), \
            patch.dict('os.environ', {'HOME': path}), \
            swallow_logs(new_level=30) as cml:
        # no configs in that empty HOME
        assert_equal(check_git_configured(), {})
        assert_in("configure git first", cml.out)
