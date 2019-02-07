# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# -*- coding: utf-8 -*-
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

from datalad.tests.utils import known_failure_direct_mode

import os
from os.path import pardir
from os.path import join as opj
from datalad.utils import (
    chpwd,
    unlink,
)

from datalad.interface.results import is_ok_dataset
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import IncompleteResultsError
from datalad.tests.utils import ok_
from datalad.api import save
from datalad.api import create
from datalad.api import add
from datalad.tests.utils import assert_raises
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import create_tree
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_status
from datalad.tests.utils import assert_result_count
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_result_values_equal
from datalad.tests.utils import skip_v6_or_later
from datalad.tests.utils import known_failure_windows


@with_testrepos('.*git.*', flavors=['clone'])
@known_failure_direct_mode  #FIXME
def test_save(path):

    ds = Dataset(path)

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("something")

    ds.repo.add("new_file.tst", git=True)
    ok_(ds.repo.dirty)

    ds.save("add a new file")
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("modify")

    ok_(ds.repo.dirty)
    ds.save("modified new_file.tst")
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # save works without ds and files given in the PWD
    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("rapunzel")
    with chpwd(path):
        save("love rapunzel")
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # and also without `-a` when things are staged
    with open(opj(path, "new_file.tst"), "w") as f:
        f.write("exotic")
    ds.repo.add("new_file.tst", git=True)
    with chpwd(path):
        save("love marsians")
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    files = ['one.txt', 'two.txt']
    for fn in files:
        with open(opj(path, fn), "w") as f:
            f.write(fn)

    ds.add([opj(path, f) for f in files])
    # superfluous call to save (add saved it already), should not fail
    # but report that nothing was saved
    assert_status('notneeded', ds.save("set of new files"))
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
    ds.save()
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))

    # now introduce a change downstairs
    subds.create('someotherds')
    ok_clean_git(subds.path, annex=isinstance(subds.repo, AnnexRepo))
    ok_(ds.repo.dirty)
    # and save via subdataset path
    ds.save('subds')
    ok_clean_git(path, annex=isinstance(ds.repo, AnnexRepo))


@with_tempfile()
@known_failure_direct_mode  #FIXME
def test_recursive_save(path):
    ds = Dataset(path).create()
    # nothing to save
    assert_status('notneeded', ds.save())
    subds = ds.create('sub')
    # subdataset presence already saved
    ok_clean_git(ds.path)
    subsubds = subds.create('subsub')
    assert_equal(
        ds.subdatasets(recursive=True, fulfilled=True, result_xfm='paths'),
        [subds.path, subsubds.path])
    newfile_name = opj(subsubds.path, 'test')
    with open(newfile_name, 'w') as f:
        f.write('some')
    # saves the status change of the subdataset due to the subsubdataset addition
    assert_result_values_equal(
        ds.save(result_filter=is_ok_dataset),
        'path',
        [ds.path])

    # make the new file known to its dataset
    ds.add(newfile_name, save=False)

    # but remains dirty because of the uncommited file down below
    assert ds.repo.dirty
    # auto-add will save nothing deep down without recursive
    assert_status('notneeded', ds.save())
    assert ds.repo.dirty
    # with recursive pick up the change in subsubds
    assert_result_values_equal(
        ds.save(recursive=True, result_filter=is_ok_dataset),
        'path',
        [subsubds.path, subds.path, ds.path])

    # at this point the entire tree is clean
    ok_clean_git(ds.path)
    states = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    # now we save recursively, nothing should happen
    res = ds.save(recursive=True)
    # we do not get any report from a subdataset, because we detect at the
    # very top that the entire tree is clean
    assert_result_count(res, 1)
    assert_result_count(res, 1, status='notneeded', action='save', path=ds.path)
    # now we introduce new files all the way down
    create_tree(subsubds.path, {"mike1": 'mike1'})
    # because we cannot say from the top if there is anything to do down below,
    # we have to traverse and we will get reports for all dataset, but there is
    # nothing actually saved
    res = ds.save(recursive=True)
    assert_result_count(res, 3)
    assert_status('notneeded', res)
    subsubds_indexed = subsubds.repo.get_indexed_files()
    assert_not_in('mike1', subsubds_indexed)
    assert_equal(states, [d.repo.get_hexsha() for d in (ds, subds, subsubds)])
    unlink(opj(subsubds.path, 'mike1'))
    ok_clean_git(ds.path)

    # modify content in subsub and try saving
    testfname = newfile_name
    subsubds.unlock(testfname)
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    # the following should all do nothing
    # no auto_add
    assert_status('notneeded', ds.save())
    # no recursive
    assert_status('notneeded', ds.save())
    # an explicit target saves only the corresponding dataset
    assert_result_values_equal(
        save(path=[testfname]),
        'path',
        [subsubds.path])
    # plain recursive without any files given will save the beast
    assert_result_values_equal(
        ds.save(recursive=True, result_filter=is_ok_dataset),
        'path',
        [subds.path, ds.path])
    # there is nothing else to save
    assert_status('notneeded', ds.save(recursive=True))
    ok_clean_git(ds.path)
    # one more time and check that all datasets in the hierarchy are not
    # contaminated with untracked files
    states = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    testfname = opj('sub', 'subsub', 'saveme2')
    with open(opj(ds.path, testfname), 'w') as f:
        f.write('I am in here!')
    assert_status('notneeded', ds.save(recursive=True))
    newstates = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    for old, new in zip(states, newstates):
        assert_equal(old, new)
    assert ds.repo.dirty
    unlink(opj(ds.path, testfname))
    ok_clean_git(ds.path)

    # now let's check saving "upwards"
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
    old_states = [d.repo.get_hexsha() for d in (ds, subds, subsubds)]
    subsubds.save(message="savingtestmessage", super_datasets=True)
    # this save actually didn't save anything in subsub (or anywhere),
    # because there were only untracked bits pending
    for old, new in zip(old_states, [d.repo.get_hexsha()
                                     for d in (ds, subds, subsubds)]):
        assert_equal(old, new)
    # but now we are saving this untracked bit specifically
    subsubds.save(message="savingtestmessage", path=['testnew2'],
                  super_datasets=True)
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

    # and if we try to save while being within that subsubds path
    subsubds.unlock('testnew2')
    create_tree(subsubds.path, {"testnew2": 'smth2'})

    # trying to replicate https://github.com/datalad/datalad/issues/1540
    subsubds.save(message="saving new changes", all_updated=True)  # no super
    with chpwd(subds.path):
        # no explicit dataset is provided by path is provided
        save(path=['subsub'], message='saving sub', super_datasets=True)
    # super should get it saved too
    assert_equal(next(ds.repo.get_branch_commits('master')).message.rstrip(),
                 'saving sub')


@with_tempfile()
def test_save_message_file(path):
    ds = Dataset(path).create()
    with assert_raises(ValueError):
        ds.save("blah", message="me", message_file="and me")

    create_tree(path, {"foo": "x",
                       "msg": u"add β"})
    ds.add("foo", save=False)
    ds.save(message_file=opj(ds.path, "msg"))
    assert_equal(ds.repo.format_commit("%s"),
                 u"add β")


def test_renamed_file():
    @with_tempfile()
    def check_renamed_file(recursive, no_annex, path):
        ds = Dataset(path).create(no_annex=no_annex)
        create_tree(path, {'old': ''})
        ds.add('old')
        ds.repo._git_custom_command(['old', 'new'], ['git', 'mv'])
        ds.save(recursive=recursive)
        ok_clean_git(path)

    for recursive in True, False:
        for no_annex in True, False:
            yield check_renamed_file, recursive, no_annex


@with_tempfile(mkdir=True)
@known_failure_direct_mode  #FIXME
def test_subdataset_save(path):
    parent = Dataset(path).create()
    sub = parent.create('sub')
    ok_clean_git(parent.path)
    create_tree(parent.path, {
        "untracked": 'ignore',
        'sub': {
            "new": "wanted"}})
    sub.add('new')
    # defined state: one untracked, modified (but clean in itself) subdataset
    ok_clean_git(sub.path)
    ok_clean_git(parent.path, untracked=['untracked'], index_modified=['sub'])

    # `save sub` does not save the parent!!
    with chpwd(parent.path):
        assert_status('notneeded', save(path=sub.path))
    ok_clean_git(parent.path, untracked=['untracked'], index_modified=['sub'])
    # `save -d .` saves the state change in the subdataset, but leaves any untracked
    # content alone
    with chpwd(parent.path):
        assert_status('ok', parent.save())
    ok_clean_git(parent.path, untracked=['untracked'])

    # get back to the original modified state and check that -S behaves in
    # exactly the same way
    create_tree(parent.path, {
        'sub': {
            "new2": "wanted2"}})
    sub.add('new2')
    ok_clean_git(parent.path, untracked=['untracked'], index_modified=['sub'])
    with chpwd(parent.path):
        assert_status(
            # notneeded to save sub, but need to save parent
            ['ok', 'notneeded'],
            # the key condition of this test is that no reference dataset is
            # given!
            save(path='sub', super_datasets=True))
    # save super must not cause untracked content to be commited!
    ok_clean_git(parent.path, untracked=['untracked'])


@known_failure_windows  # gh-2536
@with_tempfile(mkdir=True)
def test_symlinked_relpath(path):
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    os.makedirs(opj(path, "origin"))
    dspath = opj(path, "linked")
    os.symlink('origin', dspath)
    ds = Dataset(dspath).create()
    create_tree(dspath, {
        "mike1": 'mike1',  # will be added from topdir
        "later": "later",  # later from within subdir
        "d": {
            "mike2": 'mike2', # to be added within subdir
        }
    })

    # in the root of ds
    with chpwd(dspath):
        ds.repo.add("mike1", git=True)
        ds.save("committing", path="./mike1")

    # Let's also do in subdirectory
    with chpwd(opj(dspath, 'd')):
        ds.repo.add("mike2", git=True)
        ds.save("committing", path="./mike2")

        later = opj(pardir, "later")
        ds.repo.add(later, git=True)
        ds.save("committing", path=later)

    ok_clean_git(dspath)


# two subdatasets not possible in direct mode
@known_failure_direct_mode  #FIXME
@with_tempfile(mkdir=True)
def test_bf1886(path):
    parent = Dataset(path).create()
    sub = parent.create('sub')
    ok_clean_git(parent.path)
    # create a symlink pointing down to the subdataset, and add it
    os.symlink('sub', opj(parent.path, 'down'))
    parent.add('down')
    ok_clean_git(parent.path)
    # now symlink pointing up
    os.makedirs(opj(parent.path, 'subdir', 'subsubdir'))
    os.symlink(opj(pardir, 'sub'), opj(parent.path, 'subdir', 'up'))
    parent.add(opj('subdir', 'up'))
    ok_clean_git(parent.path)
    # now symlink pointing 2xup, as in #1886
    os.symlink(opj(pardir, pardir, 'sub'), opj(parent.path, 'subdir', 'subsubdir', 'upup'))
    parent.add(opj('subdir', 'subsubdir', 'upup'))
    ok_clean_git(parent.path)
    # simulatenously add a subds and a symlink pointing to it
    # create subds, but don't register it
    sub2 = create(opj(parent.path, 'sub2'))
    os.symlink(
        opj(pardir, pardir, 'sub2'),
        opj(parent.path, 'subdir', 'subsubdir', 'upup2'))
    parent.add(['sub2', opj('subdir', 'subsubdir', 'upup2')])
    ok_clean_git(parent.path)
    # full replication of #1886: the above but be in subdir of symlink
    # with no reference dataset
    sub3 = create(opj(parent.path, 'sub3'))
    os.symlink(
        opj(pardir, pardir, 'sub3'),
        opj(parent.path, 'subdir', 'subsubdir', 'upup3'))
    # need to use absolute paths
    with chpwd(opj(parent.path, 'subdir', 'subsubdir')):
        add([opj(parent.path, 'sub3'),
             opj(parent.path, 'subdir', 'subsubdir', 'upup3')])
    # here is where we need to disagree with the repo in #1886
    # we would not expect that `add` registers sub3 as a subdataset
    # of parent, because no reference dataset was given and the
    # command cannot decide (with the current semantics) whether
    # it should "add anything in sub3 to sub3" or "add sub3 to whatever
    # sub3 is in"
    ok_clean_git(parent.path, untracked=['sub3/'])


@with_tree({
    '1': '',
    '2': '',
    '3': ''})
def test_gh2043p1(path):
    # this tests documents the interim agreement on what should happen
    # in the case documented in gh-2043
    ds = Dataset(path).create(force=True)
    ds.add('1')
    ok_clean_git(ds.path, untracked=['2', '3'])
    ds.unlock('1')
    ok_clean_git(ds.path, index_modified=['1'], untracked=['2', '3'])
    # save(.) should recommit unlocked file, and not touch anything else
    # this tests the second issue in #2043
    with chpwd(path):
        # only save modified bits by default
        save('.')  #  because the first arg is the dataset
    # state of the file (unlocked/locked) is committed as well, and the
    # test doesn't lock the file again
    skip_v6_or_later(method='pass')(ok_clean_git)(ds.path, untracked=['2', '3'])
    with chpwd(path):
        # but when a path is given, anything that matches this path
        # untracked or not is added/saved
        save(path='.')
    # state of the file (unlocked/locked) is committed as well, and the
    # test doesn't lock the file again
    skip_v6_or_later(method='pass')(ok_clean_git)(ds.path)


@with_tree({
    'staged': 'staged',
    'untracked': 'untracked'})
def test_bf2043p2(path):
    ds = Dataset(path).create(force=True)
    ds.add('staged', save=False)
    ok_clean_git(ds.path, head_modified=['staged'], untracked=['untracked'])
    # plain save does not commit untracked content
    # this tests the second issue in #2043
    with chpwd(path):
        save()
    ok_clean_git(ds.path, untracked=['untracked'])
