# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding content of an archive under annex control

"""

__docformat__ = 'restructuredtext'


import os
import re
import tempfile
import warnings
from os.path import (
    basename,
    curdir,
    exists,
)
from os.path import join as opj
from os.path import lexists
from os.path import sep as opsep

from datalad.consts import ARCHIVES_SPECIAL_REMOTE
from datalad.customremotes.base import ensure_datalad_remote
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
from datalad.interface.common_opts import allow_dirty
from datalad.interface.results import get_status_dict
from datalad.log import (
    log_progress,
    logging,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import AnnexBatchCommandError
from datalad.support.constraints import (
    EnsureNone,
    EnsureStr,
)
from datalad.support.param import Parameter
from datalad.support.stats import ActivityStats
from datalad.support.strings import apply_replacement_rules
from datalad.utils import (
    Path,
    ensure_list,
    ensure_tuple_or_list,
    file_basename,
    getpwd,
    md5sum,
    rmtree,
    split_cmdline,
)

lgr = logging.getLogger('datalad.local.add_archive_content')


# Shortcut note
_KEY_OPT = "[PY: `key=True` PY][CMD: --key CMD]"
_KEY_OPT_NOTE = "Note that it will be of no effect if %s is given" % _KEY_OPT

# TODO: may be we could enable separate logging or add a flag to enable
# all but by default to print only the one associated with this given action


def _add_archive_content(
        archive,
        *,
        ds,
        annex,
        annexarchive,
        key,
        origin,
        archive_path,
        extract_rpath,
        total_stats,
        res_kwargs,
        add_archive_leading_dir=False,
        strip_leading_dirs=False,
        leading_dirs_depth=None,
        leading_dirs_consider=None,
        delete=False,
        exclude=None,
        rename=None,
        existing='fail',
        annex_options=None,
        copy=False,
        drop_after=False,
        delete_after=False):
    """Add the content of a single archive to the dataset

    Helper of `AddArchiveContent.__call__`, which does all the work for a
    single archive, so that a single invocation of the command could handle
    any number of them.  Nothing is committed here -- that is left to the
    caller, so that content of multiple archives could end up in a single
    commit.

    Parameters
    ----------
    archive : str or Path
      Archive (or a key, if `origin` is 'key') as it was specified by the
      caller.  Used to derive names for the extracted content, and for
      messages.
    ds : Dataset
      Dataset to add the content to.
    annex : AnnexRepo
      Repository of `ds`.
    annexarchive : ArchiveAnnexCustomRemote
      Used to access the cache of extracted archives, and to compose the
      URLs for the extracted files.
    key : str
      Annex key of the archive.
    origin : {'archive', 'key'}
      Whether the archive was specified as a file or as an annex key.
    archive_path : Path
      Absolute path of the archive.
    extract_rpath : Path or None
      Directory (relative to the root of `ds`) to extract the archive
      content into.  `None` stands for the root of the dataset.
    total_stats : ActivityStats
      Statistics of this archive are added to this instance.
    res_kwargs : dict
      Common arguments for the result records.

    All other parameters are as described for the `add_archive_content`
    command.

    Yields
    ------
    dict
      Result records.
    """
    archive_basename = file_basename(archive)

    try:
        key_rpath = annex.get_contentlocation(key)
    except:
        # the only probable reason for this to fail is that there is no
        # content present
        raise RuntimeError(
            "Content of %s seems to be N/A.  Fetch it first" % key
        )

    # now we simply need to go through every file in that archive and
    lgr.info(
        "Adding content of the archive %s into annex %s", archive, annex
    )
    earchive = annexarchive.cache[key_rpath]

    delete_after_rpath = None

    prefix_dir = basename(tempfile.mkdtemp(prefix=".datalad",
                                           dir=annex.path)) \
        if delete_after \
        else None

    # dedicated stats for this archive, added to the overall ones at the end
    stats = ActivityStats()

    # start a progress bar for extraction
    pbar_id = f'add-archive-{archive_path}'
    try:
        # keep track of extracted files for progress bar logging
        file_counter = 0
        # iterative over all files in the archive
        extracted_files = list(earchive.get_extracted_files())
        log_progress(
            lgr.info, pbar_id, 'Extracting archive',
            label="Extracting archive",
            unit=' Files',
            total = len(extracted_files),
            noninteractive_level = logging.INFO)
        for extracted_file in extracted_files:
            file_counter += 1
            files_left = len(extracted_files) - file_counter
            log_progress(
                lgr.info, pbar_id,
                "Files to extract %i ", files_left,
                update=1,
                increment=True,
                noninteractive_level=logging.DEBUG)
            stats.files += 1
            extracted_path = Path(earchive.path) / Path(extracted_file)

            if extracted_path.is_symlink():
                link_path = str(extracted_path.resolve())
                if not exists(link_path):
                    # TODO: config  addarchive.symlink-broken='skip'
                    lgr.warning(
                        "Path %s points to non-existing file %s" %
                        (extracted_path, link_path)
                    )
                    stats.skipped += 1
                    continue
                    # TODO: check if points outside of archive - warn & skip

            url = annexarchive.get_file_url(
                archive_key=key,
                file=extracted_file,
                size=os.stat(extracted_path).st_size)

            # preliminary target name which might get modified by renames
            target_file_orig = target_file = Path(extracted_file)

            # stream archives would not have had the original filename
            # information in them, so would be extracted under a name
            # derived from their annex key.
            # Provide ad-hoc handling for such cases
            if (len(extracted_files) == 1 and
                Path(archive).suffix in ('.xz', '.gz', '.lzma') and
                    Path(key_rpath).name.startswith(Path(
                        extracted_file).name)):
                # take archive's name without extension for filename & place
                # where it was originally extracted
                target_file = \
                    Path(extracted_file).parent / Path(archive).stem

            if strip_leading_dirs:
                leading_dir = earchive.get_leading_directory(
                    depth=leading_dirs_depth, exclude=exclude,
                    consider=leading_dirs_consider)
                leading_dir_len = \
                    len(leading_dir) + len(opsep) if leading_dir else 0
                target_file = str(target_file)[leading_dir_len:]

            if add_archive_leading_dir:
                # place extracted content under a directory corresponding to
                # the archive name with suffix stripped.
                target_file = Path(archive_basename) / target_file

            if rename:
                target_file = apply_replacement_rules(rename,
                                                      str(target_file))

            # continue to next iteration if extracted_file in excluded
            if exclude:
                try:  # since we need to skip outside loop from inside loop
                    for regexp in exclude:
                        if re.search(regexp, extracted_file):
                            lgr.debug(
                                "Skipping %s since contains %s pattern",
                                extracted_file, regexp)
                            stats.skipped += 1
                            raise StopIteration
                except StopIteration:
                    continue

            if delete_after:
                # place target file in a temporary directory
                target_file = Path(prefix_dir) / Path(target_file)
                # but also allow for it in the orig
                target_file_orig = Path(prefix_dir) / Path(target_file_orig)

            target_file_path_orig = annex.pathobj / target_file_orig

            # If we were invoked in a subdirectory, patch together the
            # correct path
            target_file_path = extract_rpath / target_file \
                if extract_rpath else target_file
            target_file_path = annex.pathobj / target_file_path

            # when the file already exists...
            if lexists(target_file_path):
                handle_existing = True
                if md5sum(str(target_file_path)) == \
                        md5sum(str(extracted_path)):
                    if not annex.is_under_annex(str(extracted_path)):
                        # if under annex -- must be having the same content,
                        # we should just add possibly a new extra URL
                        # but if under git -- we cannot/should not do
                        # anything about it ATM
                        if existing != 'overwrite':
                            continue
                    else:
                        handle_existing = False
                if not handle_existing:
                    pass  # nothing... just to avoid additional indentation
                elif existing == 'fail':
                    message = \
                        "{} exists, but would be overwritten by new file " \
                        "{}. Consider adjusting --existing".format\
                        (target_file_path, extracted_file)
                    yield get_status_dict(
                        ds=ds,
                        status='error',
                        message=message,
                        **res_kwargs)
                    return
                elif existing == 'overwrite':
                    stats.overwritten += 1
                    # to make sure it doesn't conflict -- might have been a
                    # tree
                    rmtree(target_file_path)
                else:
                    # an elaborate dance to piece together new archive names
                    target_file_path_orig_ = target_file_path

                    # To keep extension intact -- operate on the base of the
                    # filename
                    p, fn = os.path.split(target_file_path)
                    ends_with_dot = fn.endswith('.')
                    fn_base, fn_ext = file_basename(fn, return_ext=True)

                    if existing == 'archive-suffix':
                        fn_base += '-%s' % archive_basename
                    elif existing == 'numeric-suffix':
                        pass  # archive-suffix will have the same logic
                    else:
                        # we shouldn't get here, argparse should catch a
                        # non-existing value for --existing right away
                        raise ValueError(existing)
                    # keep incrementing index in the suffix until file
                    # doesn't collide
                    suf, i = '', 0
                    while True:
                        connector = \
                            ('.' if (fn_ext or ends_with_dot) else '')
                        file = fn_base + suf + connector + fn_ext
                        target_file_path_new =  \
                            Path(p) / Path(file)
                        if not lexists(target_file_path_new):
                            # we found a file name that is not yet taken
                            break
                        lgr.debug("Iteration %i of file name finding. "
                                  "File %s already exists", i,
                                  target_file_path_new)
                        i += 1
                        suf = '.%d' % i
                    target_file_path = target_file_path_new
                    lgr.debug("Original file %s will be saved into %s"
                              % (target_file_path_orig_, target_file_path))
                    # TODO: should we reserve smth like
                    # stats.clobbed += 1

            if target_file_path != target_file_path_orig:
                stats.renamed += 1

            if copy:
                raise NotImplementedError(
                    "Not yet copying from 'persistent' cache"
                )

            lgr.debug("Adding %s to annex pointing to %s and with options "
                      "%r", target_file_path, url, annex_options)

            try:
                out_json = annex.add_url_to_file(
                    target_file_path,
                    url, options=annex_options,
                    batch=True)
            except AnnexBatchCommandError as exc:
                if '.gitignored' in str(exc):
                    lgr.warning(
                        "%s matches .gitignore; skipping "
                        "(file not added to dataset)",
                        target_file_path)
                    stats.skipped += 1
                    continue
                raise

            if 'key' in out_json and out_json['key'] is not None:
                # annex.is_under_annex(target_file, batch=True):
                # due to http://git-annex.branchable.com/bugs/annex_drop_is_not___34__in_effect__34___for_load_which_was___34__addurl_--batch__34__ed_but_not_yet_committed/?updated
                # we need to maintain a list of those to be dropped files
                if drop_after:
                    # drop extracted files after adding to annex
                    annex.drop_key(out_json['key'], batch=True)
                    stats.dropped += 1
                stats.add_annex += 1
            else:
                lgr.debug("File %s was added to git, not adding url",
                    target_file_path)
                stats.add_git += 1

            if delete_after:
                # we count the removal here, but don't yet perform it
                # to not interfere with batched processes - any pure Git
                # action invokes precommit which closes batched processes.
                stats.removed += 1

            # Done with target_file -- just to have clear end of the loop
            del target_file

        if delete and archive and origin != 'key':
            lgr.debug("Removing the original archive %s", archive)
            # force=True since some times might still be staged and fail
            annex.remove(str(archive_path), force=True)

        lgr.info("Finished adding %s: %s", archive, stats.as_str(mode='line'))

        total_stats += stats

        if delete_after:
            # force since not committed. r=True for -r (passed into git call
            # to recurse)
            delete_after_rpath = opj(extract_rpath, prefix_dir) \
                if extract_rpath else prefix_dir
            lgr.debug(
                "Removing extracted and annexed files under %s",
                delete_after_rpath
            )
            annex.remove(str(ds.pathobj / delete_after_rpath), r=True,
                         force=True)
    finally:
        # take down the progress bar
        log_progress(
            lgr.info, pbar_id,
            'Finished extraction',
            noninteractive_level=logging.INFO)

        if delete_after_rpath:
            delete_after_path = str(ds.pathobj / delete_after_rpath)
            if exists(delete_after_path):  # should not be there
                # but for paranoid yoh
                lgr.warning(
                    "Removing temporary directory under which extracted "
                    "files were annexed and should have been removed: %s",
                    delete_after_path)
                rmtree(delete_after_path)

        # remove what is left and/or everything upon failure
        earchive.clean(force=True)
        # remove tempfile directories (not cleaned up automatically):
        if prefix_dir is not None:
            # it was created under the root of the dataset
            prefix_path = ds.pathobj / prefix_dir
            if lexists(prefix_path):
                os.rmdir(prefix_path)

    # the archive itself is the "subject" of this result record, unless we
    # were given a key, for which there is no path to point to
    res = get_status_dict(ds=ds, status='ok', **res_kwargs)
    if origin == 'key':
        res['key'] = key
    else:
        res.update(path=str(archive_path), type='file')
    yield res


def _get_commit_message(origin, archives):
    """Compose a commit message for the content of the given archives/keys"""
    if len(archives) == 1:
        return "Added content extracted from %s %s" % (origin, archives[0])
    return "Added content extracted from %d %ss:\n\n%s" % (
        len(archives), origin,
        "\n".join("- %s" % a for a in archives))


@build_doc
class AddArchiveContent(Interface):
    """Add content of an archive under git annex control.

    Given an already annex'ed archive, extract and add its files to the
    dataset, and reference the original archive as a custom special remote.

    Multiple archives can be provided in a single invocation. They are
    processed in the given order, and their content is added within a single
    commit, which is substantially faster than invoking the command once per
    archive. If any of the given archives cannot be used (e.g. it is not
    tracked by the dataset), nothing is added at all. If adding the content
    of an archive fails, the remaining archives are not processed, and
    whatever was added by then is left uncommitted for inspection.

    """
    _examples_ = [
        dict(text="""Add files from the archive 'big_tarball.tar.gz', but
                     keep big_tarball.tar.gz in the index""",
             code_py="add_archive_content(archive='big_tarball.tar.gz')",
             code_cmd="datalad add-archive-content big_tarball.tar.gz"),
        dict(text="""Add files from the archive 'tarball.tar.gz', and
                     remove big_tarball.tar.gz from the index""",
             code_py="add_archive_content(archive='big_tarball.tar.gz', delete=True)",
             code_cmd="datalad add-archive-content big_tarball.tar.gz --delete"),
        dict(text="""Add files from the archive 's3.zip' but remove the leading
                     directory""",
             code_py="add_archive_content(archive='s3.zip', strip_leading_dirs=True)",
             code_cmd="datalad add-archive-content s3.zip --strip-leading-dirs"),
        dict(text="""Add files from multiple archives, resulting in a single
                     commit""",
             code_py="add_archive_content(archive=['1.zip', '2.zip'])",
             code_cmd="datalad add-archive-content 1.zip 2.zip"),
        ]

    # XXX prevent common args from being added to the docstring
    _no_eval_results = True
    _params_ = dict(
        dataset=Parameter(
            args=("-d", "--dataset"),
            doc=""""specify the dataset to save""",
            constraints=EnsureDataset() | EnsureNone()),
        delete=Parameter(
            args=("-D", "--delete"),
            action="store_true",
            doc="""delete original archive from the filesystem/Git in current
            tree. %s""" % _KEY_OPT_NOTE),
        add_archive_leading_dir=Parameter(
            args=("--add-archive-leading-dir",),
            action="store_true",
            doc="""place extracted content under a directory which would
            correspond to the archive name with all suffixes stripped. E.g. the
            content of `archive.tar.gz` will be extracted under `archive/`"""),
        strip_leading_dirs=Parameter(
            args=("--strip-leading-dirs",),
            action="store_true",
            doc="""remove one or more leading directories from the archive
            layout on extraction"""),
        leading_dirs_depth=Parameter(
            args=("--leading-dirs-depth",),
            action="store",
            type=int,
            doc="""maximum depth of leading directories to strip.
            If not specified (None), no limit"""),
        leading_dirs_consider=Parameter(
            args=("--leading-dirs-consider",),
            action="append",
            doc="""regular expression(s) for directories to consider to strip
            away""",
            constraints=EnsureStr() | EnsureNone(),
        ),
        use_current_dir=Parameter(
            args=("--use-current-dir",),
            action="store_true",
            doc="""extract the archive under the current directory, not the
             directory where the archive is located. This parameter is applied
             automatically if [PY: `key=True` PY][CMD: --key CMD] was used."""),
        # TODO: add option to extract under archive's original directory. Currently would extract in curdir
        existing=Parameter(
            args=("--existing",),
            choices=('fail', 'overwrite', 'archive-suffix', 'numeric-suffix'),
            default="fail",
            doc="""what operation to perform if a file from an archive tries to
            overwrite an existing file with the same name.  'fail' (default)
            leads to an error result, 'overwrite' silently replaces
            existing file, 'archive-suffix' instructs to add a suffix (prefixed
            with a '-') matching archive name from which file gets extracted,
            and if that one is present as well, 'numeric-suffix' is in effect in
            addition, when incremental numeric suffix (prefixed with a '.') is
            added until no name collision is longer detected"""
        ),
        exclude=Parameter(
            args=("-e", "--exclude"),
            action='append',
            doc="""regular expressions for filenames which to exclude from being
            added to annex. Applied after --rename if that one is specified.
            For exact matching, use anchoring""",
            constraints=EnsureStr() | EnsureNone()
        ),
        rename=Parameter(
            args=("-r", "--rename"),
            action='append',
            doc="""regular expressions to rename files before added them under
            to Git. The first defines how to split provided string into
            two parts: Python regular expression (with groups), and replacement
            string""",
            constraints=EnsureStr(min_len=2) | EnsureNone()
        ),
        annex_options=Parameter(
            args=("-o", "--annex-options"),
            doc="""additional options to pass to git-annex """,
            constraints=EnsureStr() | EnsureNone()
        ),
        annex=Parameter(
            doc="""DEPRECATED. Use the 'dataset' parameter instead."""
        ),
        # TODO: Python only!
        stats=Parameter(
            doc="""ActivityStats instance for global tracking""",
        ),
        key=Parameter(
            args=("--key",),
            action="store_true",
            doc="""signal if provided archive is not actually a filename on its
            own but an annex key. The archive will be extracted in the current
            directory."""),
        copy=Parameter(
            args=("--copy",),
            action="store_true",
            doc="""copy the content of the archive instead of moving"""),
        allow_dirty=allow_dirty,
        commit=Parameter(
            args=("--no-commit",),
            action="store_false",
            dest="commit",
            doc="""don't commit upon completion"""),
        drop_after=Parameter(
            args=("--drop-after",),
            action="store_true",
            doc="""drop extracted files after adding to annex""",
        ),
        delete_after=Parameter(
            args=("--delete-after",),
            action="store_true",
            doc="""extract under a temporary directory, git-annex add, and
            delete afterwards. To be used to "index" files within annex without
            actually creating corresponding files under git. Note that
            `annex dropunused` would later remove that load"""),

        # TODO: interaction with archives cache whenever we make it persistent across runs
        archive=Parameter(
            args=("archive",),
            nargs="+",
            doc="""archive file or a key (if %s specified). Multiple archives
            (or keys) could be provided, and their content would be added
            within a single commit""" % _KEY_OPT,
            constraints=EnsureStr()),
    )

    @staticmethod
    @datasetmethod(name='add_archive_content')
    @eval_results
    def __call__(
            archive,
            *,
            dataset=None,
            annex=None,
            add_archive_leading_dir=False,
            strip_leading_dirs=False,
            leading_dirs_depth=None,
            leading_dirs_consider=None,
            use_current_dir=False,
            delete=False,
            key=False,
            exclude=None,
            rename=None,
            existing='fail',
            annex_options=None,
            copy=False,
            commit=True,
            allow_dirty=False,
            stats=None,
            drop_after=False,
            delete_after=False):

        if exclude:
            exclude = ensure_tuple_or_list(exclude)
        if rename:
            rename = ensure_tuple_or_list(rename)
        # a single archive (or key), or any number of them
        archives = ensure_list(archive)
        ds = require_dataset(dataset,
                             check_installed=True,
                             purpose='add-archive-content')

        # set up common params for result records
        res_kwargs = {
            'action': 'add-archive-content',
            'logger': lgr,
        }

        if not isinstance(ds.repo, AnnexRepo):
            yield get_status_dict(
                ds=ds,
                status='impossible',
                message="Can't operate in a pure Git repository",
                **res_kwargs
            )
            return
        if annex:
            warnings.warn(
                "datalad add_archive_content's `annex` parameter is "
                "deprecated and will be removed in a future release. "
                "Use the 'dataset' parameter instead.",
                DeprecationWarning)
        annex = ds.repo

        if not archives:
            yield get_status_dict(
                ds=ds,
                status='impossible',
                message='No archive was specified',
                **res_kwargs
            )
            return

        # Vet all archives before doing any modification of the dataset, so
        # that we do not end up with a partial addition whenever one of the
        # archives cannot be used.
        problems = False
        # (archive, absolute path) pairs
        archive_paths = []
        for a in archives:
            # get the archive path relative from the ds root
            archive_path = resolve_path(a, ds=dataset)
            archive_paths.append((a, archive_path))
            # let Status decide whether we can act on the given file
            for s in ds.status(
                    path=archive_path,
                    on_failure='ignore',
                    result_renderer='disabled'):
                if s['status'] == 'error':
                    if 'path not underneath the reference dataset %s' in s['message']:
                        yield get_status_dict(
                            ds=ds,
                            status='impossible',
                            message='Can not add archive outside of the dataset',
                            **res_kwargs)
                    else:
                        # status errored & we haven't anticipated the cause.
                        # Bubble up
                        yield s
                    problems = True
                    break
                elif s['state'] == 'untracked':
                    # we can't act on an untracked file
                    message = (
                        "Can not add an untracked archive. "
                        "Run 'datalad save {}'".format(a)
                    )
                    yield get_status_dict(
                               ds=ds,
                               status='impossible',
                               message=message,
                               **res_kwargs)
                    problems = True
                    break
        if problems:
            return

        if not allow_dirty and annex.dirty:
            # error out here if the dataset contains untracked changes
            yield get_status_dict(
                ds=ds,
                status='impossible',
                message=(
                    'clean dataset required. '
                    'Use `datalad status` to inspect unsaved changes'),
                **res_kwargs
            )
            return

        if key:
            # we must not have anything to do with the location under
            # .git/annex, so we will go from the current directory
            use_current_dir = True

        # figure out our location
        pwd = getpwd()

        # what needs to be done: (archive, path, key, extraction directory)
        todo = []
        for a, archive_path in archive_paths:
            # ensure the archive exists, status doesn't error on a
            # non-existing file
            if not key and not lexists(archive_path):
                yield get_status_dict(
                    ds=ds,
                    status='impossible',
                    message=(
                        'No such file: {}'.format(archive_path),
                    ),
                    **res_kwargs
                )
                problems = True
                continue

            if not key:
                check_path = archive_path.relative_to(ds.pathobj)
                # TODO: support adding archives content from outside the annex/repo
                # can become get_file_annexinfo once #6104 is merged
                akey = annex.get_file_annexinfo(check_path)['key']
                if not akey:
                    # if we didn't manage to get a key, the file must be in Git
                    raise RuntimeError(
                        f"Archive must be an annexed file in {ds}")
                archive_dir = Path(archive_path).parent
            else:
                akey = a
                archive_dir = None

            # are we in a subdirectory of the repository?
            pwd_in_root = annex.path == archive_dir
            # then we should add content under that subdirectory,
            # get the path relative to the repo top
            if use_current_dir:
                # extract the archive under the current directory, not the
                # directory where the archive is located
                extract_rpath = Path(pwd).relative_to(ds.path) \
                    if not pwd_in_root \
                    else None
            else:
                extract_rpath = archive_dir.relative_to(ds.path)

            # relpath might return '.' as the relative path to curdir, which
            # then normalize_paths would take as instructions to really go
            # from cwd, so we need to sanitize
            if extract_rpath == curdir:
                extract_rpath = None

            todo.append((a, archive_path, akey, extract_rpath))
        if problems:
            return

        origin = 'key' if key else 'archive'

        from datalad.customremotes.archives import ArchiveAnnexCustomRemote

        # TODO: shouldn't we be able just to pass existing AnnexRepo instance?
        # TODO: we will use persistent cache so we could just (ab)use possibly extracted archive
        # OK, let's ignore that the following class is actually a special
        # remote implementation, and use it only to work with its cache
        annexarchive = ArchiveAnnexCustomRemote(annex=None,
                                                path=annex.path,
                                                persistent_cache=True)
        # We will move extracted content so it must not exist prior running
        annexarchive.cache.allow_existing = True
        # make sure there is an enabled datalad-archives special remote
        ensure_datalad_remote(ds.repo, remote=ARCHIVES_SPECIAL_REMOTE,
                              autoenable=True)

        precommitted = False
        old_always_commit = annex.always_commit
        # batch mode is disabled when faking dates, we want to always commit
        annex.always_commit = annex.fake_dates_enabled
        if annex_options:
            if isinstance(annex_options, str):
                annex_options = split_cmdline(annex_options)

        # dedicated stats which would be added to passed in (if any)
        outside_stats = stats
        stats = ActivityStats()

        # archives which content was added, to be mentioned in the commit
        # message
        added = []
        failed = False
        # a progress bar across all archives is only of use if there is more
        # than a single one, individual archives have their own
        report_progress = len(todo) > 1
        pbar_id = f'add-archive-content-{ds.path}'
        if report_progress:
            log_progress(
                lgr.info, pbar_id, 'Adding archives content',
                label="Adding archives",
                unit=' Archives',
                total=len(todo),
                noninteractive_level=logging.INFO)
        try:
            for i, (a, archive_path, akey, extract_rpath) in enumerate(todo):
                for res in _add_archive_content(
                        a,
                        ds=ds,
                        annex=annex,
                        annexarchive=annexarchive,
                        key=akey,
                        origin=origin,
                        archive_path=archive_path,
                        extract_rpath=extract_rpath,
                        total_stats=stats,
                        res_kwargs=res_kwargs,
                        add_archive_leading_dir=add_archive_leading_dir,
                        strip_leading_dirs=strip_leading_dirs,
                        leading_dirs_depth=leading_dirs_depth,
                        leading_dirs_consider=leading_dirs_consider,
                        delete=delete,
                        exclude=exclude,
                        rename=rename,
                        existing=existing,
                        annex_options=annex_options,
                        copy=copy,
                        drop_after=drop_after,
                        delete_after=delete_after):
                    if res['status'] not in ('ok', 'notneeded'):
                        failed = True
                    yield res
                if report_progress:
                    log_progress(
                        lgr.info, pbar_id,
                        "Archives left to add %i ", len(todo) - i - 1,
                        update=1,
                        increment=True,
                        noninteractive_level=logging.DEBUG)
                if failed:
                    # do not proceed with the remaining archives, and do not
                    # commit -- the user should decide how to continue
                    break
                added.append(
                    akey if origin == 'key'
                    else archive_path.relative_to(ds.path))

            if not failed:
                if outside_stats:
                    outside_stats += stats
                if commit:
                    commit_stats = outside_stats if outside_stats else stats
                    # so batched ones close and files become annex symlinks etc
                    annex.precommit()
                    precommitted = True
                    if any(r.get('state', None) != 'clean'
                           for p, r in annex.status(untracked='no').items()):
                        annex.commit(
                            "%s\n\n%s" % (
                                _get_commit_message(origin, added),
                                commit_stats.as_str(mode='full')),
                            _datalad_msg=True
                        )
                        commit_stats.reset()
                else:
                    # don't commit upon completion
                    pass
        finally:
            if report_progress:
                log_progress(
                    lgr.info, pbar_id,
                    'Finished adding archives content',
                    noninteractive_level=logging.INFO)
            # since we batched addurl, we should close those batched processes
            # if haven't done yet.  explicitly checked to avoid any possible
            # "double-action"
            if not precommitted:
                annex.precommit()

            annex.always_commit = old_always_commit

        if failed:
            # the problem was reported already, do not pretend that all is
            # good with the dataset
            return
        yield get_status_dict(
            ds=ds,
            status='ok',
            **res_kwargs)
        return annex
