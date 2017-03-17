# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test update action

"""

import os
from os.path import join as opj, exists
from ..dataset import Dataset
from datalad.api import install
from datalad.api import update
from datalad.utils import knows_annex
from datalad.utils import rmtree
from datalad.utils import chpwd
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo

from nose.tools import eq_, assert_false, assert_is_instance, ok_
from datalad.tests.utils import with_tempfile, assert_in, \
    with_testrepos, assert_not_in
from datalad.tests.utils import SkipTest
from datalad.tests.utils import create_tree
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import ok_clean_git


@with_testrepos('submodule_annex', flavors=['local'])  #TODO: Use all repos after fixing them
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_simple(origin, src_path, dst_path):

    # prepare src
    source = install(src_path, source=origin, recursive=True)[0]
    # forget we cloned it (provide no 'origin' anymore), which should lead to
    # setting tracking branch to target:
    source.repo.remove_remote("origin")

    # get a clone to update later on:
    dest = install(dst_path, source=src_path, recursive=True)[0]
    # test setup done;
    # assert all fine
    ok_clean_git(dst_path)
    ok_clean_git(src_path)

    # update yields nothing => up-to-date
    # TODO: how to test besides not failing?
    dest.update()
    ok_clean_git(dst_path)

    # modify origin:
    with open(opj(src_path, "update.txt"), "w") as f:
        f.write("Additional content")
    source.add(path="update.txt")
    source.save("Added update.txt")
    ok_clean_git(src_path)

    # update without `merge` only fetches:
    dest.update()
    # modification is not known to active branch:
    assert_not_in("update.txt",
                  dest.repo.get_files(dest.repo.get_active_branch()))
    # modification is known to branch origin/master
    assert_in("update.txt", dest.repo.get_files("origin/master"))

    # merge:
    dest.update(merge=True)
    # modification is now known to active branch:
    assert_in("update.txt",
              dest.repo.get_files(dest.repo.get_active_branch()))
    # it's known to annex, but has no content yet:
    dest.repo.get_file_key("update.txt")  # raises if unknown
    eq_([False], dest.repo.file_has_content(["update.txt"]))

    # smoke-test if recursive update doesn't fail if submodule is removed
    # and that we can run it from within a dataset without providing it
    # explicitly
    dest.remove('subm 1')
    with chpwd(dest.path):
        update(recursive=True)
    dest.update(merge=True, recursive=True)

    # and now test recursive update with merging in differences
    create_tree(opj(source.path, 'subm 2'), {'load.dat': 'heavy'})
    source.save(message="saving changes within subm2",
                recursive=True, all_updated=True)
    dest.update(merge=True, recursive=True)
    # and now we can get new file
    dest.get('subm 2/load.dat')
    ok_file_has_content(opj(dest.path, 'subm 2', 'load.dat'), 'heavy')


@with_tempfile
@with_tempfile
def test_update_git_smoke(src_path, dst_path):
    # Apparently was just failing on git repos for basic lack of coverage, hence this quick test
    ds = Dataset(src_path).create(no_annex=True)
    target = install(dst_path, source=src_path)
    create_tree(ds.path, {'file.dat': '123'})
    ds.add('file.dat')
    target.update(recursive=True, merge=True)
    ok_file_has_content(opj(target.path, 'file.dat'), '123')


def test_update_recursive():
    raise SkipTest("TODO more tests to add to above ones")


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_fetch_all(src, remote_1, remote_2):
    rmt1 = AnnexRepo.clone(src, remote_1)
    rmt2 = AnnexRepo.clone(src, remote_2)

    ds = Dataset(src)
    ds.add_sibling(name="sibling_1", url=remote_1)
    ds.add_sibling(name="sibling_2", url=remote_2)

    # modify the remotes:
    with open(opj(remote_1, "first.txt"), "w") as f:
        f.write("some file load")
    rmt1.add("first.txt", commit=True)
    # TODO: Modify an already present file!

    with open(opj(remote_2, "second.txt"), "w") as f:
        f.write("different file load")
    rmt2.add("second.txt", git=True, commit=True, msg="Add file to git.")

    # Let's init some special remote which we couldn't really update/fetch
    if not os.environ.get('DATALAD_TESTS_DATALADREMOTE'):
        ds.repo.init_remote(
            'datalad',
            ['encryption=none', 'type=external', 'externaltype=datalad'])
    # fetch all remotes
    ds.update(fetch_all=True)

    # no merge, so changes are not in active branch:
    assert_not_in("first.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    assert_not_in("second.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    # but we know the changes in remote branches:
    assert_in("first.txt", ds.repo.get_files("sibling_1/master"))
    assert_in("second.txt", ds.repo.get_files("sibling_2/master"))

    # no merge strategy for multiple remotes yet:
    # more clever now, there is a tracking branch that provides a remote
    #assert_raises(NotImplementedError, ds.update, merge=True, fetch_all=True)

    # merge a certain remote:
    ds.update(sibling="sibling_1", merge=True)

    # changes from sibling_2 still not present:
    assert_not_in("second.txt",
                  ds.repo.get_files(ds.repo.get_active_branch()))
    # changes from sibling_1 merged:
    assert_in("first.txt",
              ds.repo.get_files(ds.repo.get_active_branch()))
    # it's known to annex, but has no content yet:
    ds.repo.get_file_key("first.txt")  # raises if unknown
    eq_([False], ds.repo.file_has_content(["first.txt"]))


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_newthings_coming_down(originpath, destpath):
    origin = GitRepo(originpath, create=True)
    create_tree(originpath, {'load.dat': 'heavy'})
    Dataset(originpath).add('load.dat')
    ds = install(source=originpath, path=destpath)
    assert_is_instance(ds.repo, GitRepo)
    assert_in('origin', ds.repo.get_remotes())
    # turn origin into an annex
    origin = AnnexRepo(originpath, create=True)
    # clone doesn't know yet
    assert_false(knows_annex(ds.path))
    # but after an update it should
    # no merge, only one sibling, no parameters should be specific enough
    ds.update()
    assert(knows_annex(ds.path))
    # no branches appeared
    eq_(ds.repo.get_branches(), ['master'])
    # now merge, and get an annex
    ds.update(merge=True)
    assert_in('git-annex', ds.repo.get_branches())
    assert_is_instance(ds.repo, AnnexRepo)
    # should be fully functional
    testfname = opj(ds.path, 'load.dat')
    assert_false(ds.repo.file_has_content(testfname))
    ds.get('.')
    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    # check that a new tag comes down
    origin.tag('first!')
    ds.update()
    eq_(ds.repo.repo.tags[0].name, 'first!')

    # and now we destroy the remote annex
    origin._git_custom_command([], ['git', 'config', '--remove-section', 'annex'])
    rmtree(opj(origin.path, '.git', 'annex'), chmod_files=True)
    origin._git_custom_command([], ['git', 'branch', '-D', 'git-annex'])
    origin = GitRepo(originpath)
    assert_false(knows_annex(originpath))

    # and update the local clone
    # for now this should simply not fail (see gh-793), later might be enhanced to a
    # graceful downgrade
    before_branches = ds.repo.get_branches()
    ds.update()
    eq_(before_branches, ds.repo.get_branches())
    # annex branch got pruned
    eq_(['origin/HEAD', 'origin/master'], ds.repo.get_remote_branches())
    # check that a new tag comes down even if repo types mismatch
    origin.tag('second!')
    ds.update()
    eq_(ds.repo.repo.tags[-1].name, 'second!')


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_update_volatile_subds(originpath, destpath):
    origin = Dataset(originpath).create()
    ds = install(source=originpath, path=destpath)
    # as a submodule
    sname = 'subm 1'
    osm1 = origin.create(sname)
    ds.update()
    # nothing without a merge, no inappropriate magic
    assert_not_in(sname, ds.get_subdatasets())
    ds.update(merge=True)
    # known, and placeholder exists
    assert_in(sname, ds.get_subdatasets())
    ok_(exists(opj(ds.path, sname)))

    # remove from origin
    origin.remove(sname)
    ds.update(merge=True)
    # gone locally, wasn't checked out
    assert_not_in(sname, ds.get_subdatasets())
    assert_false(exists(opj(ds.path, sname)))

    # re-introduce at origin
    osm1 = origin.create(sname)
    create_tree(osm1.path, {'load.dat': 'heavy'})
    origin.add(opj(osm1.path, 'load.dat'))
    ds.update(merge=True)
    # grab new content of uninstall subdataset, right away
    ds.get(opj(ds.path, sname, 'load.dat'))
    ok_file_has_content(opj(ds.path, sname, 'load.dat'), 'heavy')

    # now remove just-installed subdataset from origin again
    origin.remove(sname, check=False)
    assert_not_in(sname, origin.get_subdatasets())
    assert_in(sname, ds.get_subdatasets())
    # merge should disconnect the installed subdataset, but leave the actual
    # ex-subdataset alone
    ds.update(merge=True)
    assert_not_in(sname, ds.get_subdatasets())
    ok_file_has_content(opj(ds.path, sname, 'load.dat'), 'heavy')
    ok_(Dataset(opj(ds.path, sname)).is_installed())


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_reobtain_data(originpath, destpath):
    origin = Dataset(originpath).create()
    ds = install(source=originpath, path=destpath)
    # no harm
    ds.update(merge=True, reobtain_data=True)
    # content
    create_tree(origin.path, {'load.dat': 'heavy'})
    origin.add(opj(origin.path, 'load.dat'))
    # update does not bring data automatically
    ds.update(merge=True, reobtain_data=True)
    assert_in('load.dat', ds.repo.get_annexed_files())
    assert_false(ds.repo.file_has_content('load.dat'))
    # now get data
    ds.get('load.dat')
    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    # new content at origin
    create_tree(origin.path, {'novel': 'but boring'})
    origin.add('.')
    # update must not bring in data for new file
    ds.update(merge=True, reobtain_data=True)
    ok_file_has_content(opj(ds.path, 'load.dat'), 'heavy')
    assert_in('novel', ds.repo.get_annexed_files())
    assert_false(ds.repo.file_has_content('novel'))
    # modify content at origin
    os.remove(opj(origin.path, 'load.dat'))
    create_tree(origin.path, {'load.dat': 'light'})
    origin.add('.')
    # update must update file with existing data, but leave empty one alone
    ds.update(merge=True, reobtain_data=True)
    ok_file_has_content(opj(ds.path, 'load.dat'), 'light')
    assert_false(ds.repo.file_has_content('novel'))
