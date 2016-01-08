# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..files import AnnexFileAttributesDB

from ....tests.utils import with_tree
from ....tests.utils import assert_equal
from ....tests.utils import assert_false
from ....support.annexrepo import AnnexRepo

@with_tree(
    tree={'file1.txt': 'load1',
          'd': {
              'file2.txt': 'load2'
          }
    }
)
def test_AnnexFileAttributesDB(path):
    annex = AnnexRepo(path, create=True)

    # AnnexFileAttributesDB relies on information in annex so files
    # must be committed first
    annex.annex_add('.')
    annex.git_commit("initial commit")
    db = AnnexFileAttributesDB(annex=annex)
    status1 = db.get('file1.txt')
    assert(status1)

    status1_ = db.get('file1.txt')
    assert_equal(status1, status1_)
    assert_false(db.is_different('file1.txt', status1))