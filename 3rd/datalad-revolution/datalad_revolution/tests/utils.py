# -*- coding: utf-8 -*-

import os
import os.path as op
import shutil
import tempfile
from six import iteritems
from functools import wraps
from nose.plugins.attrib import attr

from datalad.api import (
    rev_create as create,
)

from datalad_revolution.gitrepo import RevolutionGitRepo as GitRepo
from datalad_revolution.annexrepo import RevolutionAnnexRepo as AnnexRepo
from datalad_revolution.dataset import RevolutionDataset as Dataset

from datalad.tests.utils import (
    assert_is,
    create_tree,
    eq_,
    SkipTest,
)

import datalad_revolution.utils as ut


def assert_repo_status(path, annex=None, untracked_mode='normal', **kwargs):
    """Compare a repo status against (optional) exceptions.

    Anything file/directory that is not explicitly indicated must have
    state 'clean', i.e. no modifications and recorded in Git.

    This is an alternative to the traditional `ok_clean_git` helper.

    Parameters
    ----------
    path: str or Repo
      in case of a str: path to the repository's base dir;
      Note, that passing a Repo instance prevents detecting annex. This might
      be useful in case of a non-initialized annex, a GitRepo is pointing to.
    annex: bool or None
      explicitly set to True or False to indicate, that an annex is (not)
      expected; set to None to autodetect, whether there is an annex.
      Default: None.
    untracked_mode: {'no', 'normal', 'all'}
      If and how untracked content is reported. The specification of untracked
      files that are OK to be found must match this mode. See `Repo.status()`
    **kwargs
      Files/directories that are OK to not be in 'clean' state. Each argument
      must be one of 'added', 'untracked', 'deleted', 'modified' and each
      value must be a list of filenames (relative to the root of the
      repository, in POSIX convention).
    """
    r = None
    if isinstance(path, AnnexRepo):
        if annex is None:
            annex = True
        # if `annex` was set to False, but we find an annex => fail
        assert_is(annex, True)
        r = path
    elif isinstance(path, GitRepo):
        if annex is None:
            annex = False
        # explicitly given GitRepo instance doesn't make sense with
        # 'annex' True
        assert_is(annex, False)
        r = path
    else:
        # 'path' is an actual path
        try:
            r = AnnexRepo(path, init=False, create=False)
            if annex is None:
                annex = True
            # if `annex` was set to False, but we find an annex => fail
            assert_is(annex, True)
        except Exception:
            # Instantiation failed => no annex
            try:
                r = GitRepo(path, init=False, create=False)
            except Exception:
                raise AssertionError("Couldn't find an annex or a git "
                                     "repository at {}.".format(path))
            if annex is None:
                annex = False
            # explicitly given GitRepo instance doesn't make sense with
            # 'annex' True
            assert_is(annex, False)

    status = r.status(untracked=untracked_mode)
    # for any file state that indicates some kind of change (all but 'clean)
    for state in ('added', 'untracked', 'deleted', 'modified'):
        oktobefound = sorted(r.pathobj.joinpath(ut.PurePosixPath(p))
                             for p in kwargs.get(state, []))
        state_files = sorted(k for k, v in iteritems(status)
                             if v.get('state', None) == state)
        eq_(state_files, oktobefound,
            'unexpected content of state "%s": %r != %r'
            % (state, state_files, oktobefound))


def get_convoluted_situation(path, repocls=AnnexRepo):
    if 'APPVEYOR' in os.environ:
        # issue only happens on appveyor, Python itself implodes
        # cannot be reproduced on a real windows box
        raise SkipTest(
            'get_convoluted_situation() causes appveyor to crash, '
            'reason unknown')
    repo = repocls(path, create=True)
    # use create(force) to get an ID and config into the empty repo
    ds = Dataset(repo.path).rev_create(force=True)
    # base content
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_clean': 'file_clean',
                'file_deleted': 'file_deleted',
                'file_modified': 'file_clean',
            },
            'file_clean': 'file_clean',
            'file_deleted': 'file_deleted',
            'file_staged_deleted': 'file_staged_deleted',
            'file_modified': 'file_clean',
        }
    )
    if isinstance(ds.repo, AnnexRepo):
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_dropped_clean': 'file_dropped_clean',
                },
                'file_dropped_clean': 'file_dropped_clean',
            }
        )
    ds.rev_save()
    if isinstance(ds.repo, AnnexRepo):
        # some files straight in git
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_ingit_clean': 'file_ingit_clean',
                    'file_ingit_modified': 'file_ingit_clean',
                },
                'file_ingit_clean': 'file_ingit_clean',
                'file_ingit_modified': 'file_ingit_clean',
            }
        )
        ds.rev_save(to_git=True)
        ds.drop([
            'file_dropped_clean',
            op.join('subdir', 'file_dropped_clean')],
            check=False)
    # clean and proper subdatasets
    ds.rev_create('subds_clean')
    ds.rev_create(op.join('subdir', 'subds_clean'))
    ds.rev_create('subds_unavailable_clean')
    ds.rev_create(op.join('subdir', 'subds_unavailable_clean'))
    # uninstall some subdatasets (still clean)
    ds.uninstall([
        'subds_unavailable_clean',
        op.join('subdir', 'subds_unavailable_clean')],
        check=False)
    assert_repo_status(ds.path)
    # make a dirty subdataset
    ds.rev_create('subds_modified')
    ds.rev_create(op.join('subds_modified', 'someds'))
    ds.rev_create(op.join('subds_modified', 'someds', 'dirtyds'))
    # make a subdataset with additional commits
    ds.rev_create(op.join('subdir', 'subds_modified'))
    pdspath = op.join(ds.path, 'subdir', 'subds_modified', 'progressedds')
    ds.rev_create(pdspath)
    create_tree(
        pdspath,
        {'file_clean': 'file_ingit_clean'}
    )
    Dataset(pdspath).rev_save()
    assert_repo_status(pdspath)
    # staged subds, and files
    create(op.join(ds.path, 'subds_added'))
    ds.repo.add_submodule('subds_added')
    create(op.join(ds.path, 'subdir', 'subds_added'))
    ds.repo.add_submodule(op.join('subdir', 'subds_added'))
    # some more untracked files
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_untracked': 'file_untracked',
                'file_added': 'file_added',
            },
            'file_untracked': 'file_untracked',
            'file_added': 'file_added',
            'dir_untracked': {
                'file_untracked': 'file_untracked',
            },
            'subds_modified': {
                'someds': {
                    "dirtyds": {
                        'file_untracked': 'file_untracked',
                    },
                },
            },
        }
    )
    ds.repo.add(['file_added', op.join('subdir', 'file_added')])
    # untracked subdatasets
    create(op.join(ds.path, 'subds_untracked'))
    create(op.join(ds.path, 'subdir', 'subds_untracked'))
    # deleted files
    os.remove(op.join(ds.path, 'file_deleted'))
    os.remove(op.join(ds.path, 'subdir', 'file_deleted'))
    # staged deletion
    ds.repo.remove('file_staged_deleted')
    # modified files
    if isinstance(ds.repo, AnnexRepo):
        ds.repo.unlock(['file_modified', op.join('subdir', 'file_modified')])
        create_tree(
            ds.path,
            {
                'subdir': {
                    'file_ingit_modified': 'file_ingit_modified',
                },
                'file_ingit_modified': 'file_ingit_modified',
            }
        )
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_modified': 'file_modified',
            },
            'file_modified': 'file_modified',
        }
    )
    return ds


def get_deeply_nested_structure(path):
    """ Here is what this does (assuming UNIX, locked):
    .
    ├── directory_untracked
    │   └── link2dir -> ../subdir
    ├── file_modified
    ├── link2dir -> subdir
    ├── link2subdsdir -> subds_modified/subdir
    ├── link2subdsroot -> subds_modified
    ├── subdir
    │   ├── annexed_file.txt -> ../.git/annex/objects/...
    │   ├── file_modified
    │   ├── git_file.txt
    │   └── link2annex_files.txt -> annexed_file.txt
    └── subds_modified
        ├── link2superdsdir -> ../subdir
        ├── subdir
        │   └── annexed_file.txt -> ../.git/annex/objects/...
        └── subds_lvl1_modified
            └── directory_untracked
    """
    ds = Dataset(path).rev_create()
    (ds.pathobj / 'subdir').mkdir()
    (ds.pathobj / 'subdir' / 'annexed_file.txt').write_text(u'dummy')
    ds.rev_save()
    (ds.pathobj / 'subdir' / 'git_file.txt').write_text(u'dummy')
    ds.rev_save(to_git=True)
    # a subtree of datasets
    subds = ds.rev_create('subds_modified')
    # another dataset, plus an additional dir in it
    (Dataset(
        ds.create(
            op.join('subds_modified', 'subds_lvl1_modified')
        ).path).pathobj / 'directory_untracked').mkdir()
    create_tree(
        ds.path,
        {
            'subdir': {
                'file_modified': 'file_modified',
            },
            'file_modified': 'file_modified',
        }
    )
    (ut.Path(subds.path) / 'subdir').mkdir()
    (ut.Path(subds.path) / 'subdir' / 'annexed_file.txt').write_text(u'dummy')
    subds.rev_save()
    (ds.pathobj / 'directory_untracked').mkdir()
    # symlink farm #1
    # symlink to annexed file
    (ds.pathobj / 'subdir' / 'link2annex_files.txt').symlink_to(
        'annexed_file.txt')
    # symlink to directory within the dataset
    (ds.pathobj / 'link2dir').symlink_to('subdir')
    # upwards pointing symlink to directory within the same dataset
    (ds.pathobj / 'directory_untracked' / 'link2dir').symlink_to(
        op.join('..', 'subdir'))
    # symlink pointing to a subdataset mount in the same dataset
    (ds.pathobj / 'link2subdsroot').symlink_to('subds_modified')
    # symlink to a dir in a subdataset (across dataset boundaries)
    (ds.pathobj / 'link2subdsdir').symlink_to(
        op.join('subds_modified', 'subdir'))
    # symlink to a dir in a superdataset (across dataset boundaries)
    (ut.Path(subds.path) / 'link2superdsdir').symlink_to(
        op.join('..', 'subdir'))
    return ds


def has_symlink_capability():
    try:
        wdir = ut.Path(tempfile.mkdtemp())
        (wdir / 'target').touch()
        (wdir / 'link').symlink_to(wdir / 'target')
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(str(wdir))


def skip_wo_symlink_capability(func):
    """Skip test when environment does not support symlinks

    Perform a behavioral test instead of top-down logic, as on
    windows this could be on or off on a case-by-case basis.
    """
    @wraps(func)
    @attr('skip_wo_symlink_capability')
    def newfunc(*args, **kwargs):
        if not has_symlink_capability():
            raise SkipTest("no symlink capabilities")
        return func(*args, **kwargs)
    return newfunc
