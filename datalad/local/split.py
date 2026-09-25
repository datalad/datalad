# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Split directories of a dataset out into subdatasets"""

__docformat__ = 'restructuredtext'

import logging
import os
import shlex
import sys
import uuid
from pathlib import (
    Path,
    PurePosixPath,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    require_dataset,
    resolve_path,
)
from datalad.interface.base import (
    Interface,
    build_doc,
    eval_results,
)
from datalad.interface.results import get_status_dict
from datalad.runner import (
    Runner,
    StdOutCapture,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.exceptions import CommandError
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import (
    ensure_list,
    rmtree,
)

lgr = logging.getLogger('datalad.local.split')

_FIXLINKS = Path(__file__).with_name('_split_fixlinks.py')


@build_doc
class Split(Interface):
    """Split directories of a dataset out into new subdatasets

    Each given directory is turned into a subdataset whose history is the
    history of that directory in the parent (via ``git filter-branch
    --subdirectory-filter``), with git-annex symlinks adjusted to their new
    location throughout that history. The new subdataset's git-annex branch
    only retains information on keys used in that history, and annexed
    content present in the parent is obtained (hardlinked where possible).
    The history of the parent dataset is not rewritten: the directory's
    content is replaced by the subdataset in a new commit. Annexed content
    that is no longer used in the parent can be dropped from it with
    ``git annex unused`` and ``git annex dropunused``.

    The dataset must not have any modifications or untracked files.
    Directories containing subdatasets, as well as datasets on an adjusted
    branch, are not supported.
    """

    _params_ = dict(
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""directory to split out into a subdataset""",
            nargs="+",
            constraints=EnsureStr()),
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc="""specify the dataset to split. If no dataset is given, an
            attempt is made to identify the dataset based on the current
            working directory.""",
            constraints=EnsureDataset() | EnsureNone()),
    )

    _examples_ = [
        dict(text="Turn directory 'data/raw' into a subdataset",
             code_py="split('data/raw')",
             code_cmd="datalad split data/raw"),
    ]

    @staticmethod
    @datasetmethod(name='split')
    @eval_results
    def __call__(path, *, dataset=None):
        ds = require_dataset(dataset, check_installed=True, purpose='split')
        res_kwargs = dict(action='split', logger=lgr, refds=ds.path)
        repo = ds.repo

        def impossible(message, p=ds.pathobj):
            return get_status_dict(
                status='impossible', path=str(p), message=message,
                **res_kwargs)

        if isinstance(repo, AnnexRepo) and repo.is_managed_branch():
            yield impossible('datasets on an adjusted branch are not supported')
            return
        if repo.dirty:
            yield impossible('dataset has modifications or untracked files')
            return

        todo = []  # (abspath, git-facing relpath)
        for p in resolve_path(ensure_list(path), ds=dataset):
            p = Path(os.path.normpath(p))
            rel = PurePosixPath(p.relative_to(ds.pathobj).as_posix()) \
                if ds.pathobj in p.parents else None
            msg = None
            if rel is None:
                msg = 'path is not a directory within the dataset'
            elif any(rel == o or rel in o.parents or o in rel.parents
                     for _, o in todo):
                msg = 'path overlaps with another path to split'
            else:
                try:
                    types = {line.split(' ', 2)[1] for line in repo.call_git_items_(
                        ['ls-tree', '-r', f'HEAD:{rel}'], read_only=True)}
                except CommandError:
                    types = set()  # not a directory in HEAD
                if not types:
                    msg = 'path is not a directory with tracked content'
                elif 'commit' in types:
                    msg = 'splitting directories with subdatasets ' \
                          'is not supported'
                elif repo.call_git(
                        ['ls-files', '-o', '-i', '--exclude-standard',
                         '--directory', '--', f':(literal){rel}'],
                        read_only=True):
                    msg = 'directory contains ignored files'
            if msg:
                yield impossible(msg, p)
                return
            todo.append((p, rel))

        for i, (p, rel) in enumerate(todo):
            try:
                _split_one(ds, p, rel)
            except Exception as e:
                # the dataset was clean: undo everything done so far
                for q, _ in todo[:i + 1]:
                    if q.exists():
                        rmtree(q)
                repo.call_git(['reset', '-q', '--hard'])
                yield get_status_dict(
                    status='error', path=str(p), exception=e, **res_kwargs)
                return
        # the index holds nothing but the split. Not using `save`: it would
        # re-add the removed files, which now exist again (inside the
        # subdatasets)
        repo.call_git(['commit', '-q', '-m', '[DATALAD] Split {} into subdataset{}'.format(
            ', '.join(str(rel) for _, rel in todo), 's' if len(todo) > 1 else '')])
        for p, _ in todo:
            yield get_status_dict(
                status='ok', path=str(p), type='dataset', **res_kwargs)


def _split_one(ds, path, rel):
    """Replace directory `path` (`rel` relative to `ds`) with a subdataset"""
    parent = ds.repo
    is_annex = isinstance(parent, AnnexRepo)
    lgr.info('Splitting %s out of %s', rel, ds)
    parent.call_git(['rm', '-r', '-q', '--', f':(literal){rel}'])
    # a bare clone of just the current branch (bare, so filter-branch does
    # not demand a checkout), turned into a regular repository after filtering
    parent.call_git([
        'clone', '-q', '--bare', '--single-branch', '--no-tags',
        # regardless of clone.defaultRemoteName
        '--origin', 'origin',
        ds.path, str(path / '.git')])
    sub = GitRepo(path)
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING='1',
               GIT_LITERAL_PATHSPECS='1')
    cmd = ['filter-branch', '--subdirectory-filter', str(rel)]
    if is_annex:
        # annex symlinks moved up len(rel.parts) directories
        cmd += ['--index-filter', ' '.join(map(shlex.quote, (
            sys.executable, str(_FIXLINKS), str(len(rel.parts)))))]
    sub.call_git(cmd + ['--', 'HEAD'], env=env)
    # nothing but the rewritten branch should remain from the parent
    for ref in sub.call_git_items_(
            ['for-each-ref', '--format=%(refname)', 'refs/original'],
            read_only=True):
        sub.call_git(['update-ref', '-d', ref])
    sub.call_git(['config', 'core.bare', 'false'])
    if is_annex:
        sub.call_git(['fetch', '-q', 'origin', 'git-annex:git-annex'])
        sub = AnnexRepo(path, create=False, init=True)
        # keep only information on keys used in the new history: hand all
        # of its trees to git-annex as subtrees of a single tree
        trees = dict.fromkeys(sub.call_git_items_(
            ['log', '--format=%T', 'HEAD'], read_only=True))
        alltrees = Runner(cwd=str(path)).run(
            ['git', 'mktree'], protocol=StdOutCapture,
            stdin=''.join(f'040000 tree {t}\t{i}\n'
                          for i, t in enumerate(trees)).encode(),
        )['stdout'].strip()
        annex_branch = sub.call_annex_oneline([
            'filter-branch', '--branch', alltrees,
            '--include-all-key-information', '--include-all-repo-config',
            '--include-global-config'])
        sub.call_git(['update-ref', 'refs/heads/git-annex', annex_branch])
        # git-annex would merge its (unfiltered) index back into the branch
        (sub.dot_git / 'annex' / 'index').unlink(missing_ok=True)
    # drop the parent's objects, also those still referenced by reflogs
    # (e.g. of the unfiltered git-annex branch)
    sub.call_git(['reflog', 'expire', '--expire=now', '--all'])
    sub.call_git(['gc', '-q', '--prune=now'])
    sub.call_git(['reset', '-q', '--hard'])
    if is_annex:
        sub.call_annex([
            'get', '-c', 'annex.hardlink=true', '--from', 'origin',
            '--in', 'origin', '.'])
    # the parent's history is unrelated to the subdataset's
    sub.call_git(['remote', 'remove', 'origin'])
    subid = None
    if ds.id:
        # an identity of its own (`create` would refuse, seeing the parent's
        # not yet saved content at this location)
        subid = str(uuid.uuid4())
        (path / '.datalad').mkdir(exist_ok=True)
        sub.call_git(['config', '-f', '.datalad/config',
                      'datalad.dataset.id', subid])
        sub.call_git(['add', '.datalad/config'])
        sub.call_git(['commit', '-q', '-m', '[DATALAD] new dataset'])
    # register in the parent
    parent.call_git(['update-index', '--add', '--cacheinfo',
                     f'160000,{sub.get_hexsha()},{rel}'])
    for k, v in (('path', rel), ('url', f'./{rel}'), ('datalad-id', subid)):
        if v:
            parent.call_git(['config', '-f', '.gitmodules',
                             f'submodule.{rel}.{k}', str(v)])
    parent.call_git(['add', '.gitmodules'])
