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
from datalad.support.annexrepo import AnnexRepo
from datalad.tests.utils import ok_, assert_false, assert_true, assert_not_equal
from datalad import api as _
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git


@with_testrepos('.*git.*', flavors=['clone'])
def test_save(path):

    ds = Dataset(path)

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

    # create subdataset
    subds = ds.create('subds')
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))
    # modify subds
    with open(opj(subds.path, "some_file.tst"), "w") as f:
        f.write("something")
    subds.save(auto_add_changes=True)
    ok_clean_git(subds.path, annex=isinstance(ds.repo, AnnexRepo))
    ok_(ds.repo.dirty)
    # ensure modified subds is commited
    ds.save(auto_add_changes=True)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))


@with_tempfile()
def test_recursive_save(path):
    ds = Dataset(path).create()
    # nothing to save
    assert_false(ds.save())
    subds = ds.create('sub')
    # subdataset presence already saved
    ok_clean_git(ds.path)
    subsubds = subds.create('subsub')
    with open(opj(subsubds.path, 'test'), 'w') as f:
        f.write('some')
    # does not save anything in the topdataset
    assert_false(ds.save())
    # auto-add will save addition of subsubds to subds
    assert_true(ds.save(auto_add_changes=True))
    # with recursive it will add the file in subsubds
    assert_true(ds.save(auto_add_changes=True, recursive=True))
    # add content to subsub and try saving
    testfname = opj('sub', 'subsub', 'saveme')
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    # the following should all do nothing
    # no auto_add
    assert_false(ds.save())
    # no recursive
    assert_false(ds.save(auto_add_changes=True))
    # no recursive and auto_add
    assert_false(ds.save(recursive=True))
    # even with explicit target, no recursive safe
    assert_false(ds.save(files=[testfname]))
    # insufficient recursion depth
    for rlevel in (0, 1):
        assert_false(ds.save(files=[testfname], recursive=True, recursion_limit=rlevel))
    # and finally with the right settings
    assert_true(ds.save(files=[testfname], recursive=True, recursion_limit=2))
    # there is nothing else to save
    assert_false(ds.save(auto_add_changes=True, recursive=True))
    # one more time and check that all datasets in the hierarchy get updated
    states = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    testfname = opj('sub', 'subsub', 'saveme2')
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    assert_true(ds.save(auto_add_changes=True, recursive=True))
    newstates = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    for old, new in zip(states, newstates):
        assert_not_equal(old, new)
