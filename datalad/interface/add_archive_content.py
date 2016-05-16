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

from os.path import join as opj, realpath, split as ops, curdir, pardir, exists, lexists, relpath, basename, abspath
from os.path import commonprefix
from os.path import sep as opsep
from os.path import islink
from os.path import isabs
from .base import Interface
from ..consts import ARCHIVES_SPECIAL_REMOTE
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone, EnsureListOf

from ..support.annexrepo import AnnexRepo
from ..support.strings import apply_replacement_rules
from ..support.stats import ActivityStats
from ..cmdline.helpers import get_repo_instance
from ..utils import getpwd, rmtree, file_basename
from ..utils import md5sum
from ..utils import assure_tuple_or_list

from six import string_types
from six.moves.urllib.parse import urlparse

from ..log import logging
lgr = logging.getLogger('datalad.interfaces.add_archive_content')


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
            doc="""Flag to delete original archive from the filesystem/git in current tree.
                   Note that it will be of no effect if --key is given."""),
        strip_leading_dirs=Parameter(
            args=("--strip-leading-dirs",),
            action="store_true",
            doc="""Flag to move all files directories up, from how they were stored in an archive,
                   if that one contained a number (possibly more than 1 down) single leading
                   directories."""),
        leading_dirs_depth=Parameter(
            args=("--leading-dirs-depth",),
            action="store",
            type=int,
            doc="""Maximal depth to strip leading directories to. If not specified (None), no limit"""),
        leading_dirs_consider=Parameter(
            args=("--leading-dirs-consider",),
            action="append",
            doc="""Regular expression(s) for directories to consider to strip away""",
            constraints=EnsureStr() | EnsureNone(),
        ),
        # TODO: add option to extract under archive's original directory. Currently would extract in curdir
        existing=Parameter(
            args=("--existing",),
            choices=('fail', 'overwrite', 'archive-suffix', 'numeric-suffix'),
            default="fail",
            doc="""What operation to perform a file from archive tries to overwrite an existing
             file with the same name. 'fail' (default) leads to RuntimeError exception.
             'overwrite' silently replaces existing file.  'archive-suffix' instructs to add
             a suffix (prefixed with a '-') matching archive name from which file gets extracted,
             and if that one present, 'numeric-suffix' is in effect in addition, when incremental
             numeric suffix (prefixed with a '.') is added until no name collision is longer detected"""
        ),
        exclude=Parameter(
            args=("-e", "--exclude"),
            action='append',
            doc="""Regular expressions for filenames which to exclude from being added to annex.
            Applied after --rename if that one is specified.  For exact matching, use anchoring.""",
            constraints=EnsureStr() | EnsureNone()
        ),
        rename=Parameter(
            args=("-r", "--rename"),
            action='append',
            doc="""Regular expressions to rename files before being added under git.
            First letter defines how to split provided string into two parts:
            Python regular expression (with groups), and replacement string.""",
            constraints=EnsureStr(min_len=2) | EnsureNone()
        ),
        annex_options=Parameter(
            args=("-o", "--annex-options"),
            doc="""Additional options to pass to git-annex""",
            constraints=EnsureStr() | EnsureNone()
        ),
        # TODO: Python only???
        annex=Parameter(
            doc="""Annex instance to use""" #,
            #constraints=EnsureStr() | EnsureNone()
        ),
        # TODO: Python only!
        stats=Parameter(
            doc="""ActivityStats instance for global tracking""",
        ),
        key=Parameter(
            args=("--key",),
            action="store_true",
            doc="""Flag to signal if provided archive is not actually a filename on its own but an annex key"""),
        copy=Parameter(
            args=("--copy",),
            action="store_true",
            doc="""Flag to copy the content of the archive instead of moving."""),
        allow_dirty=Parameter(
            args=("--allow-dirty",),
            action="store_true",
            doc="""Flag that operating on a dirty repository (uncommitted or untracked content) is Ok."""),
        commit=Parameter(
            args=("--no-commit",),
            action="store_false",
            dest="commit",
            doc="""Flag to not commit upon completion."""),
        drop_after=Parameter(
            args=("--drop-after",),
            action="store_true",
            doc="""Drop extracted files after adding to annex.""",
        ),
        delete_after=Parameter(
            args=("--remove-after",),
            action="store_true",
            doc="""Extract under a temporary directory, git-annex add, and remove after.
         To be used to "index" files within annex without actually creating corresponding
         files under git.  Note that `annex dropunused` would later remove that load."""),

        # TODO: interaction with archives cache whenever we make it persistent across runs
        archive=Parameter(
            doc="archive file or a key (if --key option specified)",
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
                 strip_leading_dirs=False, leading_dirs_depth=None, leading_dirs_consider=None,
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
        if annex is None:
            annex = get_repo_instance(class_=AnnexRepo)
            if not isabs(archive):
                # if not absolute -- relative to curdir and thus
                archive_path = relpath(abspath(archive), annex.path)
        elif not isabs(archive):
            # if we are given an annex, then assume that given path is within annex, not
            # relative to PWD
            archive_path = opj(annex.path, archive)

        # TODO: somewhat too cruel -- may be an option or smth...
        if not allow_dirty and annex.dirty:
            # already saved me once ;)
            raise RuntimeError("You better commit all the changes and untracked files first")

        # are we in a subdirectory of the repository? then we should add content under that
        # subdirectory,
        # get the path relative to the repo top
        extract_relpath = relpath(getpwd(), annex.path) \
            if commonprefix([realpath(getpwd()), annex.path]) == annex.path \
            else None

        if not key:
            # we were given a file which must exist
            if not exists(opj(annex.path, archive_path)):
                raise ValueError("Archive {} does not exist".format(archive))
            # TODO: support adding archives content from outside the annex/repo
            origin = archive
            key = annex.get_file_key(archive_path)
        else:
            origin = key

        if not key:
            # TODO: allow for it to be under git???  how to reference then?
            raise NotImplementedError(
                "Provided file is not under annex.  We don't support yet adding everything "
                "straight to git"
            )

        # and operate from now on the key or whereever content available "canonically"
        try:
            key_path = annex.get_contentlocation(key)  # , relative_to_top=True)
        except:
            raise RuntimeError("Content of %s seems to be N/A.  Fetch it first" % key)

        #key_path = opj(reltop, key_path)
        # now we simply need to go through every file in that archive and
        lgr.info("Adding content of the archive %s into annex %s", archive, annex)

        from datalad.customremotes.archives import ArchiveAnnexCustomRemote
        # TODO: shouldn't we be able just to pass existing AnnexRepo instance?
        # TODO: we will use persistent cache so we could just (ab)use possibly extracted archive
        annexarchive = ArchiveAnnexCustomRemote(path=annex.path, persistent_cache=True)
        # We will move extracted content so it must not exist prior running
        annexarchive.cache.allow_existing = True
        earchive = annexarchive.cache[key_path]

        # TODO: check if may be it was already added
        if ARCHIVES_SPECIAL_REMOTE not in annex.git_get_remotes():
            lgr.debug("Adding new special remote {}".format(ARCHIVES_SPECIAL_REMOTE))
            annex.annex_initremote(
                ARCHIVES_SPECIAL_REMOTE,
                ['encryption=none', 'type=external', 'externaltype=%s' % ARCHIVES_SPECIAL_REMOTE,
                 'autoenable=true'])
        else:
            lgr.debug("Special remote {} already exists".format(ARCHIVES_SPECIAL_REMOTE))

        try:
            old_always_commit = annex.always_commit
            annex.always_commit = False
            keys_to_drop = []

            if annex_options:
                if isinstance(annex_options, string_types):
                    annex_options = shlex.split(annex_options)

            leading_dir = earchive.get_leading_directory(
                    depth=leading_dirs_depth, exclude=exclude, consider=leading_dirs_consider) \
                if strip_leading_dirs else None
            leading_dir_len = len(leading_dir) + len(opsep) if leading_dir else 0

            # we need to create a temporary directory at the top level which would later be
            # removed
            prefix_dir = basename(tempfile.mkdtemp(prefix=".datalad", dir=annex.path)) \
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

                target_file = target_file[leading_dir_len:]

                if rename:
                    target_file = apply_replacement_rules(rename, target_file)

                if exclude:
                    try:  # since we need to skip outside loop from inside loop
                        for regexp in exclude:
                            if re.search(regexp, target_file):
                                lgr.debug("Skipping {target_file} since contains {regexp} pattern".format(**locals()))
                                stats.skipped += 1
                                raise StopIteration
                    except StopIteration:
                        continue

                if prefix_dir:
                    target_file = opj(prefix_dir, target_file)

                url = annexarchive.get_file_url(archive_key=key, file=extracted_file, size=os.stat(extracted_path).st_size)

                # lgr.debug("mv {extracted_path} {target_file}. URL: {url}".format(**locals()))

                if lexists(target_file):
                    if md5sum(target_file) == md5sum(extracted_path):
                        # must be having the same content, we should just add possibly a new extra URL
                        pass
                    elif existing == 'fail':
                        raise RuntimeError(
                            "File {} already exists, but new (?) file {} was instructed "
                            "to be placed there while overwrite=False".format(target_file, extracted_file))
                    elif existing == 'overwrite':
                        stats.overwritten += 1
                        # to make sure it doesn't conflict -- might have been a tree
                        rmtree(target_file)
                    else:
                        target_file_orig_ = target_file

                        # To keep extension intact -- operate on the base of the filename
                        p, fn = os.path.split(target_file)
                        ends_with_dot = fn.endswith('.')
                        fn_base, fn_ext = file_basename(fn, return_ext=True)

                        if existing == 'archive-suffix':
                            fn_base += '-%s' % file_basename(origin)
                        elif existing == 'numeric-suffix':
                            pass  # archive-suffix will have the same logic
                        else:
                            raise ValueError(existing)
                        # keep incrementing index in the suffix until file doesn't collide
                        suf, i = '', 0
                        while True:
                            target_file_new = opj(p, fn_base + suf + ('.' if (fn_ext or ends_with_dot) else '') + fn_ext)
                            if not lexists(target_file_new):
                                break
                            lgr.debug("File %s already exists" % target_file_new)
                            i += 1
                            suf = '.%d' % i
                        target_file = target_file_new
                        lgr.debug("Original file %s will be saved into %s"
                                  % (target_file_orig_, target_file))
                        # TODO: should we reserve smth like
                        # stats.clobbed += 1

                if target_file != target_file_orig:
                    stats.renamed += 1

                #target_path = opj(getpwd(), target_file)
                if copy:
                    raise NotImplementedError("Not yet copying from 'persistent' cache")
                else:
                    # os.renames(extracted_path, target_path)
                    # addurl implementation relying on annex'es addurl below would actually copy
                    pass

                lgr.debug("Adding %s to annex pointing to %s and with options %r",
                          target_file, url, annex_options)

                target_file_gitpath = opj(extract_relpath, target_file) if extract_relpath else target_file
                out_json = annex.annex_addurl_to_file(
                    target_file_gitpath,
                    url, options=annex_options,
                    batch=True)

                if 'key' in out_json:  # annex.is_under_annex(target_file, batch=True):
                    # due to http://git-annex.branchable.com/bugs/annex_drop_is_not___34__in_effect__34___for_load_which_was___34__addurl_--batch__34__ed_but_not_yet_committed/?updated
                    # we need to maintain a list of those to be dropped files
                    if drop_after:
                        keys_to_drop.append(out_json['key'])
                    stats.add_annex += 1
                else:
                    lgr.debug("File {} was added to git, not adding url".format(target_file))
                    stats.add_git += 1

                if delete_after:
                    # forcing since it is only staged, not yet committed
                    annex.remove(target_file_gitpath, force=True)  # TODO: batch!
                    stats.removed += 1

                # # chaining 3 annex commands, 2 of which not batched -- less efficient but more bullet proof etc
                # annex.annex_add(target_path, options=annex_options)
                # # above action might add to git or to annex
                # if annex.file_has_content(target_path):
                #     # if not --  it was added to git, if in annex, it is present and output is True
                #     annex.annex_addurl_to_file(target_file, url, options=['--relaxed'], batch=True)
                #     stats.add_annex += 1
                # else:
                #     lgr.debug("File {} was added to git, not adding url".format(target_file))
                #     stats.add_git += 1
                # # TODO: actually check if it is anyhow different from a previous version. If not
                # # then it wasn't really added

                del target_file  # Done with target_file -- just to have clear end of the loop

            if delete and archive:
                lgr.debug("Removing the original archive {}".format(archive))
                # force=True since some times might still be staged and fail
                annex.remove(archive_path, force=True)

            lgr.info("Finished adding %s: %s" % (archive, stats.as_str(mode='line')))

            if outside_stats:
                outside_stats += stats
            if commit:
                commit_stats = outside_stats if outside_stats else stats
                annex.commit(
                    "Added content extracted from %s\n\n%s" % (origin, commit_stats.as_str(mode='full'))
                )
                commit_stats.reset()
        finally:
            # since we batched addurl, we should close those batched processes
            if delete_after:
                prefix_path = opj(annex.path, prefix_dir)
                if exists(prefix_path):  # probably would always be there
                    lgr.info("Removing temporary directory under which extracted files were annexed: %s",
                             prefix_path)
                    rmtree(prefix_path)

            annex.precommit()
            if keys_to_drop:
                # since we know that keys should be retrievable, we --force since no batching
                # atm and it would be expensive
                annex.annex_drop(keys_to_drop, options=['--force'], key=True)
                stats.dropped += len(keys_to_drop)
                annex.precommit()  # might need clean up etc again

            annex.always_commit = old_always_commit
            # remove what is left and/or everything upon failure
            earchive.clean(force=True)

        return annex
