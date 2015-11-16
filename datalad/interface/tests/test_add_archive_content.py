# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for add-archive-content command

"""

__docformat__ = 'restructuredtext'

from os import chdir, getcwd
from os.path import basename, exists, isdir, join as opj

from mock import patch
from nose.tools import assert_is_instance, assert_not_in
from six.moves.urllib.parse import urlparse

from ...utils import swallow_logs
from ...tests.utils import ok_, eq_, assert_cwd_unchanged, assert_raises, \
    with_testrepos, with_tempfile, ok_startswith, assert_in, ok_clean_git
from ...support.handle import Handle
from ...support.collection import Collection
from ...consts import REPO_STD_META_FILE, HANDLE_META_DIR

from ...support.annexrepo import AnnexRepo
from ...api import add_archive_content
from ...tests.utils import with_tree, serve_path_via_http, ok_file_under_git
from ...utils import chpwd

# within top directory
# archive is in subdirectory -- adding in the same (or different) directory

tree1args = dict(
    tree=(
        ('1.tar.gz', (
            ('1 f.txt', '1 f load'),
            ('d', (('1d', ''),)), )),
        ('d1', (('1.tar.gz', (
                    ('2 f.txt', '2 f load'),
                    ('d2', (
                        ('2d', ''),)
                     )),),),),
    )
)

@assert_cwd_unchanged(ok_to_chdir=True)
@with_tree(**tree1args)
@serve_path_via_http()
def _test_add_archive_content(path, url):
    chpwd(path)
    # TODO we need to be able to pass path
    assert_raises(RuntimeError, add_archive_content, "nonexisting.tar.gz") # no repo yet

    repo = AnnexRepo(path, create=True)
    assert_raises(ValueError, add_archive_content, "nonexisting.tar.gz")

    # and by default it just does it, evrything goes to annex
    repo_ = add_archive_content('1.tar.gz')
    eq_(repo.path, repo_.path)
    ok_(exists('1'))
    ok_file_under_git('1', '1 f.txt', annexed=True)
    ok_file_under_git(opj('1', 'd', '1d'), annexed=True)


_test_add_archive_content.tags = ['integration']
