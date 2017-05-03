# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""High-level interface for adding content of an archive under annex control

"""
from __future__ import print_function

__docformat__ = 'restructuredtext'


import re
import os
import shlex
import tempfile

from os.path import join as opj, realpath, curdir, exists, lexists, relpath, basename
from os.path import commonprefix
from os.path import sep as opsep
from os.path import islink
from os.path import isabs
from os.path import dirname
from os.path import normpath

from .base import Interface
from .common_opts import allow_dirty
from ..consts import ARCHIVES_SPECIAL_REMOTE
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone

from ..support.annexrepo import AnnexRepo
from ..support.strings import apply_replacement_rules
from ..support.stats import ActivityStats
from ..cmdline.helpers import get_repo_instance
from ..utils import getpwd, rmtree, file_basename
from ..utils import md5sum
from ..utils import assure_tuple_or_list

from datalad.customremotes.base import init_datalad_remote

from six import string_types

from ..log import logging
lgr = logging.getLogger('datalad.interfaces.add_archive_content')


# Shortcut note
_KEY_OPT = "[PY: `key=True` PY][CMD: --key CMD]"
_KEY_OPT_NOTE = "Note that it will be of no effect if %s is given" % _KEY_OPT

# TODO: may be we could enable separate logging or add a flag to enable
# all but by default to print only the one associated with this given action


class AddArchiveContent(Interface):
    """Add content of an archive under git annex control.

    This results in the files within archive (which should be under annex
    control itself) added under annex referencing original archive via
    custom special remotes mechanism

    Example:

        annex-repo$ datalad add-archive-content my_big_tarball.tar.gz

    """
    _params_ = dict(
        delete=Parameter(
            args=("-d", "--delete"),
            action="store_true",
            doc="""flag to delete original archive from the filesystem/git in current tree.
                   %s""" % _KEY_OPT_NOTE),
        add_archive_leading_dir=Parameter(
            args=("--add-archive-leading-dir",),
            action="store_true",
            doc="""flag to place extracted content under a directory which would correspond
                   to archive name with suffix stripped.  E.g. for archive `example.zip` its
                   content will be extracted under a directory `example/`"""),
        strip_leading_dirs=Parameter(
            args=("--strip-leading-dirs",),
            action="store_true",
            doc="""flag to move all files directories up, from how they were stored in an archive,
                   if that one contained a number (possibly more than 1 down) single leading
                   directories"""),
        leading_dirs_depth=Parameter(
            args=("--leading-dirs-depth",),
            action="store",
            type=int,
            doc="""maximal depth to strip leading directories to.  If not specified (None), no limit"""),
        leading_dirs_consider=Parameter(
            args=("--leading-dirs-consider",),
            action="append",
            doc="""regular expression(s) for directories to consider to strip away""",
            constraints=EnsureStr() | EnsureNone(),
        ),
        use_current_dir=Parameter(
            args=("--use-current-dir",),
            action="store_true",
            doc="""flag to extract archive under the current directory,  not the directory where archive is located.
                   %s""" % _KEY_OPT_NOTE),
        # TODO: add option to extract under archive's original directory. Currently would extract in curdir
        existing=Parameter(
            args=("--existing",),
            choices=('fail', 'overwrite', 'archive-suffix', 'numeric-suffix'),
            default="fail",
            doc="""what operation to perform a file from archive tries to overwrite an existing
             file with the same name.  'fail' (default) leads to RuntimeError exception.
             'overwrite' silently replaces existing file.  'archive-suffix' instructs to add
             a suffix (prefixed with a '-') matching archive name from which file gets extracted,
             and if that one present, 'numeric-suffix' is in effect in addition, when incremental
             numeric suffix (prefixed with a '.') is added until no name collision is longer detected"""
        ),
        exclude=Parameter(
            args=("-e", "--exclude"),
            action='append',
            doc="""regular expressions for filenames which to exclude from being added to annex.
            Applied after --rename if that one is specified.  For exact matching, use anchoring""",
            constraints=EnsureStr() | EnsureNone()
        ),
        rename=Parameter(
            args=("-r", "--rename"),
            action='append',
            doc="""regular expressions to rename files before being added under git.
            First letter defines how to split provided string into two parts:
            Python regular expression (with groups), and replacement string""",
            constraints=EnsureStr(min_len=2) | EnsureNone()
        ),
        annex_options=Parameter(
            args=("-o", "--annex-options"),
            doc="""additional options to pass to git-annex""",
            constraints=EnsureStr() | EnsureNone()
        ),
        # TODO: Python only???
        annex=Parameter(
            doc="""annex instance to use"""
            #constraints=EnsureStr() | EnsureNone()
        ),
        # TODO: Python only!
        stats=Parameter(
            doc="""ActivityStats instance for global tracking""",
        ),
        key=Parameter(
            args=("--key",),
            action="store_true",
            doc="""flag to signal if provided archive is not actually a filename on its own but an annex key"""),
        copy=Parameter(
            args=("--copy",),
            action="store_true",
            doc="""flag to copy the content of the archive instead of moving"""),
        allow_dirty=allow_dirty,
        commit=Parameter(
            args=("--no-commit",),
            action="store_false",
            dest="commit",
            doc="""flag to not commit upon completion"""),
        drop_after=Parameter(
            args=("--drop-after",),
            action="store_true",
            doc="""drop extracted files after adding to annex""",
        ),
        delete_after=Parameter(
            args=("--delete-after",),
            action="store_true",
            doc="""extract under a temporary directory, git-annex add, and delete after.  To
             be used to "index" files within annex without actually creating corresponding
             files under git.  Note that `annex dropunused` would later remove that load"""),

        # TODO: interaction with archives cache whenever we make it persistent across runs
        archive=Parameter(
            doc="archive file or a key (if %s specified)" % _KEY_OPT,
            constraints=EnsureStr()),
    )

        # use-case from openfmri pipeline
        #     ExtractArchives(
        #         # will do the merge of 'replace' strategy
        #         source_branch="incoming",
        #         regex="\.(tgz|tar\..*)$",
        #         renames=[
        #             ("^[^/]*/(.*)", "\1") # e.g. to strip leading dir, or could prepend etc
        #         ],
        #         #exclude="license.*",  # regexp
        #     ),

    @staticmethod
    def __call__(archive, annex=None,
                 add_archive_leading_dir=False,
                 strip_leading_dirs=False, leading_dirs_depth=None, leading_dirs_consider=None,
                 use_current_dir=False,
                 delete=False, key=False, exclude=None, rename=None, existing='fail',
                 annex_options=None, copy=False, commit=True, allow_dirty=False,
                 stats=None, drop_after=False, delete_after=False):
        """
        Returns
        -------
        annex
        """
        if exclude:
            exclude = assure_tuple_or_list(exclude)
        if rename:
            rename = assure_tuple_or_list(rename)

        # TODO: actually I see possibly us asking user either he wants to convert
        # his git repo into annex
        archive_path = archive
        pwd = getpwd()
        if annex is None:
            annex = get_repo_instance(pwd, class_=AnnexRepo)
            if not isabs(archive):
                # if not absolute -- relative to wd and thus
                archive_path = normpath(opj(realpath(pwd), archive))
                # abspath(archive) is not "good" since dereferences links in the path
                # archive_path = abspath(archive)
        elif not isabs(archive):
            # if we are given an annex, then assume that given path is within annex, not
            # relative to PWD
            archive_path = opj(annex.path, archive)
        annex_path = annex.path

        # _rpath below should depict paths relative to the top of the annex
        archive_rpath = relpath(archive_path, annex_path)

        # TODO: somewhat too cruel -- may be an option or smth...
        if not allow_dirty and annex.dirty:
            # already saved me once ;)
            raise RuntimeError("You better commit all the changes and untracked files first")

        if not key:
            # we were given a file which must exist
            if not exists(archive_path):
                raise ValueError("Archive {} does not exist".format(archive))
            # TODO: support adding archives content from outside the annex/repo
            origin = 'archive'
            key = annex.get_file_key(archive_rpath)
            archive_dir = dirname(archive_path)
        else:
            origin = 'key'
            key = archive
            archive_dir = None  # We must not have anything to do with the location under .git/annex

        archive_basename = file_basename(archive)

        if not key:
            # TODO: allow for it to be under git???  how to reference then?
            raise NotImplementedError(
                "Provided file %s is not under annex.  We don't support yet adding everything "
                "straight to git" % archive
            )

        # are we in a subdirectory of the repository?
        pwd_under_annex = commonprefix([pwd, annex_path]) == annex_path
        #  then we should add content under that
        # subdirectory,
        # get the path relative to the repo top
        if use_current_dir:
            # if outside -- extract to the top of repo
            extract_rpath = relpath(pwd, annex_path) \
                if pwd_under_annex \
                else None
        else:
            extract_rpath = relpath(archive_dir, annex_path)

        # relpath might return '.' as the relative path to curdir, which then normalize_paths
        # would take as instructions to really go from cwd, so we need to sanitize
        if extract_rpath == curdir:
            extract_rpath = None  # no special relpath from top of the repo

        # and operate from now on the key or whereever content available "canonically"
        try:
            key_rpath = annex.get_contentlocation(key)  # , relative_to_top=True)
        except:
            raise RuntimeError("Content of %s seems to be N/A.  Fetch it first" % key)

        # now we simply need to go through every file in that archive and
        lgr.info("Adding content of the archive %s into annex %s", archive, annex)

        from datalad.customremotes.archives import ArchiveAnnexCustomRemote
        # TODO: shouldn't we be able just to pass existing AnnexRepo instance?
        # TODO: we will use persistent cache so we could just (ab)use possibly extracted archive
        annexarchive = ArchiveAnnexCustomRemote(path=annex_path, persistent_cache=True)
        # We will move extracted content so it must not exist prior running
        annexarchive.cache.allow_existing = True
        earchive = annexarchive.cache[key_rpath]

        # TODO: check if may be it was already added
        if ARCHIVES_SPECIAL_REMOTE not in annex.get_remotes():
            init_datalad_remote(annex, ARCHIVES_SPECIAL_REMOTE, autoenable=True)
        else:
            lgr.debug("Special remote {} already exists".format(ARCHIVES_SPECIAL_REMOTE))

        precommitted = False
        delete_after_rpath = None
        try:
            old_always_commit = annex.always_commit
            annex.always_commit = False

            if annex_options:
                if isinstance(annex_options, string_types):
                    annex_options = shlex.split(annex_options)

            leading_dir = earchive.get_leading_directory(
                depth=leading_dirs_depth, exclude=exclude, consider=leading_dirs_consider) \
                if strip_leading_dirs else None
            leading_dir_len = len(leading_dir) + len(opsep) if leading_dir else 0

            # we need to create a temporary directory at the top level which would later be
            # removed
            prefix_dir = basename(tempfile.mktemp(prefix=".datalad", dir=annex_path)) \
                if delete_after \
                else None

            # dedicated stats which would be added to passed in (if any)
            outside_stats = stats
            stats = ActivityStats()

            for extracted_file in earchive.get_extracted_files():
                stats.files += 1
                extracted_path = opj(earchive.path, extracted_file)

                if islink(extracted_path):
                    link_path = realpath(extracted_path)
                    if not exists(link_path):  # TODO: config  addarchive.symlink-broken='skip'
                        lgr.warning("Path %s points to non-existing file %s" % (extracted_path, link_path))
                        stats.skipped += 1
                        continue
                        # TODO: check if points outside of the archive -- warning and skip

                # preliminary target name which might get modified by renames
                target_file_orig = target_file = extracted_file

                # strip leading dirs
                target_file = target_file[leading_dir_len:]

                if add_archive_leading_dir:
                    target_file = opj(archive_basename, target_file)

                if rename:
                    target_file = apply_replacement_rules(rename, target_file)

                # continue to next iteration if extracted_file in excluded
                if exclude:
                    try:  # since we need to skip outside loop from inside loop
                        for regexp in exclude:
                            if re.search(regexp, extracted_file):
                                lgr.debug(
                                    "Skipping {extracted_file} since contains {regexp} pattern".format(**locals()))
                                stats.skipped += 1
                                raise StopIteration
                    except StopIteration:
                        continue

                if prefix_dir:
                    target_file = opj(prefix_dir, target_file)
                    # but also allow for it in the orig
                    target_file_orig = opj(prefix_dir, target_file_orig)

                target_file_path_orig = opj(annex.path, target_file_orig)

                url = annexarchive.get_file_url(archive_key=key, file=extracted_file, size=os.stat(extracted_path).st_size)

                # lgr.debug("mv {extracted_path} {target_file}. URL: {url}".format(**locals()))

                target_file_path = opj(extract_rpath, target_file) \
                    if extract_rpath else target_file

                target_file_path = opj(annex.path, target_file_path)

                if lexists(target_file_path):
                    handle_existing = True
                    if md5sum(target_file_path) == md5sum(extracted_path):
                        if not annex.is_under_annex(extracted_path):
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
                        raise RuntimeError(
                            "File {} already exists, but new (?) file {} was instructed "
                            "to be placed there while overwrite=False".format
                                (target_file_path, extracted_file)
                        )
                    elif existing == 'overwrite':
                        stats.overwritten += 1
                        # to make sure it doesn't conflict -- might have been a tree
                        rmtree(target_file_path)
                    else:
                        target_file_path_orig_ = target_file_path

                        # To keep extension intact -- operate on the base of the filename
                        p, fn = os.path.split(target_file_path)
                        ends_with_dot = fn.endswith('.')
                        fn_base, fn_ext = file_basename(fn, return_ext=True)

                        if existing == 'archive-suffix':
                            fn_base += '-%s' % archive_basename
                        elif existing == 'numeric-suffix':
                            pass  # archive-suffix will have the same logic
                        else:
                            raise ValueError(existing)
                        # keep incrementing index in the suffix until file doesn't collide
                        suf, i = '', 0
                        while True:
                            target_file_path_new = opj(p, fn_base + suf + ('.' if (fn_ext or ends_with_dot) else '') + fn_ext)
                            if not lexists(target_file_path_new):
                                break
                            lgr.debug("File %s already exists" % target_file_path_new)
                            i += 1
                            suf = '.%d' % i
                        target_file_path = target_file_path_new
                        lgr.debug("Original file %s will be saved into %s"
                                  % (target_file_path_orig_, target_file_path))
                        # TODO: should we reserve smth like
                        # stats.clobbed += 1

                if target_file_path != target_file_path_orig:
                    stats.renamed += 1

                #target_path = opj(getpwd(), target_file)
                if copy:
                    raise NotImplementedError("Not yet copying from 'persistent' cache")
                else:
                    # os.renames(extracted_path, target_path)
                    # addurl implementation relying on annex'es addurl below would actually copy
                    pass

                lgr.debug("Adding %s to annex pointing to %s and with options %r",
                          target_file_path, url, annex_options)

                out_json = annex.add_url_to_file(
                    target_file_path,
                    url, options=annex_options,
                    batch=True)

                if 'key' in out_json and out_json['key'] is not None:  # annex.is_under_annex(target_file, batch=True):
                    # due to http://git-annex.branchable.com/bugs/annex_drop_is_not___34__in_effect__34___for_load_which_was___34__addurl_--batch__34__ed_but_not_yet_committed/?updated
                    # we need to maintain a list of those to be dropped files
                    if drop_after:
                        annex.drop_key(out_json['key'], batch=True)
                        stats.dropped += 1
                    stats.add_annex += 1
                else:
                    lgr.debug("File {} was added to git, not adding url".format(target_file_path))
                    stats.add_git += 1

                if delete_after:
                    # delayed removal so it doesn't interfer with batched processes since any pure
                    # git action invokes precommit which closes batched processes. But we like to count
                    stats.removed += 1

                # # chaining 3 annex commands, 2 of which not batched -- less efficient but more bullet proof etc
                # annex.add(target_path, options=annex_options)
                # # above action might add to git or to annex
                # if annex.file_has_content(target_path):
                #     # if not --  it was added to git, if in annex, it is present and output is True
                #     annex.add_url_to_file(target_file, url, options=['--relaxed'], batch=True)
                #     stats.add_annex += 1
                # else:
                #     lgr.debug("File {} was added to git, not adding url".format(target_file))
                #     stats.add_git += 1
                # # TODO: actually check if it is anyhow different from a previous version. If not
                # # then it wasn't really added

                del target_file  # Done with target_file -- just to have clear end of the loop

            if delete and archive and origin != 'key':
                lgr.debug("Removing the original archive {}".format(archive))
                # force=True since some times might still be staged and fail
                annex.remove(archive_rpath, force=True)

            lgr.info("Finished adding %s: %s" % (archive, stats.as_str(mode='line')))

            if outside_stats:
                outside_stats += stats
            if delete_after:
                # force since not committed. r=True for -r (passed into git call
                # to recurse)
                delete_after_rpath = opj(extract_rpath, prefix_dir) if extract_rpath else prefix_dir
                lgr.debug(
                    "Removing extracted and annexed files under %s",
                    delete_after_rpath
                )
                annex.remove(delete_after_rpath, r=True, force=True)
            if commit:
                commit_stats = outside_stats if outside_stats else stats
                annex.precommit()  # so batched ones close and files become annex symlinks etc
                precommitted = True
                if annex.is_dirty(untracked_files=False):
                    annex.commit(
                        "Added content extracted from %s %s\n\n%s" %
                        (origin, archive, commit_stats.as_str(mode='full')),
                        _datalad_msg=True
                    )
                    commit_stats.reset()
        finally:
            # since we batched addurl, we should close those batched processes
            # if haven't done yet.  explicitly checked to avoid any possible
            # "double-action"
            if not precommitted:
                annex.precommit()

            if delete_after_rpath:
                delete_after_path = opj(annex_path, delete_after_rpath)
                if exists(delete_after_path):  # should not be there
                    # but for paranoid yoh
                    lgr.warning(
                        "Removing temporary directory under which extracted "
                        "files were annexed and should have been removed: %s",
                        delete_after_path)
                    rmtree(delete_after_path)

            annex.always_commit = old_always_commit
            # remove what is left and/or everything upon failure
            earchive.clean(force=True)

        return annex
