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

from os.path import join as opj, realpath, split as ops, curdir, pardir, exists, lexists, relpath, basename
from os.path import sep as opsep
from .base import Interface
from ..consts import ARCHIVES_SPECIAL_REMOTE
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone, EnsureListOf

from ..support.annexrepo import AnnexRepo
from ..support.strings import apply_replacement_rules
from ..support.stats import ActivityStats
from ..cmdline.helpers import get_repo_instance
from ..utils import getpwd, rmtree, file_basename

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
            doc="""Regular expression for filenames which to exclude from being added to annex.
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

    def __call__(self, archive, annex=None, strip_leading_dirs=False,
                 delete=False, key=False, exclude=None, rename=None, existing='fail',
                 annex_options=None, copy=False, commit=True, allow_dirty=False,
                 stats=None):
        """
        Returns
        -------
        annex
        """

        # TODO: actually I see possibly us asking user either he wants to convert
        # his git repo into annex
        if annex is None:
            annex = get_repo_instance(class_=AnnexRepo)

        # TODO: somewhat too cruel -- may be an option or smth...
        if not allow_dirty and annex.dirty:
            # already saved me once ;)
            raise RuntimeError("You better commit all the changes and untracked files first")

        # are we in a subdirectory?
        # get the path relative to the top
        # TODO: check in direct mode
        reltop = relpath(annex.path, getpwd())

        if not key:
            # we were given a file which must exist
            if not exists(archive):
                raise ValueError("Archive {} does not exist".format(archive))
            # TODO: support adding archives content from outside the annex/repo
            origin = archive
            key = annex.get_file_key(archive)
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
            key_path = annex.get_contentlocation(key) # , relative_to_top=True)
        except:
            raise RuntimeError("Content of %s seems to be N/A.  Fetch it first" % key)

        #key_path = opj(reltop, key_path)
        # now we simply need to go through every file in that archive and
        lgr.info("Adding content of the archive %s into annex %s", archive, annex)

        from datalad.customremotes.archive import AnnexArchiveCustomRemote
        # TODO: shouldn't we be able just to pass existing AnnexRepo instance?
        # TODO: whenever copy strategy is implemented, we could reuse persistent cache
        annexarchive = AnnexArchiveCustomRemote(path=annex.path, persistent_cache=False)
        # We will move extracted content so it must not exist prior running
        annexarchive.cache.allow_existing = False
        earchive = annexarchive.cache[key_path]

        # TODO: check if may be it was already added
        if ARCHIVES_SPECIAL_REMOTE not in annex.git_get_remotes():
            lgr.debug("Adding new special remote {}".format(ARCHIVES_SPECIAL_REMOTE))
            annex.annex_initremote(
                ARCHIVES_SPECIAL_REMOTE,
                ['encryption=none', 'type=external', 'externaltype=dl+archive',
                 'autoenable=true'])
        else:
            lgr.debug("Special remote {} already exists".format(ARCHIVES_SPECIAL_REMOTE))

        try:
            old_always_commit = annex.always_commit
            annex.always_commit = False

            if annex_options:
                if isinstance(annex_options, string_types):
                    annex_options = shlex.split(annex_options)

            leading_dir = earchive.get_leading_directory() if strip_leading_dirs else None
            leading_dir_len = len(leading_dir) + len(opsep) if leading_dir else 0
            stats = stats or ActivityStats()

            for extracted_file in earchive.get_extracted_files():
                stats.files += 1
                extracted_path = opj(earchive.path, extracted_file)
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

                url = annexarchive.get_file_url(archive_key=key, file=extracted_file)

                lgr.debug("mv {extracted_path} {target_file}. URL: {url}".format(**locals()))

                if lexists(target_file):
                    if existing == 'fail':
                        raise RuntimeError(
                            "File {} already exists, but new (?) file {} was instructed "
                            "to be placed there while overwrite=False".format(target_file, extracted_file))
                    elif existing == 'overwrite':
                        stats.overwritten += 1
                        # to make sure it doesn't conflict -- might have been a tree
                        rmtree(target_file)
                    else:
                        target_file_orig_ = target_file
                        if existing == 'archive-suffix':
                            target_file += '-%s' % file_basename(origin)
                        elif existing == 'numeric-suffix':
                            pass  # archive-suffix will have the same logic
                        else:
                            raise ValueError(existing)
                        # keep incrementing index in the suffix until file doesn't collide
                        suf, i = '', 0
                        while lexists(target_file + suf):
                            lgr.debug("File %s already exists" % (target_file + suf))
                            i += 1
                            suf = '.%d' % i
                        target_file += suf
                        lgr.debug("Original file %s will be saved into %s"
                                  % (target_file_orig_, target_file))
                        # TODO: should we reserve smth like
                        # stats.clobbed += 1

                if target_file != target_file_orig:
                    stats.renamed += 1

                target_path = opj(getpwd(), target_file)
                if copy:
                    raise NotImplementedError("Not yet copying from 'persistent' cache")
                else:
                    os.renames(extracted_path, target_path)

                lgr.debug("Adding %s to annex pointing to %s and with options %r",
                    target_path, url, annex_options)
                annex.annex_add(target_path, options=annex_options)

                # above action might add to git or to annex
                if annex.file_has_content(target_path):
                    # if not --  it was added to git, if in annex, it is present and output is True
                    annex.annex_addurl_to_file(target_file, url, options=['--relaxed'])
                    stats.add_annex += 1
                else:
                    lgr.debug("File {} was added to git, not adding url".format(target_file))
                    stats.add_git += 1
                # TODO: actually check if it is anyhow different from a previous version. If not
                # then it wasn't really added

                del target_file  # Done with target_file -- just to have clear end of the loop

            if delete and archive:
                lgr.debug("Removing the original archive {}".format(archive))
                # force=True since some times might still be staged and fail
                annex.git_remove(archive, force=True)

            if commit:
                annex.git_commit(
                    "Added content extracted from %s\n\n%s" % (origin, stats.as_str(mode='full'))
                )
            lgr.info("Finished adding %s: %s" % (archive, stats.as_str(mode='line')))
        finally:
            annex.always_commit = old_always_commit
            # remove what is left and/or everything upon failure
            earchive.clean()

        return annex
