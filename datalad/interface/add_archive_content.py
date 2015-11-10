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

__docformat__ = 'restructuredtext'


import re
import os
from os.path import join as opj, realpath, split as ops, curdir, pardir, exists, lexists, relpath
from .base import Interface
from ..consts import ARCHIVES_SPECIAL_REMOTE
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone, EnsureListOf

from ..support.annexrepo import AnnexRepo
from ..support.archives import ArchivesCache
from ..cmdline.helpers import get_repo_instance
from ..utils import getpwd

from six import string_types
from six.moves.urllib.parse import urlparse


from ..log import lgr

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
        overwrite=Parameter(
            args=("-o", "--overwrite"),
            action="store_true",
            doc="""Flag to replace an existing file if new file from archive has the same name"""
        ),
        exclude=Parameter(
            args=("-e", "--exclude"),
            nargs='?',
            doc="""Regular expression for filenames which to exclude from being added to annex""",
            constraints=EnsureStr() | EnsureNone()
        ),
        rename=Parameter(
            args=("-r", "--rename"),
            nargs='?',
            doc="""Regular expressions to rename files before being added under git""",
            constraints=EnsureStr() | EnsureNone()
        ),
        key=Parameter(
            args=("--key",),
            action="store_true",
            doc="""Flag to signal if provided archive is not actually a filename on its own but an annex key"""),
        archive=Parameter(
            doc="archive file or a key (if --key option specified)",
            constraints=EnsureStr()),
        # TODO:
        # options to pass into annex, e.g. on which files go directly to git and which to annex ... bleh
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

    def __call__(self, archive, delete=False, key=False, exclude=None, rename=None, overwrite=False):
        """
        Returns
        -------
        annex
        """

        annex_options = None
        # TODO: actually I see possibly us asking user either he wants to convert
        # his git repo into annex
        annex = get_repo_instance(class_=AnnexRepo)

        # are we in subdirectory?
        # move all of this logic into a helper function with proper testing etc
        subdir = relpath(annex.path, getpwd())
        if subdir != curdir:
            raise NotImplemented("see https://github.com/datalad/datalad/issues/292")

        """
        annexpath = realpath(annex.path)
        pwdpath = realpath(getpwd())
        if annexpath < pwdpath:
            subdir = pwdpath[len(annexpath)+1:]
        elif annexpath > pwdpath:
            raise RuntimeError("magic failed: PWD of %s is shorter than of annex %s."
                               " Some unsupported yet symlinking?" % (pwdpath, annexpath))
        else:
            subdir = curdir
        """
        # but it is given relative to the top
        reltop = relpath(annex.path, getpwd())

        # TODO: somewhat too cruel -- may be an option or smth...
        if annex.dirty:
            # already saved me once ;)
            raise RuntimeError("You better commit all the changes and untracked files first")

        # print "Got ", archive, key, exclude, rename

        if not key:
            # we were given a file which must exist
            assert(exists(archive))
            key = annex.get_file_key(archive)

        if not key:
            # TODO: allow for it to be under git???  how to reference then?
            raise ValueError("Provided file is not under annex, can't operate")

        # and operate from now on the key or whereever content available "canonically"
        try:
            key_archive = annex.get_contentlocation(key)
        except:
            raise RuntimeError("Content of %s seems to be N/A.  Fetch it first" % key)

        key_archive = opj(reltop, key_archive)
        # now we simply need to go through every file in that archive and

        from datalad.customremotes.archive import AnnexArchiveCustomRemote
        # TODO: shouldn't we be able just to pass existing AnnexRepo instance?
        annexarchive = AnnexArchiveCustomRemote(path=annex.path)
        # We will move extracted content so it must not exist prior running
        annexarchive.cache.allow_existing = False
        earchive = annexarchive.cache[key_archive]

        # TODO: check if may be it was already added
        annex.annex_initremote(
            ARCHIVES_SPECIAL_REMOTE,
            ['encryption=none', 'type=external', 'externaltype=dl+archive',
             'autoenable=true'])

        try:
            for extracted_file in earchive.get_extracted_files():

                extracted_path = opj(earchive.path, extracted_file)
                target_file = extracted_file

                if exclude:
                    raise NotImplementedError
                    lgr.debug("Skipping %s since matched exclude pattern" % extracted_file)
                    continue

                if rename:
                    # tunes target_file
                    raise NotImplementedError


                if lexists(target_file) and not overwrite:
                    raise RuntimeError()

                url = annexarchive.get_file_url(archive_key=key, file=extracted_file)
                lgr.info("mv {extracted_path} {target_file}. URL: {url}".format(**locals()))
                target_path = opj(getpwd(), target_file)
                os.renames(extracted_path, target_path)
                annex.annex_add(target_path, options=annex_options)
                # fails
                #annex.annex_addurl_to_file(target_file, url)
                annex.annex_addurl_to_file(target_file, url, options=['--relaxed'])
                #annex.annex_addurl_to_file(target_path, url)
            if delete and archive:
                annex.git_remove(archive)
            # more meaningful message
            annex.git_commit("Added content from archive under key %s" % key)
        finally:
            # remove what is left and/or everything upon failure
            earchive.clean()
        return annex