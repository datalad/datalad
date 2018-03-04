# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os

from .utils import (
    chpwd,
    get_dataset_root,
    with_tree,

    assert_raises,
    assert_equal,
)


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
    from datalad.support.gitrepo import check_git_configured
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
