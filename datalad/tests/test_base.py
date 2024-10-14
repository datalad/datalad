# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os
import os.path as op
import sys
from unittest.mock import patch

from datalad.cmd import (
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_in,
    assert_raises,
    chpwd,
    get_dataset_root,
    ok_file_has_content,
    swallow_logs,
    with_tree,
)
from datalad.utils import get_home_envvars


# verify that any target platform can deal with forward slashes
# as os.path.sep, regardless of its native preferences
@with_tree(tree={'subdir': {'testfile': 'testcontent'}})
def test_paths_with_forward_slashes(path=None):
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
def test_not_under_git(path=None):
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
def test_git_config_warning(path=None):
    if 'GIT_AUTHOR_NAME' in os.environ:
        raise SkipTest("Found existing explicit identity config")

    # Note: An easier way to test this, would be to just set GIT_CONFIG_GLOBAL
    # to point somewhere else. However, this is not supported by git before
    # 2.32. Hence, stick with changed HOME in this test, but be sure to unset a
    # possible GIT_CONFIG_GLOBAL in addition.

    patched_env = os.environ.copy()
    patched_env.pop('GIT_CONFIG_GLOBAL', None)
    patched_env.update(get_home_envvars(path))
    with chpwd(path), \
            patch.dict('os.environ', patched_env, clear=True), \
            swallow_logs(new_level=30) as cml:
        out = WitlessRunner().run(
            [sys.executable, '-c', 'import datalad'],
            protocol=StdOutErrCapture)
        assert_in("configure Git before", out['stderr'])
