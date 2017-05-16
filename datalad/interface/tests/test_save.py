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
from datalad.utils import chpwd

from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import DeprecatedError
from datalad.tests.utils import ok_, assert_false, assert_true, assert_not_equal
from datalad.api import save
from datalad.tests.utils import assert_raises
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_equal


@with_testrepos('.*git.*', flavors=['clone'])
def test_save(path):

    ds = Dataset(path)

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("something")

    ds.repo.add("new_file.tst", git=True)
    ok_(ds.repo.dirty)

    # no all_changes any longer
    with assert_raises(DeprecatedError):
        ds.save("add a new file", all_changes=True)

    ds.save("add a new file", all_updated=False)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("modify")

    ok_(ds.repo.dirty)
    ds.save("modified new_file.tst", all_updated=True)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # save works without ds and files given in the PWD
    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("rapunzel")
    with chpwd(path):
        save("love rapunzel", all_updated=True)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # and also without `-a` when things are staged
    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("exotic")
    ds.repo.add("new_file.tst", git=True)
    with chpwd(path):
        save("love marsians", all_updated=False)
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))


    files = ['one.txt', 'two.txt']
    for fn in files:
        with open(opj(path, fn), "w") as f:
            f.write(fn)

    ds.add([opj(path, f) for f in files])
    # superfluous call to save (add saved it already), should not fail
    # but report that nothing was saved
    assert_false(ds.save("set of new files"))
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # create subdataset
    subds = ds.create('subds')
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))
    # modify subds
    with open(opj(subds.path, "some_file.tst"), "w") as f:
        f.write("something")
    subds.add('.')
    ok_clean_git(subds.path, annex=isinstance(subds.repo, AnnexRepo))
    # Note/TODO: ok_clean_git is failing in direct mode, due to staged but
    # uncommited .datalad (probably caused within create)
    ok_(ds.repo.dirty)
    # ensure modified subds is committed
    ds.save(all_updated=True)
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
    assert_equal(
        ds.get_subdatasets(recursive=True, absolute=True, fulfilled=True),
        [subsubds.path, subds.path])
    newfile_name = opj(subsubds.path, 'test')
    with open(newfile_name, 'w') as f:
        f.write('some')
    # saves the status change of the subdataset due to the subsubdataset addition
    assert_equal(ds.save(all_updated=True), [ds])

    # make the new file known to its dataset
    # with #1141 this would be
    #ds.add(newfile_name, save=False)
    subsubds.add(newfile_name, save=False)

    # but remains dirty because of the untracked file down below
    assert ds.repo.dirty
    # auto-add will save nothing deep down without recursive
    assert_equal(ds.save(all_updated=True), [])
    assert ds.repo.dirty
    # with recursive pick up the change in subsubds
    assert_equal(ds.save(all_updated=True, recursive=True), [subsubds, subds, ds])
    # modify content in subsub and try saving
    testfname = newfile_name
    subsubds.unlock(testfname)
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    # the following should all do nothing
    # no auto_add
    assert_false(ds.save())
    # no recursive
    assert_false(ds.save(all_updated=True))
    # an explicit target saves only the corresponding dataset
    assert_equal(save(files=[testfname]), [subsubds])
    # plain recursive without any files given will save the beast
    assert_equal(ds.save(recursive=True), [subds, ds])
    # there is nothing else to save
    assert_false(ds.save(all_updated=True, recursive=True))
    # one more time and check that all datasets in the hierarchy get updated
    states = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    testfname = opj('sub', 'subsub', 'saveme2')
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    assert_true(ds.save(all_updated=True, recursive=True))
    newstates = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    for old, new in zip(states, newstates):
        assert_not_equal(old, new)
    # now let's check saving "upwards"
    assert not subds.repo.dirty
    create_tree(subds.path, {"testnew": 'smth', "testadded": "added"})
    subds.repo.add("testadded")
    indexed_files = subds.repo.get_indexed_files()
    assert subds.repo.dirty
    assert ds.repo.dirty

    assert not subsubds.repo.dirty
    create_tree(subsubds.path, {"testnew2": 'smth'})
    assert subsubds.repo.dirty
    # and indexed files didn't change
    assert_equal(indexed_files, subds.repo.get_indexed_files())
    ok_clean_git(subds.repo, untracked=['testnew'],
                 index_modified=['subsub'], head_modified=['testadded'])
    subsubds.save(message="savingtestmessage", super_datasets=True,
                  all_updated=True)
    ok_clean_git(subsubds.repo)
    # but its super should have got only the subsub saved
    # not the file we created
    ok_clean_git(subds.repo, untracked=['testnew'], head_modified=['testadded'])

    # check commits to have correct messages
    # there are no more dedicated superdataset-save commits anymore, because
    # superdatasets get saved as part of the processed hierarchy and can contain
    # other parts in the commit (if so instructed)
    assert_equal(next(subsubds.repo.get_branch_commits('master')).message.rstrip(),
                 'savingtestmessage')
    assert_equal(next(subds.repo.get_branch_commits('master')).message.rstrip(),
                 'savingtestmessage')
    assert_equal(next(ds.repo.get_branch_commits('master')).message.rstrip(),
                 'savingtestmessage')
