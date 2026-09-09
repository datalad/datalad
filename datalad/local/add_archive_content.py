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
from collections import namedtuple
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
    with_result_progress,
)
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    AnnexBatchCommandError,
    CapturedException,
)
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
        key_rpath,
        origin,
        archive_path,
        extract_rpath,
        total_stats,
        res_kwargs,
        add_archive_leading_dir=False,
        strip_leading_dirs=False,
        leading_dirs_depth=None,
        leading_dirs_consider=None,
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
    commit.  The removal of the original archive (`delete`) is left to the
    caller as well, for the same reason.

    Parameters
    ----------
    archive : str or Path
      Archive (or a key, if `origin` is 'key') as specified by the caller.
      Used to derive names for the extracted content, and for messages.
    ds : Dataset
    annex : AnnexRepo
      Repository of `ds`.
    annexarchive : ArchiveAnnexCustomRemote
      Provides the cache of extracted archives, and the URLs to compose for
      the extracted files.
    key : str
      Annex key of the archive.
    key_rpath : str or Path
      Location of the content of `key`, as established (and thus verified to
      be present) by the caller.
    origin : {'archive', 'key'}
      Whether the archive was specified as a file or as an annex key.
    archive_path : Path
      Absolute path of the archive.
    extract_rpath : Path or None
      Directory, relative to the root of `ds`, to extract the content into.
      `None` stands for the root of the dataset itself.
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
            label="Extracting %s" % archive_basename,
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
                        "{} of {}. Consider adjusting --existing".format\
                        (target_file_path, extracted_file, archive)
                    # point at the archive we are failing on, it is not
                    # necessarily the only one we were given
                    yield get_status_dict(
                        ds=ds,
                        status='error',
                        message=message,
                        **_archive_res_kwargs(archive_path, key, origin),
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
                try:
                    os.rmdir(prefix_path)
                except OSError as exc:
                    # do not mask an exception which brought us here in the
                    # first place, and which likely explains the leftovers
                    lgr.warning("Failed to remove temporary directory %s: %s",
                                prefix_path, CapturedException(exc))

    yield get_status_dict(
        ds=ds,
        status='ok',
        message=("added content of key %s", key) if origin == 'key' else None,
        **_archive_res_kwargs(archive_path, key, origin),
        **res_kwargs)


@with_result_progress("Adding archives", unit=" Archives")
def _add_archives_content(todo, **kwargs):
    """Add the content of each archive of `todo`, stopping at the first failure

    `todo` is a list of `_ArchiveSpec` instances, the remaining arguments are
    passed on to `_add_archive_content()`.
    """
    for spec in todo:
        failed = False
        for res in _add_archive_content(
                spec.archive,
                key=spec.key,
                key_rpath=spec.key_rpath,
                archive_path=spec.path,
                extract_rpath=spec.extract_rpath,
                **kwargs):
            failed = failed or res['status'] not in ('ok', 'notneeded')
            yield res
        if failed:
            # do not touch the remaining archives: the caller will not commit,
            # and it is up to the user to decide how to continue
            return


# what needs to be done for a single archive, as established by the vetting
_ArchiveSpec = namedtuple(
    '_ArchiveSpec', 'archive path key key_rpath extract_rpath')



def _archive_res_kwargs(archive_path, key, origin):
    """Result record fields to identify the archive (or key) acted on"""
    if origin == 'key':
        # there is no meaningful path to point to, but the key identifies it
        return dict(type='key', key=key)
    return dict(path=str(archive_path), type='file')


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

    Multiple archives can be given in a single invocation. They are processed
    in the given order, and their content is added within a single commit,
    which is substantially faster than invoking the command once per archive.

    All given archives are checked before any of them is acted on: if any one
    of them cannot be used (it is untracked, absent, not under annex control,
    or its content is not available locally), nothing is added at all.
    Should adding the content of an archive fail nevertheless, the remaining
    archives are not processed, and nothing is committed: the content added
    up to that point is left staged for inspection, and a subsequent
    invocation will refuse to operate on such a dirty dataset until those
    changes are dealt with. Original archives are removed
    ([PY: `delete=True` PY][CMD: --delete CMD]) only once all of them were
    added successfully.

    .. versionchanged:: 1.7
       More than one archive can be given. A result record is now yielded for
       each given archive, in addition to the one for the dataset.

    """
    _examples_ = [
        dict(text="""Add files from the archive 'big_tarball.tar.gz', but
                     keep big_tarball.tar.gz in the index""",
             code_py="add_archive_content(archive='big_tarball.tar.gz')",
             code_cmd="datalad add-archive-content big_tarball.tar.gz"),
        dict(text="""Add files from the archive 'big_tarball.tar.gz', and
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
            doc="""specify the dataset to operate on""",
            constraints=EnsureDataset() | EnsureNone()),
        delete=Parameter(
            args=("-D", "--delete"),
            action="store_true",
            doc="""delete original archives from the filesystem/Git in current
            tree, once the content of all of them was added. %s"""
            % _KEY_OPT_NOTE),
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
            doc="""signal that the provided archives are not filenames on
            their own but annex keys. Such archives are extracted in the
            current directory."""),
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
            metavar='ARCHIVE',
            nargs="+",
            doc="""archive file or a key (if %s specified). More than one can
            be given; the content of all of them is added within a single
            commit""" % _KEY_OPT,
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

        # what kind of thing we were given, used for result records and the
        # commit message
        origin = 'key' if key else 'archive'

        if not archives or not all(str(a) for a in archives):
            yield get_status_dict(
                ds=ds,
                status='impossible',
                message='No archive was specified',
                **res_kwargs
            )
            return

        # Vet all archives before modifying the dataset in any way, so that
        # nothing is added whenever any one of them can not be used
        problems = False
        archive_paths = list(zip(
            archives, resolve_path(archives, ds=dataset, ds_resolved=ds)))

        if key:
            # we must not have anything to do with the location under
            # .git/annex, so we will go from the current directory
            use_current_dir = True

        # figure out our location
        pwd = getpwd()

        precommitted = False
        failed = False
        old_always_commit = annex.always_commit
        # batch mode is disabled when faking dates, we want to always commit
        annex.always_commit = annex.fake_dates_enabled
        # from here on batched git-annex processes may be in use, they are
        # closed by the precommit() in the `finally`
        try:
            # a single `status` query tells us everything we need to know about
            # all archives at once: whether we can act on them at all, their
            # annex key, and where the content of that key is
            status_records = {}
            if not key:
                for s in ds.status(
                        path=[p for _, p in archive_paths],
                        annex='availability',
                        on_failure='ignore',
                        result_renderer='disabled'):
                    status_records.setdefault(str(s['path']), s)

            todo = []
            for a, archive_path in archive_paths:
                akey = key_rpath = archive_dir = None
                # a message for a problem which prevents us from using this
                # archive, or a result record to bubble up as is
                problem = bubbled = None
                if key:
                    # a key has no path to inspect, we can only ask for the
                    # location of its content
                    akey = a
                    key_rpath = annex.get_contentlocation(akey, batch=True)
                    if not key_rpath:
                        problem = (
                            'Content of %s is not available, get it first', a)
                else:
                    s = status_records.get(str(archive_path))
                    message = (s or {}).get('message')
                    if s is None or s['status'] == 'error':
                        if message and \
                                'path not underneath the reference dataset %s' \
                                in message:
                            problem = \
                                'Can not add archive outside of the dataset'
                        elif s is None or s.get('state') == 'unknown':
                            problem = 'No such file: {}'.format(archive_path)
                        else:
                            # errored for a cause we have not anticipated
                            bubbled = s
                    elif s['state'] == 'untracked':
                        # we can't act on an untracked file
                        problem = ("Can not add an untracked archive. "
                                   "Run 'datalad save {}'".format(a))
                    elif not s.get('key'):
                        # no key -- the archive is in Git
                        problem = (
                            'Archive must be an annexed file, %s is not', a)
                    elif not s.get('objloc'):
                        problem = (
                            'Content of %s is not available, get it first', a)
                    else:
                        akey, key_rpath = s['key'], s['objloc']
                        archive_dir = Path(archive_path).parent
                if problem or bubbled:
                    yield bubbled or get_status_dict(
                        ds=ds,
                        status='impossible',
                        message=problem,
                        **_archive_res_kwargs(archive_path, a, origin),
                        **res_kwargs)
                    problems = True
                    continue

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

                # relpath might return '.' as the relative path to curdir,
                # which then normalize_paths would take as instructions to
                # really go from cwd, so we need to sanitize
                if extract_rpath == curdir:
                    extract_rpath = None

                todo.append(_ArchiveSpec(
                    a, archive_path, akey, key_rpath, extract_rpath))
            if problems:
                return

            if not allow_dirty and annex.dirty:
                # error out here if the dataset contains untracked changes.
                # This comes after the vetting above, so that a problem with
                # an archive itself (an untracked one in particular) is
                # reported in its own terms
                yield get_status_dict(
                    ds=ds,
                    status='impossible',
                    message=(
                        'clean dataset required. '
                        'Use `datalad status` to inspect unsaved changes'),
                    **res_kwargs
                )
                return

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

            if annex_options and isinstance(annex_options, str):
                annex_options = split_cmdline(annex_options)

            # dedicated stats which would be added to passed in (if any)
            outside_stats = stats
            stats = ActivityStats()

            for res in _add_archives_content(
                    todo,
                    ds=ds,
                    annex=annex,
                    annexarchive=annexarchive,
                    origin=origin,
                    total_stats=stats,
                    res_kwargs=res_kwargs,
                    add_archive_leading_dir=add_archive_leading_dir,
                    strip_leading_dirs=strip_leading_dirs,
                    leading_dirs_depth=leading_dirs_depth,
                    leading_dirs_consider=leading_dirs_consider,
                    exclude=exclude,
                    rename=rename,
                    existing=existing,
                    annex_options=annex_options,
                    copy=copy,
                    drop_after=drop_after,
                    delete_after=delete_after):
                failed = failed or res['status'] not in ('ok', 'notneeded')
                yield res

            if not failed:
                if delete and origin != 'key':
                    # only now, when the content of all archives was added: a
                    # failure should not leave a removal behind, and removing
                    # tears down the batched processes we reuse across archives
                    lgr.debug("Removing the original archives")
                    # force=True since some times might still be staged and fail
                    annex.remove([str(s.path) for s in todo], force=True)
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
                                _get_commit_message(origin, [
                                    s.key if origin == 'key'
                                    else s.path.relative_to(ds.path)
                                    for s in todo]),
                                commit_stats.as_str(mode='full')),
                            _datalad_msg=True
                        )
                        commit_stats.reset()
        finally:
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
