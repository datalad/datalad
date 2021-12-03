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

from datalad.api import (
    Dataset,
    clone,
)
from datalad.consts import DATALAD_SPECIAL_REMOTE
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import (
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
def test_get_contentlocation(tdir):
    repo = AnnexRepo(tdir, create=True, init=True)
    repo.save('added file.dat', ['file.dat'])

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
def test_ensure_datalad_remote_init_and_enable_needed(path):
    from datalad.consts import DATALAD_SPECIAL_REMOTE
    ds = Dataset(path).create(force=True)
    repo = ds.repo
    assert_false(repo.get_remotes())
    ensure_datalad_remote(repo)
    assert_in(DATALAD_SPECIAL_REMOTE, repo.get_remotes())


@with_tempfile
def check_ensure_datalad_remote_maybe_enable(autoenable, path):
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


def test_ensure_datalad_remote_maybe_enable():
    yield check_ensure_datalad_remote_maybe_enable, False
    yield check_ensure_datalad_remote_maybe_enable, True
