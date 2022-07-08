# emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test no_annex"""


from os.path import join as opj

from datalad.api import (
    create,
    no_annex,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_repo_status,
    create_tree,
    eq_,
    known_failure_githubci_win,
    with_tempfile,
)
from datalad.utils import Path


@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_no_annex(path=None):
    ds = create(path)
    assert_repo_status(ds.path)
    create_tree(
        ds.path,
        {'code': {
            'inannex': 'content',
            'notinannex': 'othercontent'},
         'README': 'please'})
    # add inannex pre configuration
    ds.save(opj('code', 'inannex'))
    no_annex(pattern=['code/**', 'README'], dataset=ds.path)

    inannex = (ds.pathobj / 'code' / 'inannex')

    # add inannex and README post configuration
    ds.save([opj('code', 'notinannex'), 'README'])

    repo = ds.repo
    try:
        assert_repo_status(ds.path)
    except AssertionError:
        # If on an adjusted branch and notinannex's mtime is as recent or newer
        # than .git/index's, the clean filter runs on it when save() is called.
        # This leads to a racy failure until after git-annex's 424bef6b6
        # (smudge: check for known annexed inodes before checking
        # annex.largefiles, 2021-05-03).
        #
        # https://git-annex.branchable.com/forum/one-off_unlocked_annex_files_that_go_against_large/
        if repo.is_managed_branch() and repo.git_annex_version <= "8.20210428":
            assert_repo_status(ds.path, modified=[inannex])
            raise SkipTest("Known bug fixed in git-annex")
        raise

    # one is annex'ed, the other is not, despite no change in add call
    # importantly, also .gitattribute is not annexed
    eq_([opj('code', 'inannex')],
        [str(Path(p)) for p in repo.get_annexed_files()])
