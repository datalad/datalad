# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test drop command"""

import os.path as op

from datalad.api import (
    Dataset,
    clone,
    drop,
)
from datalad.distributed.drop import (
    _detect_nondead_annex_at_remotes,
    _detect_unpushed_revs,
)
from datalad.support.exceptions import (
    IncompleteResultsError,
    NoDatasetFound,
)
from datalad.tests.utils import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    OBSCURE_FILENAME,
    assert_in,
    assert_in_results,
    assert_raises,
    assert_result_count,
    assert_true,
    eq_,
    get_deeply_nested_structure,
    with_tempfile,
)
from datalad.utils import chpwd


@with_tempfile
@with_tempfile
def test_drop_file_content(path, outside_path):
    # see docstring for test data structure
    ds = get_deeply_nested_structure(path)
    axfile_rootds = op.join("subdir", "annexed_file.txt")
    axfile_subds = op.join("subds_modified", "subdir", "annexed_file.txt")
    gitfile = op.join("subdir", "git_file.txt")

    # refuse to operate on non-ds paths
    assert_in_results(
        ds.drop(outside_path, on_failure='ignore'),
        status='error',
        message=('path not underneath the reference dataset %s', ds)
    )
    # we only have a single copy of annexed files right now
    # check that it is not dropped by default
    with assert_raises(IncompleteResultsError) as cme:
        ds.drop(axfile_rootds)
    # The --force suggestion from git-annex-drop is translated to --reckless.
    assert_in("--reckless", str(cme.exception))

    # error on non-existing paths
    non_existant_relpaths = ['funky', op.join('subds_modified', 'subfunky')]
    res = ds.drop(non_existant_relpaths, on_failure='ignore')
    # only two results, one per file
    assert_result_count(res, len(non_existant_relpaths))
    for rp in non_existant_relpaths:
        assert_in_results(
            res,
            type='file',
            status='error',
            action='drop',
            message='not found',
            path=str(ds.pathobj / rp),
            refds=ds.path,
        )

    # drop multiple files from different datasets
    res = ds.drop(
        [axfile_rootds, axfile_subds],
        reckless='availability',
        jobs=2,
        on_failure='ignore')
    assert_result_count(res, 2)
    for rp in [axfile_rootds, axfile_subds]:
        assert_in_results(
            res,
            type='file',
            status='ok',
            action='drop',
            path=str(ds.pathobj / rp),
            refds=ds.path,
        )

    # dropping file content for files in git
    res = ds.drop(gitfile, on_failure='ignore')
    assert_result_count(res, 1)
    assert_in_results(
        res,
        type='file',
        # why is this 'notneeded' and not 'impossible'
        # if the latter, any operation on any dataset with a
        # single file in git would fail
        status='notneeded',
        action='drop',
        message="no annex'ed content",
        path=str(ds.pathobj / gitfile),
        refds=ds.path,
    )

    # modified files, we cannot drop their content
    modfile = ds.pathobj / axfile_rootds
    modfile.unlink()
    modfile.write_text('new content')
    res = ds.drop(modfile, on_failure='ignore')
    assert_in_results(
        res,
        status='impossible',
        action='drop',
        message="cannot drop modified content, save first",
        path=str(modfile),
        refds=ds.path,
    )

    # detection of untracked content
    untrackeddir = ds.pathobj / 'subds_modified' / 'subds_lvl1_modified' / \
        f'{OBSCURE_FILENAME}_directory_untracked'
    res = ds.drop(untrackeddir, on_failure='ignore')
    assert_in_results(
        res,
        status='impossible',
        action='drop',
        message="cannot drop untracked content, save first",
        path=str(untrackeddir),
        type='directory',
        refds=ds.path,
    )

    # and lastly, recursive drop
    res = ds.drop(recursive=True, on_failure='ignore')
    # there is not much to test here (we already dropped the only
    # annexed files above). however, we should see results from the top
    # ds, and the most-bottom ds
    # subdatasets
    for p in [ds.pathobj / 'subdir' / 'file_modified',
              untrackeddir]:
        assert_in_results(res, path=str(p))


@with_tempfile
@with_tempfile
def test_drop_allkeys(origpath, clonepath):
    # create a dataset with two keys, belonging to two files,
    # in two different branches
    ds = Dataset(origpath).create()
    repo = ds.repo
    repo.call_git(['checkout', '-b', 'otherbranch'])
    (ds.pathobj / 'file1').write_text('file1')
    ds.save()
    repo.call_git(['checkout', DEFAULT_BRANCH])
    (ds.pathobj / 'file2').write_text('file2')
    ds.save()

    # confirm we have two keys
    eq_(2, repo.call_annex_records(['info'])[0]['local annex keys'])

    # do it wrong first
    assert_in_results(
        ds.drop('some', what='allkeys', on_failure='ignore'),
        status='impossible',
        type='dataset',
        action='drop',
        message=(
            'cannot drop %s, with path constraints given: %s',
            'allkeys', [ds.pathobj / 'some']),
    )
    # confirm we still have two keys
    eq_(2, repo.call_annex_records(['info'])[0]['local annex keys'])

    # clone the beast and get all keys into the clone
    dsclone = clone(ds.path, clonepath)
    dsclone.repo.call_annex(['get', '--all'])
    # confirm we have two keys in the clone
    eq_(2, dsclone.repo.call_annex_records(['info'])[0]['local annex keys'])

    # now cripple availability by dropping the "hidden" key at origin
    repo.call_annex(['drop', '--branch', 'otherbranch', '--force'])
    # confirm one key left
    eq_(1, repo.call_annex_records(['info'])[0]['local annex keys'])

    # and now drop all keys from the clone, one is redundant and can be
    # dropped, the other is not and must fail
    res = dsclone.drop(what='allkeys', on_failure='ignore')
    # confirm one key gone, one left
    eq_(1, dsclone.repo.call_annex_records(['info'])[0]['local annex keys'])
    assert_result_count(res, 1, action='drop', status='error', type='key')
    assert_result_count(res, 1, action='drop', status='ok', type='key')
    # now force it
    res = dsclone.drop(what='allkeys', reckless='availability',
                       on_failure='ignore')
    assert_result_count(res, 1)
    assert_result_count(res, 1, action='drop', status='ok', type='key')
    # all gone
    eq_(0, dsclone.repo.call_annex_records(['info'])[0]['local annex keys'])


@with_tempfile
@with_tempfile
@with_tempfile
def test_undead_annex_detection(gitpath, origpath, clonepath):
    gitds = Dataset(gitpath).create(annex=False)
    # a gitrepo can be inspected too, it might just not know anything
    eq_([], _detect_nondead_annex_at_remotes(gitds.repo, 'someid'))

    origds = Dataset(origpath).create()
    origrepo = origds.repo
    # only the local repo knows about its own annex
    eq_([None], _detect_nondead_annex_at_remotes(origrepo, origrepo.uuid))

    # works with clones
    cloneds = clone(origds, clonepath)
    clonerepo = cloneds.repo
    # the clone now know two locations, itself and origin
    eq_([None, DEFAULT_REMOTE],
        _detect_nondead_annex_at_remotes(clonerepo, origrepo.uuid))
    # just from cloning the original repo location does not learn
    # about the new annex in the clone
    eq_([], _detect_nondead_annex_at_remotes(origrepo, clonerepo.uuid))
    # it will know after a push
    cloneds.push()
    eq_([None], _detect_nondead_annex_at_remotes(origrepo, clonerepo.uuid))
    # we can declare an annex dead (here done at original location)
    origrepo.call_annex(['dead', clonerepo.uuid])
    eq_([], _detect_nondead_annex_at_remotes(origrepo, clonerepo.uuid))
    # again not automatically communicated to clones
    eq_([None, DEFAULT_REMOTE],
        _detect_nondead_annex_at_remotes(clonerepo, clonerepo.uuid))
    # but a fetch will make the death known
    clonerepo.call_git(['fetch'])
    eq_([None],
        _detect_nondead_annex_at_remotes(clonerepo, clonerepo.uuid))
    # after a local git-annex branch synchronization, it is completely
    # "gone"
    clonerepo.localsync()
    eq_([],
        _detect_nondead_annex_at_remotes(clonerepo, clonerepo.uuid))


@with_tempfile
def test_uninstall_recursive(path):
    ds = Dataset(path).create()
    subds = ds.create('sub')

    # fail to uninstall with subdatasets present
    res = ds.drop(
        what='all', reckless='availability', on_failure='ignore')
    assert_in_results(
        res,
        action='uninstall',
        path=ds.path,
        type='dataset',
        status='error',
        message=('cannot drop dataset, subdataset(s) still present '
                 '(forgot --recursive?): %s', [subds.path]),
    )
    res = ds.drop(
        what='all', reckless='availability', recursive=True,
        on_failure='ignore')
    # both datasets gone
    assert_result_count(res, 2)
    assert_result_count(res, 2, type='dataset', status='ok')
    # the subdataset is reported first
    eq_([subds.path, ds.path],
        [r.get('path') for r in res])
    # no dataset installed anymore
    eq_(ds.is_installed(), False)
    # not even a trace
    eq_(ds.pathobj.exists(), False)


@with_tempfile
@with_tempfile
def test_unpushed_state_detection(origpath, clonepath):
    origds = Dataset(origpath).create()
    # always test in annex mode
    tester = lambda x: _detect_unpushed_revs(x, True)

    origrepo = origds.repo
    # this is still a unique repo, all payload branches are
    # unpushed
    eq_([DEFAULT_BRANCH], tester(origrepo))
    origrepo.call_git(['checkout', '-b', 'otherbranch'])
    eq_([DEFAULT_BRANCH, 'otherbranch'],
        tester(origrepo))
    # let's advance the state by one
    (origds.pathobj / 'file1').write_text('some text')
    origds.save()
    # same picture
    eq_([DEFAULT_BRANCH, 'otherbranch'],
        tester(origrepo))
    # back to original branch
    origrepo.call_git(['checkout', DEFAULT_BRANCH])

    # now lets clone
    cloneds = clone(origds, clonepath)
    clonerepo = cloneds.repo
    # right after the clone there will be no unpushed changes
    eq_([], tester(clonerepo))
    # even with more than one branch in the clone
    clonerepo.call_git(['checkout', '-t', f'{DEFAULT_REMOTE}/otherbranch'])
    eq_([], tester(clonerepo))

    # let's advance the local state now
    (cloneds.pathobj / 'file2').write_text('some other text')
    cloneds.save()
    # only the modified branch is detected
    eq_(['otherbranch'], tester(clonerepo))
    # a push will bring things into the clear
    cloneds.push(to=DEFAULT_REMOTE)
    eq_([], tester(clonerepo))


@with_tempfile(mkdir=True)
@with_tempfile
@with_tempfile
def test_safetynet(otherpath, origpath, clonepath):
    # we start with a dataset that is hosted somewhere
    origds = Dataset(origpath).create()
    # a clone is made to work on the dataset
    cloneds = clone(origds, clonepath)
    # checkout a different branch at origin to simplify testing below
    origds.repo.call_git(['checkout', '-b', 'otherbranch'])

    # an untracked file is added to simulate some work
    (cloneds.pathobj / 'file1').write_text('some text')
    # now we try to drop the entire dataset in a variety of ways
    # to check that it does not happen too quickly

    # cannot simple run drop somewhere and give a path to a dataset
    # to drop
    with chpwd(otherpath):
        assert_raises(NoDatasetFound, drop, clonepath, what='all')
    assert_true(cloneds.is_installed())

    # refuse to remove the CWD
    with chpwd(clonepath):
        assert_raises(RuntimeError, drop, what='all')
    assert_true(cloneds.is_installed())

    assert_in_results(
        cloneds.drop(what='all', on_failure='ignore'),
        message='cannot drop untracked content, save first',
        status='impossible')
    assert_true(cloneds.is_installed())

    # so let's save...
    cloneds.save()
    # - branch is progressed
    # - a new key is only available here
    res = cloneds.drop(what='all', on_failure='ignore')
    assert_in_results(res, action="uninstall", status="error")
    assert_true(res[0]['message'][0].startswith(
        "to-be-dropped dataset has revisions "
        "that are not available at any known sibling"))
    assert_true(cloneds.is_installed())

    # so let's push -- git only
    # we cannot use git-push directly, it would not handle
    # managed branches properly
    cloneds.push(data='nothing')

    res = cloneds.drop(what='all', on_failure='ignore')
    assert_in_results(res, action="uninstall", status="error")
    assert_true(res[0]['message'][0].startswith(
        "to-be-deleted local annex not declared 'dead'"))
    # some windows test setup is not very robust, explicitly
    # include the default name "origin" in the test success
    # conditions to make this more robust
    eq_(res[0]['message'][1], [DEFAULT_REMOTE])
    assert_true(cloneds.is_installed())

    # announce dead
    cloneds.repo.call_annex(['dead', 'here'])
    # but just a local declaration is not good enough
    assert_in_results(
        cloneds.drop(what='all', on_failure='ignore'),
        status='error')
    assert_true(cloneds.is_installed())

    # so let's push that announcement also
    cloneds.push(data='nothing')

    res = cloneds.drop(what='all', on_failure='ignore')
    assert_in_results(res, action="drop", status="error")
    assert_true(res[0]['message'].startswith(
        "unsafe\nCould only verify the existence of "
        "0 out of 1 necessary"),
        msg=f"Results were {res}")
    assert_true(cloneds.is_installed())

    # so let's push all
    cloneds.push()

    # and kill the beast!
    res = cloneds.drop(what='all', on_failure='ignore')
    # only now we also drop the key!
    assert_result_count(res, 2)
    assert_in_results(
        res, action='drop', type='key', status='ok', path=cloneds.path)
    assert_in_results(
        res, action='uninstall', type='dataset', status='ok', path=cloneds.path)


@with_tempfile
def test_kill(path):
    # create a complicated and dirty mess
    ds = get_deeply_nested_structure(path)
    # cannot use kill without recursion enabled, because there will be no
    # checks for subdatasets, hence we cannot make the impression that
    # this would be a surgical operation
    assert_raises(ValueError, ds.drop, what='all', reckless='kill')
    # wipe it out
    res = ds.drop(what='all', reckless='kill', recursive=True)
    assert_result_count(res, 1)
    assert_in_results(
        res,
        status='ok',
        path=ds.path,
        type='dataset',
        action='uninstall',
    )
    eq_(False, ds.is_installed())
    eq_(False, ds.pathobj.exists())
