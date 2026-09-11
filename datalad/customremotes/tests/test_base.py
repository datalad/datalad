# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for the base of our custom remotes"""


from os.path import isabs
from uuid import uuid4

import pytest

from datalad.api import (
    Dataset,
    clone,
)
from datalad.consts import DATALAD_SPECIAL_REMOTE
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_in,
    assert_not_in,
    assert_raises,
    known_failure_githubci_win,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path

from ..archives import ArchiveAnnexCustomRemote
from ..base import (
    ensure_datalad_remote,
    init_datalad_remote,
)


# PermissionError: [WinError 32] The process cannot access the file because it is being used by another process:
@known_failure_githubci_win
@with_tree(tree={'file.dat': ''})
def test_get_contentlocation(tdir=None):
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.add('file.dat')
    repo.commit('added file.dat')

    # TODO contentlocation would come with eval_availability=True
    key = repo.get_file_annexinfo('file.dat')['key']
    cr = ArchiveAnnexCustomRemote(None, path=tdir)
    key_path = cr.get_contentlocation(key, absolute=False)
    assert not isabs(key_path)
    key_path_abs = cr.get_contentlocation(key, absolute=True)
    assert isabs(key_path_abs)
    assert cr._contentlocations == {key: key_path}
    repo.drop('file.dat', options=['--force'])
    assert not cr.get_contentlocation(key, absolute=True)


def test_ensure_datalad_remote_unkown_remote():
    with assert_raises(ValueError):
        ensure_datalad_remote("doesn't matter", "unknown")


@with_tempfile
def test_ensure_datalad_remote_init_and_enable_needed(path=None):
    from datalad.consts import DATALAD_SPECIAL_REMOTE
    ds = Dataset(path).create(force=True)
    repo = ds.repo
    assert_false(repo.get_remotes())
    ensure_datalad_remote(repo)
    assert_in(DATALAD_SPECIAL_REMOTE, repo.get_remotes())


@pytest.mark.parametrize("autoenable", [False, True])
@with_tempfile
def test_ensure_datalad_remote_maybe_enable(path=None, *, autoenable):
    path = Path(path)
    ds_a = Dataset(path / "a").create(force=True)
    init_datalad_remote(ds_a.repo, DATALAD_SPECIAL_REMOTE,
                        autoenable=autoenable)

    ds_b = clone(source=ds_a.path, path=path / "b")
    repo = ds_b.repo
    if not autoenable:
        assert_not_in("datalad", repo.get_remotes())
    ensure_datalad_remote(repo)
    assert_in("datalad", repo.get_remotes())


@with_tempfile
def test_ensure_datalad_remote_uuid_mismatch(path=None):
    # Regression test: a dataset can have the special remote already
    # configured (in git-annex's remote.log) under a uuid other than the
    # one currently hard-coded in DATALAD_SPECIAL_REMOTES_UUIDS -- e.g. a
    # dataset created before a fixed uuid was adopted for it.  In that case
    # the uuid-based lookup in ensure_datalad_remote would not find it,
    # and it would try (and fail) to `initremote` a duplicate, since
    # git-annex itself identifies special remotes by name too and refuses:
    #   "There is already a special remote named ..."
    path = Path(path)
    legacy_uuid = str(uuid4())
    ds_a = Dataset(path / "a").create(force=True)
    # configure with a uuid distinct from DATALAD_SPECIAL_REMOTES_UUIDS
    ds_a.repo.init_remote(
        DATALAD_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'autoenable=false',
         'externaltype=%s' % DATALAD_SPECIAL_REMOTE,
         'uuid=%s' % legacy_uuid])

    ds_b = clone(source=ds_a.path, path=path / "b")
    repo = ds_b.repo
    assert_not_in(DATALAD_SPECIAL_REMOTE, repo.get_remotes())
    # must not raise despite the uuid mismatch
    ensure_datalad_remote(repo)
    assert_in(DATALAD_SPECIAL_REMOTE, repo.get_remotes())

    # A direct, repeated init_datalad_remote() call (e.g. triggered by
    # other code that did not go through the same uuid-mismatch-aware
    # lookup) must likewise not fail with git-annex's "already a special
    # remote" error, but fall back to enabling the existing one -- and that
    # fallback must still apply the given options via enableremote, so
    # flip autoenable to confirm it actually took effect rather than being
    # silently dropped.
    assert_equal(
        repo.get_special_remotes()[legacy_uuid]["autoenable"], "false")
    init_datalad_remote(repo, DATALAD_SPECIAL_REMOTE, autoenable=True)
    assert_equal(
        repo.get_special_remotes()[legacy_uuid]["autoenable"], "true")
