# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Copy files and their metadata (from one dataset to another)"""

__docformat__ = 'restructuredtext'


import itertools
import logging
import os.path as op
from shutil import copyfile

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.interface.results import get_status_dict
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.support.param import Parameter
from datalad.support.exceptions import CommandError
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.gitrepo import GitRepo
from datalad.utils import (
    assure_list,
    get_dataset_root,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    resolve_path,
)

lgr = logging.getLogger('datalad.local.copy')


@build_doc
class Copy(Interface):
    """
    """
    _params_ = dict(
        dataset=Parameter(
            # not really needed on the cmdline, but for PY to resolve relative
            # paths
            args=("-d", "--dataset"),
            doc="""target dataset to save copied files into. This may be a
            superdataset containing the actual destination dataset. In this case,
            any changes will be save up to this dataset.[PY: This dataset is also
            the reference for any relative paths. PY].""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""paths to copy (and possibly a target path to copy to).""",
            nargs='+',
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r",),
            action='store_true',
            doc="""copy directories recursively"""),
        target_dir=Parameter(
            args=('--target-directory', '-t'),
            metavar='DIRECTORY',
            doc="""copy all PATH arguments into DIRECTORY""",
            constraints=EnsureStr() | EnsureNone()),
    )

    @staticmethod
    @datasetmethod(name='copy')
    @eval_results
    def __call__(
            path,
            dataset=None,
            recursive=False,
            # TODO needs message
            target_dir=None):
        # Concept
        #
        # Loosely model after the POSIX cp command
        #
        # 1. Determine the target of the copy operation, and its associated
        #    dataset
        #
        # 2. for each source: determine source dataset, query for metadata, put
        #    into target dataset
        #
        # Instead of sifting and sorting through input args, process them one
        # by one sequentially. Utilize lookup caching to make things faster,
        # instead of making the procedure itself more complicated.

        # turn into list of absolute paths
        paths = [resolve_path(p, dataset) for p in assure_list(path)]

        # determine the destination path
        if target_dir:
            target_dir = target = resolve_path(target_dir, dataset)
        else:
            # it must be the last item in the path list
            if len(paths) < 2:
                raise ValueError("No target directory was given to `copy`.")
            target = paths.pop(-1)
            # target could be a directory, or even an individual file
            if len(paths) > 2:
                # must be a directory
                target_dir = target
            else:
                # single source, target be an explicit destination filename
                target_dir = target if target.is_dir() else target.parent

        res_kwargs = dict(
            action='copy',
            logger=lgr,
        )

        # warn about directory sources when there will be no recursion
        if not recursive:
            np = []
            for src in paths:
                if src.is_dir():
                    yield dict(
                        path=str(src),
                        status='impossible',
                        message='recursion not enabled, omitting directory',
                        **res_kwargs
                    )
                else:
                    np.append(src)
            paths = np
            del np

        target_ds = get_dataset_root(target_dir)
        if not target_ds:
            yield dict(
                path=str(target),
                status='error',
                message='copy destination not within a dataset',
                **res_kwargs
            )
            return

        target_ds = Dataset(target_ds)
        target_repo = target_ds.repo

        # TODO figure out when it is best to verify that a target AnnexRepo
        # has a properly configured 'datalad' special remote setup

        # lookup cache for dir to ds mappings
        dir_cache = {
            target_repo.pathobj: dict(
                repo=target_repo,
                srinfo=_extract_special_remote_info(target_repo)
            ),
        }

        if dataset:
            ds = require_dataset(dataset, check_installed=True,
                                 purpose='copying into')
            if ds.pathobj not in target_ds.pathobj.parents:
                yield dict(
                    path=ds.path,
                    status='error',
                    message=(
                        'reference dataset does not contain '
                        'destination dataset: %s',
                        target_ds),
                    **res_kwargs
                )
                return
            dir_cache[ds.pathobj] = dict(ds=ds)
        else:
            ds = None

        lgr.debug('Attempt to copy files into %s', target_ds)

        # make sure the target dir exists. We can use this to distinguish
        # a file from a dir target later on

        target_is_dir = target == target_dir

        if target_is_dir:
            # do it once upfront
            target.mkdir(parents=True, exist_ok=True)

        # get a space to place to be inject annex keys into
        (target_ds.pathobj / '.git' / 'tmp' / 'datalad-copy').mkdir(
            exist_ok=True, parents=True)

        # TODO at the moment only a single destination repo is considered
        # but eventually it should be possible to populate a nested
        # hierarchy of datasets
        to_save = []
        for src, dest in itertools.chain.from_iterable(
                _yield_src_dest(p, target, p.parent if p.is_dir() else None, recursive)
                for p in paths):
            for res in _copy_file(src, dest, target_repo, cache=dir_cache):
                yield dict(
                    res,
                    **res_kwargs
                )
                if res.get('status', None) == 'ok':
                    to_save.append(res['destination'])

        if not to_save:
            # nothing left to do
            return

        yield from (ds if ds else target_ds).save(
            path=to_save,
            # we provide an explicit file list
            recursive=False,
        )

        # TODO cleanup tmp


def _yield_src_dest(start, target, base, recursive):
    if start.is_dir():
        if recursive:
            for p in start.iterdir():
                yield from _yield_src_dest(p, target, base, recursive)
        else:
            # we hit a directory and are told to not recurse
            return
    else:
        # reflect src hierarchy if target is a directory, otherwise
        yield start, target / (start.relative_to(base) if base else start.name)


def _copy_file(src, dest, dest_repo, cache):
    str_src = str(src)
    str_dest = str(dest)
    if not op.lexists(str_src):
        yield dict(
            path=str_src,
            status='impossible',
            message='no such file or directory',
        )
        return

    # at this point we know that there is something at `src`,
    # and it must be a file
    src_dir = src.parent
    # get the source dataset, if any
    # `src_ds` will be None, if there is none, and can serve as a flag
    # for further processing
    src_ds_rec = cache.get(src_dir, None)
    if src_ds_rec is None:
        src_ds = get_dataset_root(src_dir)
        src_ds_rec = dict(ds=src_ds if src_ds is None else Dataset(src_ds))
        cache[src_dir] = src_ds_rec
    src_ds = src_ds_rec['ds'] if src_ds_rec else None

    # get the repo shortcut
    src_repo = src_ds.repo if src_ds else None

    # whenever there is no annex (remember an AnnexRepo is also a GitRepo)
    if src_repo is None or not isinstance(src_repo, AnnexRepo):
        # so the best thing we can do is to copy the actual file into the
        # worktree of the destination dataset.
        # we will not care about unlocking or anything like that we just
        # replace whatever is at `dest`, save() must handle the rest.
        # we are not following symlinks, they cannot be annex pointers
        lgr.info('Copying file from no or non-annex dataset: %s', src)
        _replace_file(str_src, dest, str_dest, follow_symlinks=False)
        yield dict(
            path=str_src,
            destination=str_dest,
            status='ok',
        )
        # TODO if we later deal with metadata, we might want to consider
        # going further
        return

    # now we know that we are copying from an AnnexRepo dataset
    # look for URLs on record
    rpath = str(src.relative_to(src_ds.pathobj))

    # pull what we know about this file from the source repo
    finfo = src_repo.get_content_annexinfo(
        paths=[rpath],
        # a simple `exists()` will not be enough (pointer files, etc...)
        eval_availability=True,
        # if it truely is a symlink9not just an annex pointer, we would not
        # want to resolve it
        eval_file_type=True,
    ).popitem()[1]
    if 'key' not in finfo or not isinstance(dest_repo, AnnexRepo):
        lgr.info(
            'Copying non-annexed file or copy into non-annex dataset: %s -> %s',
            src, dest_repo)
        # the best thing we can do when the target isn't an annex repo
        # or the source is not an annexed files is to copy the file,
        # but only if we have it
        # (make default True, because a file in Git doesn't have this property)
        if not finfo.get('has_content', True):
            yield dict(
                path=str_src,
                status='impossible',
                message='file has no content available',
            )
            return
        # follow symlinks to pull content from annex
        _replace_file(str_src, dest, str_dest,
                      follow_symlinks=finfo.get('type', 'file') == 'file')
        yield dict(
            path=str_src,
            destination=str_dest,
            status='ok',
        )
        return

    # at this point we are copying an annexed file into an annex repo
    src_key = finfo['key']

    # TODO
    # 3. if there are URLs defined in the source repo, add them through
    #    `annex registerurl`, possibly followup with `setpresentkey`
    #    for the datalad special remote
    # 4. if a key is known to be available from a non-datalad-type special
    #    remote, import this remote config, enable it, and `setpresentkey`
    #    it
    # make an attempt to compute a key in the target repo, this will hopefully
    # become more relevant once "salted backends" are possible
    # https://github.com/datalad/datalad/issues/3357 that could prevent
    # information leakage across datasets
    if finfo.get('has_content', True):
        dest_key = dest_repo.call_git_oneline(['annex', 'calckey', str_src])
    else:
        lgr.warning(
            'File content not available, forced to reuse previous annex key: %s',
            str_src)
        dest_key = src_key

    dest_repo._run_annex_command_json(
        'fromkey',
        # we use force, because in all likelihood there is no content for this key
        # yet
        opts=[dest_key, str_dest, '--force'],
    )
    if 'objloc' in finfo:
        # we have the chance to place the actual content into the target annex
        # put in a tmp location, git-annex will move from there
        tmploc = dest_repo.pathobj / '.git' / 'tmp' / 'datalad-copy' / dest_key
        _replace_file(finfo['objloc'], tmploc, str(tmploc), follow_symlinks=False)

        dest_repo._run_annex_command(
            'reinject',
            annex_options=[str(tmploc), str_dest],
        )

    # are there any URLs defined? Get them by special remote
    # query by key to hopefully avoid additional file system interaction
    whereis = src_repo.whereis(finfo['key'], key=True, output='full')
    urls_by_sr = {
        k: v['urls']
        for k, v in whereis.items()
        if v.get('urls', None)
    }

    if urls_by_sr:
        # some URLs are on record in the for this file
        # obtain information on special remotes
        src_srinfo = src_ds_rec.get('srinfo', None)
        if src_srinfo is None:
            src_srinfo = _extract_special_remote_info(src_repo)
            # put in cache
            src_ds_rec['srinfo'] = src_srinfo
        # TODO generalize to more than one unique dest_repo
        dest_srinfo = _extract_special_remote_info(dest_repo)

        for src_rid, urls in urls_by_sr.items():
            if not (src_rid == '00000000-0000-0000-0000-000000000001' or
                    src_srinfo.get(src_rid, {}).get('externaltype', None) == 'datalad'):
                lgr.warn(
                    'Ignore URL for presently unsupported special remote'
                )
                continue
            if src_rid != '00000000-0000-0000-0000-000000000001' and \
                    src_srinfo[src_rid] not in dest_srinfo.values():
                # this is a special remote that the destination repo doesnt know
                sri = src_srinfo[src_rid]
                lgr.debug('Init additionally required special remote: %s', sri)
                dest_repo.init_remote(
                    # TODO what about a naming conflict across all dataset sources?
                    sri['name'],
                    ['{}={}'.format(k, v) for k, v in sri.items() if k != 'name'],
                )
                # must update special remote info for later matching
                dest_srinfo = _extract_special_remote_info(dest_repo)
            for url in urls:
                lgr.debug('Register URL for key %s: %s', dest_key, url)
                dest_repo._run_annex_command(
                    'registerurl', annex_options=[dest_key, url])
            dest_rid = src_rid \
                if src_rid == '00000000-0000-0000-0000-000000000001' \
                else [
                    k for k, v in dest_srinfo.items()
                    if v['name'] == src_srinfo[src_rid]['name']
                ].pop()
            lgr.debug('Mark key %s as present for special remote: %s',
                      dest_key, dest_rid)
            dest_repo._run_annex_command(
                'setpresentkey', annex_options=[dest_key, dest_rid, '1'])

    # TODO prevent copying .git or .datalad of from other datasets
    yield dict(
        path=str_src,
        destination=str_dest,
        message=dest,
        status='ok',
    )


def _replace_file(str_src, dest, str_dest, follow_symlinks):
    if op.lexists(str_dest):
        dest.unlink()
    else:
        dest.parent.mkdir(exist_ok=True, parents=True)
    copyfile(str_src, str_dest, follow_symlinks=False)


def _extract_special_remote_info(repo):
    return {
        k:
        {pk: pv for pk, pv in v.items() if pk != 'timestamp'}
        for k, v in repo.get_special_remotes().items()
    }
