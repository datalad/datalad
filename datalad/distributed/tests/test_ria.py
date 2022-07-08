"""Test workflow (pieces) for RIA stores"""

from datalad.api import (
    Dataset,
    clone,
)
from datalad.tests.utils_pytest import (
    DEFAULT_REMOTE,
    assert_equal,
    assert_result_count,
    assert_true,
    has_symlink_capability,
    skip_if,
    skip_if_on_windows,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path


@skip_if_on_windows  # currently all tests re RIA/ORA don't run on windows
@skip_if(cond=not has_symlink_capability(),
         msg="skip testing ephemeral clone w/o symlink capabilities")
@with_tree({'file1.txt': 'some',
            'sub': {'other.txt': 'other'}})
@with_tempfile
@with_tempfile
def test_ephemeral(ds_path=None, store_path=None, clone_path=None):

    dspath = Path(ds_path)
    store = Path(store_path)
    file_test =  Path('file1.txt')
    file_testsub = Path('sub') / 'other.txt'


    # create the original dataset
    ds = Dataset(dspath)
    ds.create(force=True)
    ds.save()

    # put into store:
    ds.create_sibling_ria("ria+{}".format(store.as_uri()), "riastore",
                          new_store_ok=True)
    ds.push(to="riastore", data="anything")

    # now, get an ephemeral clone from the RIA store:
    eph_clone = clone('ria+{}#{}'.format(store.as_uri(), ds.id), clone_path,
                      reckless="ephemeral")

    # ephemeral clone was properly linked (store has bare repos!):
    clone_annex = (eph_clone.repo.dot_git / 'annex')
    assert_true(clone_annex.is_symlink())
    assert_true(clone_annex.resolve().samefile(
        store / ds.id[:3] / ds.id[3:] / 'annex'))
    if not eph_clone.repo.is_managed_branch():
        # TODO: We can't properly handle adjusted branch yet
        # we don't need to get files in order to access them:
        assert_equal((eph_clone.pathobj / file_test).read_text(), "some")
        assert_equal((eph_clone.pathobj / file_testsub).read_text(), "other")

        # can we unlock those files?
        eph_clone.unlock(file_test)
        # change content
        (eph_clone.pathobj / file_test).write_text("new content")
        eph_clone.save()

        # new content should already be in store
        # (except the store doesn't know yet)
        res = eph_clone.repo.fsck(remote="riastore-storage", fast=True)
        assert_equal(len(res), 2)
        assert_result_count(res, 1, success=True, file=file_test.as_posix())
        assert_result_count(res, 1, success=True, file=file_testsub.as_posix())

        # push back git history
        eph_clone.push(to=DEFAULT_REMOTE, data="nothing")

        # get an update in origin
        ds.update(merge=True, reobtain_data=True)
        assert_equal((ds.pathobj / file_test).read_text(), "new content")
