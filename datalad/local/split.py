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
    Dataset,
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
from datalad.support.gitrepo import GitRepo
from datalad.support.param import Parameter
from datalad.utils import ensure_list

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

        abspaths = resolve_path(ensure_list(path), ds=dataset)
        relpaths = []
        for p in abspaths:
            # git-facing relative path
            rel = PurePosixPath(p.relative_to(ds.pathobj).as_posix()) \
                if ds.pathobj in p.parents else None
            msg = None
            if rel is None:
                msg = 'path is not a directory within the dataset'
            elif any(rel == o or rel in o.parents or o in rel.parents
                     for o in relpaths):
                msg = 'path overlaps with another path to split'
            else:
                modes = {
                    line.split(' ', 1)[0] for line in repo.call_git_items_(
                        ['ls-files', '-s', '--', str(rel)], read_only=True)}
                if not modes or not p.is_dir():
                    msg = 'path is not a directory with tracked content'
                elif '160000' in modes:
                    msg = 'splitting directories with subdatasets ' \
                          'is not supported'
            if msg:
                yield impossible(msg, p)
                return
            relpaths.append(rel)

        for p, rel in zip(abspaths, relpaths):
            _split_one(ds, p, rel)
        # the dataset was clean, so the index holds nothing but the split.
        # Not using `save`: it would re-add the removed files, which now
        # exist again (inside the subdatasets)
        repo.call_git(['add', '.gitmodules'])
        repo.call_git(['commit', '-q', '-m', '[DATALAD] Split {} into subdataset{}'.format(
            ', '.join(map(str, relpaths)), 's' if len(relpaths) > 1 else '')])
        for p in abspaths:
            yield get_status_dict(
                status='ok', path=str(p), type='dataset', **res_kwargs)


def _split_one(ds, path, rel):
    """Replace directory `path` (`rel` relative to `ds`) with a subdataset"""
    parent = ds.repo
    is_annex = isinstance(parent, AnnexRepo)
    lgr.info('Splitting %s out of %s', rel, ds)
    parent.call_git(['rm', '-r', '-q', '--', str(rel)])
    if path.exists():
        raise RuntimeError(
            f'{path} still exists after removing tracked content from it, '
            'likely due to ignored files. Remove them and retry after '
            'resetting the dataset')
    # a bare clone of just the current branch (bare, so filter-branch does
    # not demand a checkout), turned into a regular repository after filtering
    parent.call_git([
        'clone', '-q', '--bare', '--single-branch', '--no-tags', '--origin', 'origin',
        ds.path, str(path / '.git')])
    sub = GitRepo(path)
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING='1')
    cmd = ['filter-branch', '--subdirectory-filter', str(rel)]
    if is_annex:
        # annex symlinks moved up len(rel.parts) directories
        cmd += ['--index-filter', ' '.join(map(shlex.quote, (
            sys.executable, str(_FIXLINKS), str(len(rel.parts)))))]
    sub.call_git(cmd + ['--', 'HEAD'], env=env)
    # nothing but the rewritten branch should remain from the parent
    for ref in sub.call_git_items_(
            ['for-each-ref', '--format=%(refname)',
             'refs/original', 'refs/remotes'], read_only=True):
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
        (sub.dot_git / 'annex' / 'index').unlink()
        sub.call_git(['update-ref', '-d', 'refs/annex/last-index'])
    sub.call_git(['reflog', 'expire', '--expire=now', '--all'])
    sub.call_git(['gc', '-q', '--prune=now'])
    sub.call_git(['reset', '-q', '--hard'])
    if is_annex:
        sub.call_annex([
            'get', '-c', 'annex.hardlink=true', '--from', 'origin',
            '--in', 'origin', '.'])
    subid = None
    if ds.id:
        # an identity of its own (`create` would refuse, seeing the parent's
        # not yet saved content at this location)
        subid = str(uuid.uuid4())
        subds = Dataset(path)
        subds.config.set('datalad.dataset.id', subid, scope='branch')
        subds.save(path='.datalad', message='[DATALAD] new dataset',
                   to_git=True, result_renderer='disabled')
    # register in the parent
    parent.call_git(['update-index', '--add', '--cacheinfo',
                     f'160000,{sub.get_hexsha()},{rel}'])
    for k, v in (('path', rel), ('url', f'./{rel}'), ('datalad-id', subid)):
        if v:
            parent.call_git(['config', '-f', '.gitmodules',
                             f'submodule.{rel}.{k}', str(v)])
