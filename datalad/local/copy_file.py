# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
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
from functools import lru_cache

lgr = logging.getLogger('datalad.local.copy_file')


class _CachedRepo(object):
    """Custom wrapper around a Repo instance

    It provides a few customized methods that also cache their return
    values. For all other method access the underlying repo instance
    is used.

    A repository is assumed to be static. Cache invalidation must
    be done manually, if that assumption does no longer hold.
    """

    def __init__(self, path):
        self._unresolved_path = path
        self._repo = Dataset(path).repo
        self._tmpdir = None
        self._ismanagedbranch = None

    def __getattr__(self, name):
        """Fall back on the actual repo instance, if we have nothing"""
        return getattr(self._repo, name)

    # more than 20 special remotes may be rare
    @lru_cache(maxsize=20)
    def get_special_remotes_wo_timestamp(self):
        return {
            k:
            {pk: pv for pk, pv in v.items() if pk != 'timestamp'}
            for k, v in self._repo.get_special_remotes().items()
        }

    # there can be many files, and the records per file are smallish
    @lru_cache(maxsize=10000)
    def get_file_annexinfo(self, fpath):
        rpath = str(fpath.relative_to(self._unresolved_path))
        finfo = self._repo.get_content_annexinfo(
            paths=[rpath],
            # a simple `exists()` will not be enough (pointer files, etc...)
            eval_availability=True,
        )
        finfo = finfo.popitem()[1] if finfo else {}
        return finfo

    # n-keys and n-files should have the same order of magnitude
    @lru_cache(maxsize=10000)
    def get_whereis_key_by_specialremote(self, key):
        """Returns whereis () for a single key

        Returns
        -------
        dict
          Keys are special remote IDs, values are dicts with all relevant
          whereis properties, currently ('urls' (list), 'here' (bool)).
        """
        whereis = self._repo.whereis(key, key=True, output='full')
        whereis_by_sr = {
            k: {prop: v[prop] for prop in ('urls', 'here')
                if v.get(prop) not in (None, [])}
            for k, v in whereis.items()
        }
        return whereis_by_sr

    def is_managed_branch(self):
        if self._ismanagedbranch is None:
            self._ismanagedbranch = self._repo.is_managed_branch()
        return self._ismanagedbranch

    def get_tmpdir(self):
        if not self._tmpdir:
            tmploc = self._repo.pathobj / '.git' / 'tmp' / 'datalad-copy'
            tmploc.mkdir(exist_ok=True, parents=True)
            # put in cache for later clean/lookup
            self._tmpdir = tmploc
        return self._tmpdir

    def cleanup_cachedrepo(self):
        # TODO this could also be the place to stop lingering batch processes
        if not self._tmpdir:
            return

        try:
            self._tmpdir.rmdir()
        except OSError as e:
            ce = CapturedException(e)
            lgr.warning('Failed to clean up temporary directory: %s', ce)

    def get_repotype(self):
        return type(self._repo)


class _StaticRepoCache(dict):
    """Cache to give a repository instance for any given file path

    Instances of _CachedRepo are created and returned based on the
    determined dataset root path of a given file path.
    """
    def __hash__(self):
        # every cache instance is, and should be considered unique
        # this is only needed for `lru_cache` to be able to handle
        # `self`
        return id(self)

    # a thousand dirs? should most, certainly not all datasets
    @lru_cache(maxsize=1000)
    def _dir2reporoot(self, fdir):
        return get_dataset_root(fdir)

    def __getitem__(self, fpath):
        """Return a repository instance for a given file path

        Parameters
        ----------
        fpath : Path

        Returns
        -------
        _CachedRepo or None
        """
        repo_root = self._dir2reporoot(fpath.parent)

        if repo_root is None:
            return

        repo = self.get(repo_root)

        if repo is None:
            repo = _CachedRepo(repo_root)
            self[repo_root] = repo

        return repo

    def clear(self):
        for repo in self.values():
            repo.cleanup_cachedrepo()
        super().clear()


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
            *,
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
        repo_cache = _StaticRepoCache()
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
            repo_cache.clear()

        if not (ds and to_save):
            # nothing left to do
            return

        yield from ds.save(
            path=to_save,
            # we provide an explicit file list
            recursive=False,
            message=message,
            return_type='generator',
            result_renderer='disabled'
        )


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


def _copy_file(src, dest, cache):
    """Transfer a single file from a source to a target dataset

    Parameters
    ----------
    src : Path or str
      Source file path
    dest : Path or str
      Destination file path
    cache : StaticRepoCache

    Yields
    ------
    dict
      Result record.
    """
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
    src_repo = cache[src]
    # same for the destination repo
    dest_repo = cache[dest]
    if not dest_repo:
        yield dict(
            path=str_dest,
            status='error',
            message='copy destination not within a dataset',
        )
        return

    # whenever there is no annex (remember an AnnexRepo is also a GitRepo)
    if src_repo is None or not issubclass(src_repo.get_repotype(), AnnexRepo):
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

    # pull what we know about this file from the source repo
    finfo = src_repo.get_file_annexinfo(src)
    if 'key' not in finfo or not issubclass(dest_repo.get_repotype(), AnnexRepo):
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

    #
    # at this point we are copying an annexed file into an annex repo
    if not dest_repo._check_version_kludges("fromkey-supports-unlocked") \
       and dest_repo.is_managed_branch():
        res = _place_filekey_managed(
            finfo, str_src, dest, str_dest, dest_repo)
    else:
        res = _place_filekey(
            finfo, str_src, dest, str_dest, dest_repo)
    if isinstance(res, dict):
        yield res
        return
    dest_key = res

    # are there any URLs defined? Get them by special remote
    # query by key to hopefully avoid additional file system interaction
    whereis_by_sr = src_repo.get_whereis_key_by_specialremote(finfo['key'])
    if not whereis_by_sr:
        yield dict(
            path=str_src,
            destination=str_dest,
            message='no known location of file content',
            status='impossible',
        )
        return

    avail_remote = []
    urls_by_sr = {k: v['urls'] for k, v in whereis_by_sr.items() if v.get('urls')}
    if urls_by_sr:
        # some URLs are on record in the for this file
        avail_remote.extend(_register_urls(
            dest_repo,
            dest_key,
            urls_by_sr,
            src_repo.get_special_remotes_wo_timestamp(),
        ))

    if not avail_remote \
            and not dest_repo.get_file_annexinfo(dest).get('has_content'):
        # not having set any remotes is not a problem, if the file content got
        # here via other means
        yield dict(
            path=str_src,
            destination=str_dest,
            message='no usable/supported remote for file content',
            status='impossible',
        )
        return

    # TODO prevent copying .datalad of from other datasets?
    yield dict(
        path=str_src,
        destination=str_dest,
        message=dest,
        status='ok',
    )


def _register_urls(repo, key, urls_by_sr, src_srinfo):
    """Register URLs for a key in a repo based on special remote info

    Parameters
    ----------
    repo : AnnexRepo
    key : str
    urls_by_sr : dict
    src_srinfo : dict

    Returns
    -------
    list
      IDs of (newly initialized) special remotes in the target dataset that
      can provide the key.
    """
    avail_sr = []
    for src_rid, urls in urls_by_sr.items():
        if not (src_rid == '00000000-0000-0000-0000-000000000001' or
                src_srinfo.get(src_rid, {}).get('externaltype', None) == 'datalad'):
            # TODO generalize to any special remote
            lgr.warning(
                'Ignore URL for presently unsupported special remote'
            )
            continue
        if src_rid != '00000000-0000-0000-0000-000000000001' and \
                src_srinfo[src_rid] \
                not in repo.get_special_remotes_wo_timestamp().values():
            # this is a special remote that the destination repo doesn't know
            sri = src_srinfo[src_rid]
            lgr.debug('Init additionally required special remote: %s', sri)
            repo.init_remote(
                # TODO what about a naming conflict across all dataset sources?
                sri['name'],
                ['{}={}'.format(k, v) for k, v in sri.items() if k != 'name'],
            )
            # must update special remote info for later matching
            repo.get_special_remotes_wo_timestamp.cache_clear()
        for url in urls:
            lgr.debug('Register URL for key %s: %s', key, url)
            # TODO OPT: add .register_url(key, batched=False) to AnnexRepo
            #  to speed up this step by batching.
            repo.call_annex(['registerurl', key, url])
        dest_rid = src_rid \
            if src_rid == '00000000-0000-0000-0000-000000000001' \
            else [
                k for k, v in repo.get_special_remotes_wo_timestamp().items()
                if v['name'] == src_srinfo[src_rid]['name']
            ].pop()
        lgr.debug('Mark key %s as present for special remote: %s',
                  key, dest_rid)
        repo.call_annex(['setpresentkey', key, dest_rid, '1'])
        # record ID of special remote in dest dataset
        avail_sr.append(dest_rid)
    return avail_sr


def _replace_file(str_src, dest, str_dest, follow_symlinks):
    if op.lexists(str_dest):
        dest.unlink()
    else:
        dest.parent.mkdir(exist_ok=True, parents=True)
    copyfile(str_src, str_dest, follow_symlinks=follow_symlinks)


def _place_filekey(finfo, str_src, dest, str_dest, dest_repo):
    """Put a key into a target repository

    Parameters
    ----------
    finfo : dict
      Properties of the source file, as reported by get_content_annexinfo()
    str_src : str
      Source path as a plain str
    dest : Path
      Destination path
    str_dest : str
      Same as `dest`, but as a plain str
    dest_repo_rec : dict
      Repository lookup cache item. This function will add and query
      a 'tmp' key to this record for a temp dir for copy operations
      to be used for the destination repository.

    Returns
    -------
    str or dict
      If a str, the key was established and the key name is returned.
      If a dict, an error occurred and an error result record is returned.
    """
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
        tmploc = dest_repo.get_tmpdir() / dest_key
        _replace_file(finfo['objloc'], tmploc, str(tmploc), follow_symlinks=False)

        dest_repo.call_annex(['reinject', str(tmploc), str_dest])

    return dest_key


def _place_filekey_managed(finfo, str_src, dest, str_dest, dest_repo):
    # TODO put in effect, when salted backends are a thing, until then
    # avoid double-computing the file hash
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
