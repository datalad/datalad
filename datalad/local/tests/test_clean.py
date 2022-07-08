# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Primarily a smoke test for ls

"""

__docformat__ = 'restructuredtext'

from datalad.api import clean
from datalad.consts import (
    ANNEX_TEMP_DIR,
    ANNEX_TRANSFER_DIR,
    ARCHIVES_TEMP_DIR,
    SEARCH_INDEX_DOTGITDIR,
)
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_status,
    with_tempfile,
)
from datalad.utils import (
    Path,
    chpwd,
    swallow_outputs,
)


@with_tempfile(mkdir=True)
def test_clean(d=None):
    AnnexRepo(d, create=True)
    ds = Dataset(d)
    assert_status('notneeded', clean(dataset=ds))

    archives_path = ds.pathobj / Path(ARCHIVES_TEMP_DIR)
    annex_tmp_path = ds.pathobj / Path(ANNEX_TEMP_DIR)
    annex_trans_path = ds.pathobj / Path(ANNEX_TRANSFER_DIR)
    index_path = ds.repo.dot_git / Path(SEARCH_INDEX_DOTGITDIR)

    # if we create some temp archives directory
    (archives_path / 'somebogus').mkdir(parents=True)
    res = clean(dataset=ds, return_type='item-or-list',
                result_filter=lambda x: x['status'] == 'ok')
    assert_equal(res['path'], str(archives_path))
    assert_equal(res['message'][0] % tuple(res['message'][1:]),
                 "Removed 1 temporary archive directory: somebogus")
    assert_false(archives_path.exists())

    # relative path
    (archives_path / 'somebogus').mkdir(parents=True)
    (archives_path / 'somebogus2').mkdir(parents=True)
    with chpwd(d), swallow_outputs() as cmo:
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 2 temporary archive directories: somebogus, "
                     "somebogus2")
        assert_false(archives_path.exists())

    # and what about git annex temporary files?
    annex_tmp_path.mkdir(parents=True)
    (annex_tmp_path / "somebogus").write_text("load")
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(annex_tmp_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 1 temporary annex file: somebogus")
        assert_false(annex_tmp_path.exists())

    (annex_trans_path / 'somebogus').mkdir(parents=True, exist_ok=True)
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(annex_trans_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 1 annex temporary transfer directory: somebogus")
        assert_false(annex_trans_path.exists())

    # search index
    index_path.mkdir(parents=True)
    (index_path / "MAIN_r55n3hiyvxkdf1fi.seg, _MAIN_1.toc").write_text("noop")
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(index_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed 1 metadata search index file: "
                     "MAIN_r55n3hiyvxkdf1fi.seg, _MAIN_1.toc")
        assert_false(index_path.exists())

    # remove empty directories, too
    archives_path.mkdir(parents=True)
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(archives_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed empty temporary archive directory")
        assert_false(archives_path.exists())

    annex_tmp_path.mkdir(parents=True)
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(annex_tmp_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed empty temporary annex directory")
        assert_false(annex_tmp_path.exists())

    annex_trans_path.mkdir(parents=True)
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(annex_trans_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed empty annex temporary transfer directory")
        assert_false(annex_trans_path.exists())

    index_path.mkdir(parents=True)
    with chpwd(d):
        res = clean(return_type='item-or-list',
                    result_filter=lambda x: x['status'] == 'ok')
        assert_equal(res['path'], str(index_path))
        assert_equal(res['message'][0] % tuple(res['message'][1:]),
                     "Removed empty metadata search index directory")
        assert_false(index_path.exists())
