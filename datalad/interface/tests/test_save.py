# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""test command datalad save

"""

__docformat__ = 'restructuredtext'

from os.path import join as opj

from datalad.distribution.dataset import Dataset
from datalad.api import create
from datalad.api import save
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import ok_
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import ok_clean_git


@with_testrepos('.*git.*', flavors=['clone'])
def test_save(path):

    ds = Dataset(path)
    if isinstance(ds.repo, AnnexRepo):
        ds.repo._init()

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("something")

    ds.repo.add("new_file.tst", git=True)
    ok_(ds.repo.dirty)

    ds.save("add a new file", auto_add_changes=False)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("modify")

    ok_(ds.repo.dirty)
    # no need to git add before:
    ds.save("modified new_file.tst", auto_add_changes=True)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    files = ['one.txt', 'two.txt']
    for fn in files:
        with open(opj(path, fn), "w") as f:
            f.write(fn)

    ds.save("set of new files", files=[opj(path, f) for f in files])
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))
