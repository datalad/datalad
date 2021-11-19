# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Copy files (from one dataset to another)"""

__docformat__ = 'restructuredtext'


import logging
import os.path as op
from shutil import copyfile
import sys

from datalad.interface.base import Interface
from datalad.interface.utils import eval_results
from datalad.interface.base import build_doc
from datalad.support.constraints import (
    EnsureStr,
    EnsureNone,
)
from datalad.interface.common_opts import save_message_opt
from datalad.support.param import Parameter
from datalad.distribution.dataset import (
    Dataset,
    require_dataset,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import CapturedException
from datalad.utils import (
    ensure_list,
    get_dataset_root,
    Path,
)

from datalad.distribution.dataset import (
    EnsureDataset,
    datasetmethod,
    resolve_path,
)

lgr = logging.getLogger('datalad.local.copy_file')


@build_doc
class CopyFile(Interface):
    """Copy files and their availability metadata from one dataset to another.

    The difference to a system copy command is that here additional content
    availability information, such as registered URLs, is also copied to the
    target dataset. Moreover, potentially required git-annex special remote
    configurations are detected in a source dataset and are applied to a target
    dataset in an analogous fashion. It is possible to copy a file for which no
    content is available locally, by just copying the required metadata on
    content identity and availability.

    .. note::
      At the moment, only URLs for the special remotes 'web' (git-annex built-in)
      and 'datalad' are recognized and transferred.

    || REFLOW >>
    The interface is modeled after the POSIX 'cp' command, but with one
    additional way to specify what to copy where: [CMD: --specs-from CMD][PY:
    `specs_from` PY] allows the caller to flexibly input source-destination
    path pairs.
    << REFLOW ||

    || REFLOW >>
    This command can copy files out of and into a hierarchy of nested datasets.
    Unlike with other DataLad command, the [CMD: --recursive CMD][PY: `recursive`
    PY] switch does not enable recursion into subdatasets, but is analogous
    to the POSIX 'cp' command switch and enables subdirectory recursion, regardless
    of dataset boundaries. It is not necessary to enable recursion in order to
    save changes made to nested target subdatasets.
    << REFLOW ||
    """
    _params_ = dict(
        dataset=Parameter(
            # not really needed on the cmdline, but for PY to resolve relative
            # paths
            args=("-d", "--dataset"),
            doc="""root dataset to save after copy operations are completed.
            All destination paths must be within this dataset, or its
            subdatasets. If no dataset is given, dataset modifications will be
            left unsaved.""",
            constraints=EnsureDataset() | EnsureNone()),
        path=Parameter(
            args=("path",),
            metavar='PATH',
            doc="""paths to copy (and possibly a target path to copy to).""",
            nargs='*',
            constraints=EnsureStr() | EnsureNone()),
        recursive=Parameter(
            args=("--recursive", "-r",),
            action='store_true',
            doc="""copy directories recursively"""),
        target_dir=Parameter(
            args=('--target-dir', '-t'),
            metavar='DIRECTORY',
            doc="""copy all source files into this DIRECTORY. This value is
            overridden by any explicit destination path provided via [CMD:
            --specs-from CMD][PY: 'specs_from' PY]. When not given, this
            defaults to the path of the dataset specified via [CMD: --dataset
            CMD][PY: 'dataset' PY].""",
            constraints=EnsureStr() | EnsureNone()),
        specs_from=Parameter(
            args=('--specs-from',),
            metavar='SOURCE',
            doc="""read list of source (and destination) path names from a given
            file, or stdin (with '-'). Each line defines either a source
            path, or a source/destination path pair (separated by a null byte
            character).[PY:  Alternatively, a list of 2-tuples with
            source/destination pairs can be given. PY]"""),
        message=save_message_opt,
    )

    _examples_ = [
        dict(
            text="Copy a file into a dataset 'myds' using a path and a target "
                 "directory specification, and save its addition to 'myds'",
            code_py="""\
            copy_file('path/to/myfile', dataset='path/to/myds')""",
            code_cmd="""\
            datalad copy-file path/to/myfile -d path/to/myds"""),
        dict(
            text="Copy a file to a dataset 'myds' and save it under a new name "
                 "by providing two paths",
            code_py="""\
            copy_file(path=['path/to/myfile', 'path/to/myds/newname'],
                      dataset='path/to/myds')""",
            code_cmd="""\
            datalad copy-file path/to/myfile path/to/myds/new -d path/to/myds"""),
        dict(
            text="Copy a file into a dataset without saving it",
            code_py="copy_file('path/to/myfile', target_dir='path/to/myds/')",
            code_cmd="datalad copy-file path/to/myfile -t path/to/myds"),
        dict(
            text="Copy a directory and its subdirectories into a dataset 'myds'"
                 " and save the addition in 'myds'",
            code_py="""\
            copy_file('path/to/dir/', recursive=True, dataset='path/to/myds')""",
            code_cmd="""\
            datalad copy-file path/to/dir -r -d path/to/myds"""),
        dict(
            text="Copy files using a path and optionally target specification "
                 "from a file",
            code_py="""\
            copy_file(dataset='path/to/myds', specs_from='path/to/specfile')""",
            code_cmd="""\
            datalad copy-file -d path/to/myds --specs-from specfile"""
        ),
        dict(
            text="Read a specification from stdin and pipe the output of a find"
                 " command into the copy-file command",
            code_cmd="""\
            find <expr> | datalad copy-file -d path/to/myds --specs-from -"""
        )
    ]

    @staticmethod
    @datasetmethod(name='copy_file')
    @eval_results
    def __call__(
            path=None,
            dataset=None,
            recursive=False,
            target_dir=None,
            specs_from=None,
            message=None):
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

        if path and specs_from:
            raise ValueError(
                "Path argument(s) AND a specs-from specified, "
                "this is not supported.")

        ds = None
        if dataset:
            ds = require_dataset(dataset, check_installed=True,
                                 purpose='copy into')

        if target_dir:
            target_dir = resolve_path(target_dir, dataset)

        if path:
            # turn into list of absolute paths
            paths = [resolve_path(p, dataset) for p in ensure_list(path)]

            # we already checked that there are no specs_from
            if not target_dir:
                if len(paths) == 1:
                    if not ds:
                        raise ValueError("No target directory was given.")
                    # we can keep target_dir unset and need not manipulate
                    # paths, this is all done in a generic fashion below
                elif len(paths) == 2:
                    # single source+dest combo
                    if paths[-1].is_dir():
                        # check if we need to set target_dir, in case dest
                        # is a dir
                        target_dir = paths.pop(-1)
                    else:
                        specs_from = [paths]
                else:
                    target_dir = paths.pop(-1)

            if not specs_from:
                # in all other cases we have a plain source list
                specs_from = paths

        if not specs_from:
            raise ValueError("Neither `paths` nor `specs_from` given.")

        if target_dir:
            if ".git" in target_dir.parts:
                raise ValueError(
                    "Target directory should not contain a .git directory: {}"
                    .format(target_dir))
        elif ds:
            # no specific target set, but we have to write into a dataset,
            # and one was given. It seems to make sense to use this dataset
            # as a target. it is already to reference for any path resolution.
            # Any explicitly given destination, will take precedence over
            # a general target_dir setting nevertheless.
            target_dir = ds.pathobj

        res_kwargs = dict(
            action='copy_file',
            logger=lgr,
        )

        # lookup cache for dir to repo mappings, and as a DB for cleaning
        # things up
        repo_cache = {}
        # which paths to pass on to save
        to_save = []
        try:
            for src_path, dest_path in _yield_specs(specs_from):
                src_path = Path(src_path)
                dest_path = None \
                    if dest_path is None \
                    else resolve_path(dest_path, dataset)
                lgr.debug('Processing copy specification: %s -> %s',
                          src_path, dest_path)

                # Some checks, first impossibility "wins"
                msg_impossible = None
                if not recursive and src_path.is_dir():
                    msg_impossible = 'recursion not enabled, omitting directory'
                elif (dest_path and dest_path.name == '.git') \
                        or src_path.name == '.git':
                    msg_impossible = \
                        "refuse to place '.git' into destination dataset"
                elif not (dest_path or target_dir):
                    msg_impossible = 'need destination path or target directory'

                if msg_impossible:
                    yield dict(
                        path=str(src_path),
                        status='impossible',
                        message=msg_impossible,
                        **res_kwargs
                    )
                    continue

                for src_file, dest_file in _yield_src_dest_filepaths(
                        src_path, dest_path, target_dir=target_dir):
                    if ds and ds.pathobj not in dest_file.parents:
                        # take time to compose proper error
                        dpath = str(target_dir if target_dir else dest_path)
                        yield dict(
                            path=dpath,
                            status='error',
                            message=(
                                'reference dataset does not contain '
                                'destination path: %s',
                                dpath),
                            **res_kwargs
                        )
                        # only recursion could yield further results, which would
                        # all have the same issue, so call it over right here
                        break
                    for res in _copy_file(src_file, dest_file, cache=repo_cache):
                        yield dict(
                            res,
                            **res_kwargs
                        )
                        if res.get('status', None) == 'ok':
                            to_save.append(res['destination'])
        finally:
            # cleanup time
            # TODO this could also be the place to stop lingering batch processes
            _cleanup_cache(repo_cache)

        if not (ds and to_save):
            # nothing left to do
            return

        yield from ds.save(
            path=to_save,
            # we provide an explicit file list
            recursive=False,
            message=message,
        )


def _cleanup_cache(repo_cache):
    done = set()
    for _, repo_rec in repo_cache.items():
        repo = repo_rec['repo']
        if not repo or repo.pathobj in done:
            continue
        tmp = repo_rec.get('tmp', None)
        if tmp:
            try:
                tmp.rmdir()
            except OSError as e:
                ce = CapturedException(e)
                lgr.warning(
                    'Failed to clean up temporary directory: %s', ce)
        done.add(repo.pathobj)


def _yield_specs(specs):
    if specs == '-':
        specs_it = sys.stdin
    elif isinstance(specs, (list, tuple)):
        specs_it = specs
    else:
        specs_it = Path(specs).open('r')

    for spec in specs_it:
        if isinstance(spec, (list, tuple)):
            src = spec[0]
            dest = spec[1]
        elif isinstance(spec, Path):
            src = spec
            dest = None
        else:
            # deal with trailing newlines and such
            spec = spec.rstrip()
            spec = spec.split('\0')
            src = spec[0]
            dest = None if len(spec) == 1 else spec[1]
        yield src, dest


def _yield_src_dest_filepaths(src, dest, src_base=None, target_dir=None):
    """Yield src/dest path pairs

    Parameters
    ----------

    src : Path
      Source file or directory. If a directory, yields files from this
      directory recursively.
    dest : Path or None
      Destination path. Either a complete file path, or a base directory
      (see `src_base`).
    src_base : Path
      If given, the destination path will be `dest`/`src.relative_to(src_base)`

    Yields
    ------
    src, dest
      Path instances
    """
    if src.is_dir():
        # we only get here, when recursion is desired
        if src.name == '.git':
            # we never want to copy the git repo internals into another repo
            # this would break the target git in unforseeable ways
            return
        # special case: not yet a file to copy
        if src_base is None:
            # TODO maybe an unconditional .parent isn't a good idea,
            # if someone wants to copy a whole drive...
            src_base = src.parent
        for p in src.iterdir():
            yield from _yield_src_dest_filepaths(p, dest, src_base, target_dir)
        return

    if target_dir is None and not dest:
        raise ValueError("Neither target_dir nor dest specified")

    if not dest:
        # no explicit destination given, build one from src and target_dir
        # reflect src hierarchy if dest is a directory, otherwise
        if src.is_absolute() and src_base:
            dest = target_dir / src.relative_to(src_base)
        else:
            dest = target_dir / src.name

    yield src, dest


def _get_repo_record(fpath, cache):
    fdir = fpath.parent
    # get the repository, if there is any.
    # `src_repo` will be None, if there is none, and can serve as a flag
    # for further processing
    repo_rec = cache.get(fdir, None)
    if repo_rec is None:
        repo_root = get_dataset_root(fdir)
        repo_rec = dict(
            repo=None if repo_root is None else Dataset(repo_root).repo,
            # this is different from repo.pathobj which resolves symlinks
            repo_root=Path(repo_root) if repo_root else None)
        cache[fdir] = repo_rec
    return repo_rec


def _copy_file(src, dest, cache):
    lgr.debug("Attempt to copy: %s -> %s", src, dest)
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
    # get the source repository, if there is any.
    # `src_repo` will be None, if there is none, and can serve as a flag
    # for further processing
    src_repo_rec = _get_repo_record(src, cache)
    src_repo = src_repo_rec['repo']
    # same for the destination repo
    dest_repo_rec = _get_repo_record(dest, cache)
    dest_repo = dest_repo_rec['repo']
    if not dest_repo:
        yield dict(
            path=str_dest,
            status='error',
            message='copy destination not within a dataset',
        )
        return

    # whenever there is no annex (remember an AnnexRepo is also a GitRepo)
    if src_repo is None or not isinstance(src_repo, AnnexRepo):
        # so the best thing we can do is to copy the actual file into the
        # worktree of the destination dataset.
        # we will not care about unlocking or anything like that we just
        # replace whatever is at `dest`, save() must handle the rest.
        # we are not following symlinks, they cannot be annex pointers
        lgr.info(
            'Copying file from a location which is not an annex dataset: %s',
            src)
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
    rpath = str(src.relative_to(src_repo_rec['repo_root']))

    # pull what we know about this file from the source repo
    finfo = src_repo.get_content_annexinfo(
        paths=[rpath],
        # a simple `exists()` will not be enough (pointer files, etc...)
        eval_availability=True,
        # if it truly is a symlink, not just an annex pointer, we would not
        # want to resolve it
        eval_file_type=True,
    )
    finfo = finfo.popitem()[1] if finfo else {}
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
    if not dest_repo._check_version_kludges("fromkey-supports-unlocked") \
       and dest_repo.is_managed_branch():
        res = _place_filekey_managed(
            finfo, str_src, dest, str_dest, dest_repo_rec)
    else:
        res = _place_filekey(
            finfo, str_src, dest, str_dest, dest_repo_rec)
    if isinstance(res, dict):
        yield res
        return
    dest_key = res

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
        src_srinfo = src_repo_rec.get('srinfo', None)
        if src_srinfo is None:
            src_srinfo = _extract_special_remote_info(src_repo)
            # put in cache
            src_repo_rec['srinfo'] = src_srinfo
        # TODO generalize to more than one unique dest_repo
        dest_srinfo = _extract_special_remote_info(dest_repo)

        for src_rid, urls in urls_by_sr.items():
            if not (src_rid == '00000000-0000-0000-0000-000000000001' or
                    src_srinfo.get(src_rid, {}).get('externaltype', None) == 'datalad'):
                # TODO generalize to any special remote
                lgr.warning(
                    'Ignore URL for presently unsupported special remote'
                )
                continue
            if src_rid != '00000000-0000-0000-0000-000000000001' and \
                    src_srinfo[src_rid] not in dest_srinfo.values():
                # this is a special remote that the destination repo doesn't know
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
                # TODO OPT: add .register_url(key, batched=False) to AnnexRepo
                #  to speed up this step by batching.
                dest_repo.call_annex(['registerurl', dest_key, url])
            dest_rid = src_rid \
                if src_rid == '00000000-0000-0000-0000-000000000001' \
                else [
                    k for k, v in dest_srinfo.items()
                    if v['name'] == src_srinfo[src_rid]['name']
                ].pop()
            lgr.debug('Mark key %s as present for special remote: %s',
                      dest_key, dest_rid)
            dest_repo.call_annex(['setpresentkey', dest_key, dest_rid, '1'])

    # TODO prevent copying .datalad of from other datasets?
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
    copyfile(str_src, str_dest, follow_symlinks=follow_symlinks)


def _extract_special_remote_info(repo):
    return {
        k:
        {pk: pv for pk, pv in v.items() if pk != 'timestamp'}
        for k, v in repo.get_special_remotes().items()
    }


def _place_filekey(finfo, str_src, dest, str_dest, dest_repo_rec):
    dest_repo = dest_repo_rec['repo']
    src_key = finfo['key']
    # make an attempt to compute a key in the target repo, this will hopefully
    # become more relevant once "salted backends" are possible
    # https://github.com/datalad/datalad/issues/3357 that could prevent
    # information leakage across datasets
    if finfo.get('has_content', True):
        dest_key = dest_repo.call_annex_oneline(['calckey', str_src])
    else:
        lgr.debug(
            'File content not available, forced to reuse previous annex key: %s',
            str_src)
        dest_key = src_key

    if op.lexists(str_dest):
        # if the target already exists, we remove it first, because we want to
        # modify this path (potentially pointing to a new key), rather than
        # failing next on 'fromkey', due to a key mismatch.
        # this is more compatible with the nature of 'cp'
        dest.unlink()
    res = dest_repo._call_annex_records(
        # we use force, because in all likelihood there is no content for this key
        # yet
        ['fromkey', dest_key, str_dest, '--force'],
    )
    if any(not r['success'] for r in res):
        return dict(
            path=str_dest,
            status='error',
            message='; '.join(
                m for r in res for m in r.get('error-messages', [])),
        )
    if 'objloc' in finfo:
        # we have the chance to place the actual content into the target annex
        # put in a tmp location, git-annex will move from there
        tmploc = dest_repo_rec.get('tmp', None)
        if not tmploc:
            tmploc = dest_repo.pathobj / '.git' / 'tmp' / 'datalad-copy'
            tmploc.mkdir(exist_ok=True, parents=True)
            # put in cache for later clean/lookup
            dest_repo_rec['tmp'] = tmploc

        tmploc = tmploc / dest_key
        _replace_file(finfo['objloc'], tmploc, str(tmploc), follow_symlinks=False)

        dest_repo.call_annex(['reinject', str(tmploc), str_dest])

    return dest_key


def _place_filekey_managed(finfo, str_src, dest, str_dest, dest_repo_rec):
    # TODO put in effect, when salted backends are a thing, until then
    # avoid double-computing the file hash
    #dest_repo = dest_repo_rec['repo']
    #if finfo.get('has_content', True):
    #    dest_key = dest_repo.call_git_oneline(['annex', 'calckey', str_src])
    dest_key = finfo['key']
    if not finfo.get('has_content', True):
        return dict(
            path=str_dest,
            status='error',
            message=(
                'Cannot create file in managed branch without file content.'
                'Missing for: %s',
                str_src)
        )
    _replace_file(finfo['objloc'], dest, str_dest, follow_symlinks=True)
    return dest_key
