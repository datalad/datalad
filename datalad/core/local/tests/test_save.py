# -*- coding: utf-8 -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test save command"""

import os
import os.path as op

from datalad.utils import (
    ensure_list,
    Path,
    on_windows,
    rmtree,
)
from datalad.tests.utils import (
    assert_in,
    assert_in_results,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    chpwd,
    create_tree,
    DEFAULT_BRANCH,
    eq_,
    known_failure,
    known_failure_appveyor,
    known_failure_windows,
    maybe_adjust_repo,
    OBSCURE_FILENAME,
    ok_,
    SkipTest,
    skip_wo_symlink_capability,
    swallow_outputs,
    with_tempfile,
    with_testrepos,
    with_tree,
)

import datalad.utils as ut
from datalad.distribution.dataset import Dataset
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CommandError
from datalad.api import (
    create,
    install,
    save,
)


tree_arg = dict(tree={'test.txt': 'some',
                      'test_annex.txt': 'some annex',
                      'test1.dat': 'test file 1',
                      'test2.dat': 'test file 2',
                      OBSCURE_FILENAME: 'blobert',
                      'dir': {'testindir': 'someother',
                              OBSCURE_FILENAME: 'none'},
                      'dir2': {'testindir3': 'someother3'}})


# https://ci.appveyor.com/project/mih/datalad/builds/29840270/job/oya0cs55nwtoga4p
# # (The system cannot find the path specified.)
@known_failure_appveyor
@with_testrepos('.*git.*', flavors=['clone'])
def test_save(path):

    ds = Dataset(path)

    with open(op.join(path, "new_file.tst"), "w") as f:
        f.write("something")

    ds.repo.add("new_file.tst", git=True)
    ok_(ds.repo.dirty)

    ds.save(message="add a new file")
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    with open(op.join(path, "new_file.tst"), "w") as f:
        f.write("modify")

    ok_(ds.repo.dirty)
    ds.save(message="modified new_file.tst")
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    # save works without ds and files given in the PWD
    with open(op.join(path, "new_file.tst"), "w") as f:
        f.write("rapunzel")
    with chpwd(path):
        save(message="love rapunzel")
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    # and also without `-a` when things are staged
    with open(op.join(path, "new_file.tst"), "w") as f:
        f.write("exotic")
    ds.repo.add("new_file.tst", git=True)
    with chpwd(path):
        save(message="love marsians")
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    files = ['one.txt', 'two.txt']
    for fn in files:
        with open(op.join(path, fn), "w") as f:
            f.write(fn)

    ds.save([op.join(path, f) for f in files])
    # superfluous call to save (alll saved it already), should not fail
    # but report that nothing was saved
    assert_status('notneeded', ds.save(message="set of new files"))
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    # create subdataset
    subds = ds.create('subds')
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))
    # modify subds
    with open(op.join(subds.path, "some_file.tst"), "w") as f:
        f.write("something")
    subds.save()
    assert_repo_status(subds.path, annex=isinstance(subds.repo, AnnexRepo))
    # ensure modified subds is committed
    ds.save()
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))

    # now introduce a change downstairs
    subds.create('someotherds')
    assert_repo_status(subds.path, annex=isinstance(subds.repo, AnnexRepo))
    ok_(ds.repo.dirty)
    # and save via subdataset path
    ds.save('subds', version_tag='new_sub')
    assert_repo_status(path, annex=isinstance(ds.repo, AnnexRepo))
    tags = ds.repo.get_tags()
    ok_(len(tags) == 1)
    eq_(tags[0], dict(hexsha=ds.repo.get_hexsha(), name='new_sub'))
    # fails when retagged, like git does
    res = ds.save(version_tag='new_sub', on_failure='ignore')
    assert_status('error', res)
    assert_result_count(
        res, 1,
        action='save', type='dataset', path=ds.path,
        message=('cannot tag this version: %s',
                 "fatal: tag 'new_sub' already exists"))


@with_tempfile()
def test_save_message_file(path):
    ds = Dataset(path).create()
    with assert_raises(ValueError):
        ds.save("blah", message="me", message_file="and me")

    create_tree(path, {"foo": "x",
                       "msg": "add foo"})
    ds.repo.add("foo")
    ds.save(message_file=op.join(ds.path, "msg"))
    # ATTN: Consider corresponding branch so that this check works when we're
    # on an adjusted branch too (e.g., when this test is executed under
    # Windows).
    eq_(ds.repo.format_commit("%s", DEFAULT_BRANCH),
        "add foo")


def test_renamed_file():
    @with_tempfile()
    def check_renamed_file(recursive, annex, path):
        ds = Dataset(path).create(annex=annex)
        create_tree(path, {'old': ''})
        ds.repo.add('old')
        ds.repo.call_git(["mv"], files=["old", "new"])
        ds.save(recursive=recursive)
        assert_repo_status(path)

    for recursive in False,:  #, True TODO when implemented
        for annex in True, False:
            yield check_renamed_file, recursive, annex


@with_tempfile(mkdir=True)
def test_subdataset_save(path):
    parent = Dataset(path).create()
    sub = parent.create('sub')
    assert_repo_status(parent.path)
    create_tree(parent.path, {
        "untracked": 'ignore',
        'sub': {
            "new": "wanted"}})
    sub.save('new')
    # defined state: one untracked, modified (but clean in itself) subdataset
    assert_repo_status(sub.path)
    assert_repo_status(parent.path, untracked=['untracked'], modified=['sub'])

    # `save sub` does not save the parent!!
    with chpwd(parent.path):
        assert_status('notneeded', save(dataset=sub.path))
    assert_repo_status(parent.path, untracked=['untracked'], modified=['sub'])
    # `save -u .` saves the state change in the subdataset,
    # but leaves any untracked content alone
    with chpwd(parent.path):
        assert_status('ok', parent.save(updated=True))
    assert_repo_status(parent.path, untracked=['untracked'])

    # get back to the original modified state and check that -S behaves in
    # exactly the same way
    create_tree(parent.path, {
        'sub': {
            "new2": "wanted2"}})
    sub.save('new2')
    assert_repo_status(parent.path, untracked=['untracked'], modified=['sub'])


@with_tempfile(mkdir=True)
def test_subsuperdataset_save(path):
    # Verify that when invoked without recursion save does not
    # cause querying of subdatasets of the subdataset
    # see https://github.com/datalad/datalad/issues/4523
    parent = Dataset(path).create()
    # Create 3 levels of subdatasets so later to check operation
    # with or without --dataset being specified
    sub1 = parent.create('sub1')
    sub2 = parent.create(sub1.pathobj / 'sub2')
    sub3 = parent.create(sub2.pathobj / 'sub3')
    assert_repo_status(path)
    # now we will lobotomize that sub3 so git would fail if any query is performed.
    (sub3.pathobj / '.git' / 'config').chmod(0o000)
    try:
        sub3.repo.call_git(['ls-files'], read_only=True)
        raise SkipTest
    except CommandError:
        # desired outcome
        pass
    # the call should proceed fine since neither should care about sub3
    # default is no recursion
    parent.save('sub1')
    sub1.save('sub2')
    assert_raises(CommandError, parent.save, 'sub1', recursive=True)
    # and should not fail in the top level superdataset
    with chpwd(parent.path):
        save('sub1')
    # or in a subdataset above the problematic one
    with chpwd(sub1.path):
        save('sub2')


@skip_wo_symlink_capability
@with_tempfile(mkdir=True)
def test_symlinked_relpath(path):
    # initially ran into on OSX https://github.com/datalad/datalad/issues/2406
    os.makedirs(op.join(path, "origin"))
    dspath = op.join(path, "linked")
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
        ds.save(message="committing", path="./mike1")

    # Let's also do in subdirectory as CWD, check that relative path
    # given to a plain command (not dataset method) are treated as
    # relative to CWD
    with chpwd(op.join(dspath, 'd')):
        save(dataset=ds.path,
             message="committing",
             path="mike2")

        later = op.join(op.pardir, "later")
        ds.repo.add(later, git=True)
        save(dataset=ds.path, message="committing", path=later)

    assert_repo_status(dspath)


@skip_wo_symlink_capability
@with_tempfile(mkdir=True)
def test_bf1886(path):
    parent = Dataset(path).create()
    parent.create('sub')
    assert_repo_status(parent.path)
    # create a symlink pointing down to the subdataset, and add it
    os.symlink('sub', op.join(parent.path, 'down'))
    parent.save('down')
    assert_repo_status(parent.path)
    # now symlink pointing up
    os.makedirs(op.join(parent.path, 'subdir', 'subsubdir'))
    os.symlink(op.join(op.pardir, 'sub'), op.join(parent.path, 'subdir', 'up'))
    parent.save(op.join('subdir', 'up'))
    # 'all' to avoid the empty dir being listed
    assert_repo_status(parent.path, untracked_mode='all')
    # now symlink pointing 2xup, as in #1886
    os.symlink(
        op.join(op.pardir, op.pardir, 'sub'),
        op.join(parent.path, 'subdir', 'subsubdir', 'upup'))
    parent.save(op.join('subdir', 'subsubdir', 'upup'))
    assert_repo_status(parent.path)
    # simulatenously add a subds and a symlink pointing to it
    # create subds, but don't register it
    create(op.join(parent.path, 'sub2'))
    os.symlink(
        op.join(op.pardir, op.pardir, 'sub2'),
        op.join(parent.path, 'subdir', 'subsubdir', 'upup2'))
    parent.save(['sub2', op.join('subdir', 'subsubdir', 'upup2')])
    assert_repo_status(parent.path)
    # full replication of #1886: the above but be in subdir of symlink
    # with no reference dataset
    create(op.join(parent.path, 'sub3'))
    os.symlink(
        op.join(op.pardir, op.pardir, 'sub3'),
        op.join(parent.path, 'subdir', 'subsubdir', 'upup3'))
    # need to use absolute paths
    with chpwd(op.join(parent.path, 'subdir', 'subsubdir')):
        save([op.join(parent.path, 'sub3'),
              op.join(parent.path, 'subdir', 'subsubdir', 'upup3')])
    assert_repo_status(parent.path)


@with_tree({
    '1': '',
    '2': '',
    '3': ''})
def test_gh2043p1(path):
    # this tests documents the interim agreement on what should happen
    # in the case documented in gh-2043
    ds = Dataset(path).create(force=True)
    ds.save('1')
    assert_repo_status(ds.path, untracked=['2', '3'])
    ds.unlock('1')
    assert_repo_status(
        ds.path,
        # on windows we are in an unlocked branch by default, hence
        # we would see no change
        modified=[] if ds.repo.is_managed_branch() else ['1'],
        untracked=['2', '3'])
    # save(.) should recommit unlocked file, and not touch anything else
    # this tests the second issue in #2043
    with chpwd(path):
        # only save modified bits
        save(path='.', updated=True)
    # state of the file (unlocked/locked) is committed as well, and the
    # test doesn't lock the file again
    assert_repo_status(ds.path, untracked=['2', '3'])
    with chpwd(path):
        # but when a path is given, anything that matches this path
        # untracked or not is added/saved
        save(path='.')
    # state of the file (unlocked/locked) is committed as well, and the
    # test doesn't lock the file again
    assert_repo_status(ds.path)


@with_tree({
    'staged': 'staged',
    'untracked': 'untracked'})
def test_bf2043p2(path):
    ds = Dataset(path).create(force=True)
    ds.repo.add('staged')
    assert_repo_status(ds.path, added=['staged'], untracked=['untracked'])
    # save -u does not commit untracked content
    # this tests the second issue in #2043
    with chpwd(path):
        save(updated=True)
    assert_repo_status(ds.path, untracked=['untracked'])


@with_tree({
    OBSCURE_FILENAME + u'_staged': 'staged',
    OBSCURE_FILENAME + u'_untracked': 'untracked'})
def test_encoding(path):
    staged = OBSCURE_FILENAME + u'_staged'
    untracked = OBSCURE_FILENAME + u'_untracked'
    ds = Dataset(path).create(force=True)
    ds.repo.add(staged)
    assert_repo_status(ds.path, added=[staged], untracked=[untracked])
    ds.save(updated=True)
    assert_repo_status(ds.path, untracked=[untracked])


@with_tree(**tree_arg)
def test_add_files(path):
    ds = Dataset(path).create(force=True)

    test_list_1 = ['test_annex.txt']
    test_list_2 = ['test.txt']
    test_list_3 = ['test1.dat', 'test2.dat']
    test_list_4 = [op.join('dir', 'testindir'),
                   op.join('dir', OBSCURE_FILENAME)]

    for arg in [(test_list_1[0], False),
                (test_list_2[0], True),
                (test_list_3, False),
                (test_list_4, False)]:
        # special case 4: give the dir:
        if arg[0] == test_list_4:
            result = ds.save('dir', to_git=arg[1])
            status = ds.repo.annexstatus(['dir'])
        else:
            result = ds.save(arg[0], to_git=arg[1])
            for a in ensure_list(arg[0]):
                assert_result_count(result, 1, path=str(ds.pathobj / a))
            status = ds.repo.get_content_annexinfo(
                ut.Path(p) for p in ensure_list(arg[0]))
        for f, p in status.items():
            if arg[1]:
                assert p.get('key', None) is None, f
            else:
                assert p.get('key', None) is not None, f


@with_tree(**tree_arg)
@with_tempfile(mkdir=True)
def test_add_subdataset(path, other):
    subds = create(op.join(path, 'dir'), force=True)
    ds = create(path, force=True)
    ok_(subds.repo.dirty)
    ok_(ds.repo.dirty)
    assert_not_in('dir', ds.subdatasets(result_xfm='relpaths'))
    # "add everything in subds to subds"
    save(dataset=subds.path)
    assert_repo_status(subds.path)
    assert_not_in('dir', ds.subdatasets(result_xfm='relpaths'))
    # but with a base directory we add the dataset subds as a subdataset
    # to ds
    res = ds.save(subds.path)
    assert_in_results(res, action="add", path=subds.path, refds=ds.path)
    res = ds.subdatasets()
    assert_result_count(res, 1)
    assert_result_count(
        res, 1,
        # essentials
        path=op.join(ds.path, 'dir'),
        gitmodule_url='./dir',
        gitmodule_name='dir',
    )
    #  create another one
    other = create(other)
    # install into superdataset, but don't add
    other_clone = install(source=other.path, path=op.join(ds.path, 'other'))
    # little dance to get the revolution-type dataset
    other_clone = Dataset(other_clone.path)
    ok_(other_clone.is_installed)
    assert_not_in('other', ds.subdatasets(result_xfm='relpaths'))
    # now add, it should pick up the source URL
    ds.save('other')
    # and that is why, we can reobtain it from origin
    ds.uninstall('other')
    ok_(not other_clone.is_installed())
    ds.get('other')
    ok_(other_clone.is_installed())


# CommandError: command '['git', '-c', 'receive.autogc=0', '-c', 'gc.auto=0', 'annex', 'add', '--json', '--', 'empty', 'file.txt']' failed with exitcode 1
# Failed to run ['git', '-c', 'receive.autogc=0', '-c', 'gc.auto=0', 'annex', 'add', '--json', '--', 'empty', 'file.txt'] under 'C:\\Users\\appveyor\\AppData\\Local\\Temp\\1\\datalad_temp_tree_j2mk92y3'. Exit code=1.
@known_failure_windows
@with_tree(tree={
    'file.txt': 'some text',
    'empty': '',
    'file2.txt': 'some text to go to annex',
    '.gitattributes': '* annex.largefiles=(not(mimetype=text/*))'}
)
def test_add_mimetypes(path):
    ds = Dataset(path).create(force=True)
    ds.repo.add('.gitattributes')
    ds.repo.commit('added attributes to git explicitly')
    # now test that those files will go into git/annex correspondingly
    # WINDOWS FAILURE NEXT
    __not_tested__ = ds.save(['file.txt', 'empty'])
    assert_repo_status(path, untracked=['file2.txt'])
    # But we should be able to force adding file to annex when desired
    ds.save('file2.txt', to_git=False)
    # check annex file status
    annexinfo = ds.repo.get_content_annexinfo()
    for path, in_annex in (
           # Empty one considered to be  application/octet-stream
           # i.e. non-text
           ('empty', True),
           ('file.txt', False),
           ('file2.txt', True)):
        # low-level API report -> repo path reference, no ds path
        p = ds.repo.pathobj / path
        assert_in(p, annexinfo)
        if in_annex:
            assert_in('key', annexinfo[p], p)
        else:
            assert_not_in('key', annexinfo[p], p)


@known_failure_appveyor
# ^ Issue only happens on appveyor, Python itself implodes. Cannot be
#   reproduced on a real windows box.
@with_tempfile(mkdir=True)
def test_gh1597(path):
    ds = Dataset(path).create()
    sub = ds.create('sub')
    res = ds.subdatasets()
    assert_result_count(res, 1, path=sub.path)
    # now modify .gitmodules with another command
    ds.subdatasets(contains=sub.path, set_property=[('this', 'that')])
    # now modify low-level
    with open(op.join(ds.path, '.gitmodules'), 'a') as f:
        f.write('\n')
    assert_repo_status(ds.path, modified=['.gitmodules'])
    ds.save('.gitmodules')
    # must not come under annex mangement
    assert_not_in(
        'key',
        ds.repo.annexstatus(paths=['.gitmodules']).popitem()[1])


@with_tempfile(mkdir=True)
def test_gh1597_simpler(path):
    ds = Dataset(path).create()
    # same goes for .gitattributes
    with open(op.join(ds.path, '.gitignore'), 'a') as f:
        f.write('*.swp\n')
    ds.save('.gitignore')
    assert_repo_status(ds.path)
    # put .gitattributes in some subdir and add all, should also go into Git
    attrfile = op.join ('subdir', '.gitattributes')
    ds.repo.set_gitattributes(
        [('*', dict(mycustomthing='this'))],
        attrfile)
    assert_repo_status(ds.path, untracked=[attrfile], untracked_mode='all')
    ds.save()
    assert_repo_status(ds.path)
    # no annex key, not in annex
    assert_not_in(
        'key',
        ds.repo.get_content_annexinfo([ut.Path(attrfile)]).popitem()[1])


@with_tempfile(mkdir=True)
def test_update_known_submodule(path):
    def get_baseline(p):
        ds = Dataset(p).create()
        sub = create(str(ds.pathobj / 'sub'))
        assert_repo_status(ds.path, untracked=['sub'])
        return ds
    # attempt one
    ds = get_baseline(op.join(path, 'wo_ref'))
    with chpwd(ds.path):
        save(recursive=True)
    assert_repo_status(ds.path)

    # attempt two, same as above but call add via reference dataset
    ds = get_baseline(op.join(path, 'w_ref'))
    ds.save(recursive=True)
    assert_repo_status(ds.path)


@with_tempfile(mkdir=True)
def test_add_recursive(path):
    # make simple hierarchy
    parent = Dataset(path).create()
    assert_repo_status(parent.path)
    sub1 = parent.create(op.join('down', 'sub1'))
    assert_repo_status(parent.path)
    sub2 = parent.create('sub2')
    # next one make the parent dirty
    subsub = sub2.create('subsub')
    assert_repo_status(parent.path, modified=['sub2'])
    res = parent.save()
    assert_repo_status(parent.path)

    # now add content deep in the hierarchy
    create_tree(subsub.path, {'new': 'empty'})
    assert_repo_status(parent.path, modified=['sub2'])

    # recursive add should not even touch sub1, because
    # it knows that it is clean
    res = parent.save(recursive=True, jobs=5)
    # the key action is done
    assert_result_count(
        res, 1, path=op.join(subsub.path, 'new'), action='add', status='ok')
    # saved all the way up
    assert_result_count(res, 3, action='save', status='ok')
    assert_repo_status(parent.path)


@with_tree(**tree_arg)
def test_relpath_add(path):
    ds = Dataset(path).create(force=True)
    with chpwd(op.join(path, 'dir')):
        eq_(save('testindir')[0]['path'],
            op.join(ds.path, 'dir', 'testindir'))
        # and now add all
        save('..')
    # auto-save enabled
    assert_repo_status(ds.path)


@skip_wo_symlink_capability
@with_tempfile()
def test_bf2541(path):
    ds = create(path)
    subds = ds.create('sub')
    assert_repo_status(ds.path)
    os.symlink('sub', op.join(ds.path, 'symlink'))
    with chpwd(ds.path):
        res = save(recursive=True)
    assert_repo_status(ds.path)


@with_tempfile()
def test_remove_subds(path):
    ds = create(path)
    ds.create('sub')
    ds.create(op.join('sub', 'subsub'))
    assert_repo_status(ds.path)
    assert_result_count(
        ds.subdatasets(), 1,
        path=op.join(ds.path, 'sub'))
    # all good at this point, subdataset known, dataset clean
    # now have some external force wipe out the subdatasets
    rmtree(op.join(ds.path, 'sub'))
    assert_result_count(
        ds.status(), 1,
        path=op.join(ds.path, 'sub'),
        state='deleted')
    # a single call to save() must fix up the mess
    assert_status('ok', ds.save())
    assert_repo_status(ds.path)


@with_tempfile()
def test_partial_unlocked(path):
    # https://github.com/datalad/datalad/issues/1651
    ds = create(path)
    (ds.pathobj / 'normal.txt').write_text(u'123')
    ds.save()
    assert_repo_status(ds.path)
    ds.unlock('normal.txt')
    ds.save()
    # mixed git and git-annex'ed files
    (ds.pathobj / 'ingit.txt').write_text(u'234')
    ds.save(to_git=True)
    (ds.pathobj / 'culprit.txt').write_text(u'345')
    (ds.pathobj / 'ingit.txt').write_text(u'modified')
    ds.save()
    assert_repo_status(ds.path)
    # but now a change in the attributes
    ds.unlock('culprit.txt')
    ds.repo.set_gitattributes([
        ('*', {'annex.largefiles': 'nothing'})])
    ds.save()
    assert_repo_status(ds.path)


@with_tree({'.gitattributes': "* annex.largefiles=(largerthan=4b)",
            "foo": "in annex"})
def test_save_partial_commit_shrinking_annex(path):
    # This is a variation on the test above. The main difference is that there
    # are other staged changes in addition to the unlocked filed.
    ds = create(path, force=True)
    ds.save()
    assert_repo_status(ds.path)
    ds.unlock(path="foo")
    create_tree(ds.path, tree={"foo": "a", "staged": ""},
                remove_existing=True)
    # Even without this staged change, a plain 'git commit -- foo' would fail
    # with git-annex's partial index error, but save (or more specifically
    # GitRepo.save_) drops the pathspec if there are no staged changes.
    ds.repo.add("staged", git=True)
    if ds.repo.supports_unlocked_pointers:
        ds.save(path="foo")
        assert_repo_status(ds.path, added=["staged"])
    else:
        # Unlike the obsolete interface.save, save doesn't handle a partial
        # commit if there were other staged changes.
        with assert_raises(CommandError) as cm:
            ds.save(path="foo")
        assert_in("partial commit", str(cm.exception))


@with_tempfile()
def test_path_arg_call(path):
    ds = create(path)
    for testfile in (
            ds.pathobj / 'abs.txt',
            ds.pathobj / 'rel.txt'):
        testfile.write_text(u'123')
        # we used to resolve relative paths against a dataset just given by
        # a path, but we no longer do that
        #save(dataset=ds.path, path=[testfile.name], to_git=True)
        save(dataset=ds, path=[testfile.name], to_git=True)


@with_tree(tree={
    'file.txt': 'some text',
    'd1': {
        'subrepo': {
            'subfile': 'more repo text',
        },
    },
    'd2': {
        'subds': {
            'subfile': 'more ds text',
        },
    },
})
def test_surprise_subds(path):
    # https://github.com/datalad/datalad/issues/3139
    ds = create(path, force=True)
    # a lonely repo without any commit
    somerepo = AnnexRepo(path=op.join(path, 'd1', 'subrepo'), create=True)
    # a proper subdataset
    subds = create(op.join(path, 'd2', 'subds'), force=True)

    # If subrepo is an adjusted branch, it would have a commit, making most of
    # this test irrelevant because it is about the unborn branch edge case.
    adjusted = somerepo.is_managed_branch()
    # This edge case goes away with Git v2.22.0.
    fixed_git = somerepo.git_version >= '2.22.0'

    # save non-recursive
    res = ds.save(recursive=False, on_failure='ignore')
    if not adjusted and fixed_git:
        # We get an appropriate error about no commit being checked out.
        assert_in_results(res, action='add_submodule', status='error')

    # the content of both subds and subrepo are not added to their
    # respective parent as no --recursive was given
    assert_repo_status(subds.path, untracked=['subfile'])
    assert_repo_status(somerepo.path, untracked=['subfile'])

    if adjusted or fixed_git:
        if adjusted:
            # adjusted branch: #datalad/3178 (that would have a commit)
            modified = [subds.repo.pathobj, somerepo.pathobj]
            untracked = []
        else:
            # Newer Git versions refuse to add a sub-repository with no commits
            # checked out.
            modified = [subds.repo.pathobj]
            untracked = ['d1']
        assert_repo_status(ds.path, modified=modified, untracked=untracked)
        assert_not_in(ds.repo.pathobj / 'd1' / 'subrepo' / 'subfile',
                      ds.repo.get_content_info())
    else:
        # however, while the subdataset is added (and reported as modified
        # because it content is still untracked) the subrepo
        # cannot be added (it has no commit)
        # worse: its untracked file add been added to the superdataset
        assert_repo_status(ds.path, modified=['d2/subds'])
        assert_in(ds.repo.pathobj / 'd1' / 'subrepo' / 'subfile',
                  ds.repo.get_content_info())
    # with proper subdatasets, all evil is gone
    assert_not_in(ds.repo.pathobj / 'd2' / 'subds' / 'subfile',
                  ds.repo.get_content_info())


@with_tree({"foo": ""})
def test_bf3285(path):
    ds = Dataset(path).create(force=True)
    # Note: Using repo.pathobj matters in the "TMPDIR=/var/tmp/sym\ link" case
    # because assert_repo_status is based off of {Annex,Git}Repo.path, which is
    # the realpath'd path (from the processing in _flyweight_id_from_args).
    subds = create(ds.repo.pathobj.joinpath("subds"))
    # Explicitly saving a path does not save an untracked, unspecified
    # subdataset.
    ds.save("foo")
    assert_repo_status(ds.path, untracked=[subds.path])


@with_tree({"outside": "",
            "ds": {"within": ""}})
def test_on_failure_continue(path):
    ds = Dataset(op.join(path, "ds")).create(force=True)
    # save() calls status() in a way that respects on_failure.
    assert_in_results(
        ds.save(path=[op.join(path, "outside"),
                      op.join(path, "ds", "within")],
                on_failure="ignore"),
        action="status",
        status="error")
    # save() continued despite the failure and saved ds/within.
    assert_repo_status(ds.path)


@with_tree(tree={OBSCURE_FILENAME: "abc"})
def test_save_obscure_name(path):
    ds = Dataset(path).create(force=True)
    fname = OBSCURE_FILENAME
    # Just check that we don't fail with a unicode error.
    with swallow_outputs():
        ds.save(path=fname, result_renderer="default")


@with_tree(tree={
    ".dot": "ab", "nodot": "cd",
    "nodot-subdir": {".dot": "ef", "nodot": "gh"},
    ".dot-subdir": {".dot": "ij", "nodot": "kl"}})
def check_save_dotfiles(to_git, save_path, path):
    # Note: Take relpath to work with Travis "TMPDIR=/var/tmp/sym\ link" run.
    paths = [Path(op.relpath(op.join(root, fname), path))
             for root, _, fnames in os.walk(op.join(path, save_path or ""))
             for fname in fnames]
    ok_(paths)
    ds = Dataset(path).create(force=True)
    if not to_git and ds.repo.is_managed_branch():
        ver = ds.repo.git_annex_version
        if "8" < ver < "8.20200309":
            # git-annex's 1978a2420 (2020-03-09) fixed a bug where
            # annexed dotfiles could switch when annex.dotfiles=true
            # was not set in .git/config or git-annex:config.log.
            ds.repo.config.set("annex.dotfiles", "true",
                               where="local", reload=True)
        elif ver < "8" and save_path is None:
            raise SkipTest("Fails with annex version below v8.*")

    ds.save(save_path, to_git=to_git)
    if save_path is None:
        assert_repo_status(ds.path)
    repo = ds.repo
    annexinfo = repo.get_content_annexinfo()

    def _check(fn, p):
        fn("key", annexinfo[repo.pathobj / p], p)

    if to_git:
        def check(p):
            _check(assert_not_in, p)
    else:
        def check(p):
            _check(assert_in, p)

    for path in paths:
        check(path)


def test_save_dotfiles():
    for git in [True, False, None]:
        for save_path in [None, "nodot-subdir"]:
            yield check_save_dotfiles, git, save_path


@with_tempfile
def test_save_nested_subs_explicit_paths(path):
    ds = Dataset(path).create()
    spaths = [Path("s1"), Path("s1", "s2"), Path("s1", "s2", "s3")]
    for spath in spaths:
        Dataset(ds.pathobj / spath).create()
    ds.save(path=spaths)
    eq_(set(ds.subdatasets(recursive=True, result_xfm="relpaths")),
        set(map(str, spaths)))


@with_tempfile
def test_save_gitrepo_annex_subds_adjusted(path):
    ds = Dataset(path).create(annex=False)
    subds = ds.create("sub")
    maybe_adjust_repo(subds.repo)
    (subds.pathobj / "foo").write_text("foo")
    subds.save()
    ds.save()
    assert_repo_status(ds.path)


@known_failure
@with_tempfile
def test_save_adjusted_partial(path):
    ds = Dataset(path).create()
    subds = ds.create("sub")
    maybe_adjust_repo(subds.repo)
    (subds.pathobj / "foo").write_text("foo")
    subds.save()
    (ds.pathobj / "other").write_text("staged, not for committing")
    ds.repo.call_git(["add", "other"])
    ds.save(path=["sub"])
    assert_repo_status(ds.path, added=["other"])
