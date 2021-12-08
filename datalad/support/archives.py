# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various handlers/functionality for different types of files (e.g. for archives)

"""

import hashlib
import os
import tempfile
import string
import random
import logging

from datalad.support.path import (
    join as opj,
    exists,
    abspath,
    isabs,
    normpath,
    relpath,
    pardir,
    isdir,
    sep as opsep,
)

from datalad.support.locking import lock_if_check_fails
from datalad.support.external_versions import external_versions
from datalad.consts import ARCHIVES_TEMP_DIR
from datalad.utils import (
    any_re_search,
    ensure_bytes,
    ensure_unicode,
    unlink,
    rmtemp,
    rmtree,
    get_tempfile_kwargs,
    on_windows,
    Path,
)
from datalad import cfg
from datalad.config import anything2bool

# fall back on patool, if requested, or 7z is not found
if (cfg.obtain('datalad.runtime.use-patool', default=False,
               valtype=anything2bool)
        or not external_versions['cmd:7z']):
    from datalad.support.archive_utils_patool import (
        decompress_file as _decompress_file,
        # other code expects this to be here
        compress_files
    )
else:
    from datalad.support.archive_utils_7z import (
        decompress_file as _decompress_file,
        # other code expects this to be here
        compress_files
    )

lgr = logging.getLogger('datalad.support.archives')


def decompress_file(archive, dir_, leading_directories='strip'):
    """Decompress `archive` into a directory `dir_`

    Parameters
    ----------
    archive: str
    dir_: str
    leading_directories: {'strip', None}
      If `strip`, and archive contains a single leading directory under which
      all content is stored, all the content will be moved one directory up
      and that leading directory will be removed.
    """
    if not exists(dir_):
        lgr.debug("Creating directory %s to extract archive into", dir_)
        os.makedirs(dir_)

    _decompress_file(archive, dir_)

    if leading_directories == 'strip':
        _, dirs, files = next(os.walk(dir_))
        if not len(files) and len(dirs) == 1:
            # move all the content under dirs[0] up 1 level
            widow_dir = opj(dir_, dirs[0])
            lgr.debug("Moving content within %s upstairs", widow_dir)
            subdir, subdirs_, files_ = next(os.walk(opj(dir_, dirs[0])))
            for f in subdirs_ + files_:
                os.rename(opj(subdir, f), opj(dir_, f))
            # NFS might hold it victim so use rmtree so it tries a few times
            rmtree(widow_dir)
    elif leading_directories is None:
        pass   # really do nothing
    else:
        raise NotImplementedError("Not supported %s" % leading_directories)


def _get_cached_filename(archive):
    """A helper to generate a filename which has original filename and additional suffix
    which wouldn't collide across files with the same name from different locations
    """
    #return "%s_%s" % (basename(archive), hashlib.md5(archive).hexdigest()[:5])
    # per se there is no reason to maintain any long original name here.
    archive_cached = hashlib.md5(ensure_bytes(str(Path(archive).resolve()))).hexdigest()[:10]
    lgr.debug("Cached directory for archive %s is %s", archive, archive_cached)
    return archive_cached


def _get_random_id(size=6, chars=string.ascii_uppercase + string.digits):
    """Return a random ID composed from digits and uppercase letters

    upper-case so we are tolerant to unlikely collisions on dummy FSs
    """
    return ''.join(random.choice(chars) for _ in range(size))


class ArchivesCache(object):
    """Cache to maintain extracted archives

    Parameters
    ----------
    toppath : str
      Top directory under .git/ of which temp directory would be created.
      If not provided -- random tempdir is used
    persistent : bool, optional
      Passed over into generated ExtractedArchives
    """
    # TODO: make caching persistent across sessions/runs, with cleanup
    # IDEA: extract under .git/annex/tmp so later on annex unused could clean it
    #       all up
    def __init__(self, toppath=None, persistent=False):
        self._toppath = toppath
        if toppath:
            path = opj(toppath, ARCHIVES_TEMP_DIR)
            if not persistent:
                tempsuffix = "-" + _get_random_id()
                lgr.debug("For non-persistent archives using %s suffix for path %s",
                          tempsuffix, path)
                path += tempsuffix
            # TODO: begging for a race condition
            if not exists(path):
                lgr.debug("Initiating clean cache for the archives under %s",
                          path)
                try:
                    self._made_path = True
                    os.makedirs(path)
                    lgr.debug("Cache initialized")
                except Exception:
                    lgr.error("Failed to initialize cached under %s", path)
                    raise
            else:
                lgr.debug(
                    "Not initiating existing cache for the archives under %s",
                    path)
                self._made_path = False
        else:
            if persistent:
                raise ValueError(
                    "%s cannot be persistent, because no toppath was provided"
                    % self)
            path = tempfile.mkdtemp(**get_tempfile_kwargs())
            self._made_path = True

        self._path = path
        self.persistent = persistent
        # TODO?  ensure that it is absent or we should allow for it to persist a bit?
        #if exists(path):
        #    self._clean_cache()
        self._archives = {}

        # TODO: begging for a race condition
        if not exists(path):
            lgr.debug("Initiating clean cache for the archives under %s", self.path)
            try:
                self._made_path = True
                os.makedirs(path)
                lgr.debug("Cache initialized")
            except Exception as e:
                lgr.error("Failed to initialize cached under %s", path)
                raise
        else:
            lgr.debug("Not initiating existing cache for the archives under %s", self.path)
            self._made_path = False

    @property
    def path(self):
        return self._path

    def clean(self, force=False):
        for aname, a in list(self._archives.items()):
            a.clean(force=force)
            del self._archives[aname]
        # Probably we should not rely on _made_path and not bother if persistent removing it
        # if ((not self.persistent) or force) and self._made_path:
        #     lgr.debug("Removing the entire archives cache under %s", self.path)
        #     rmtemp(self.path)
        if (not self.persistent) or force:
            lgr.debug("Removing the entire archives cache under %s", self.path)
            rmtemp(self.path)

    def _get_normalized_archive_path(self, archive):
        """Return full path to archive

        So we have consistent operation from different subdirs,
        while referencing archives from the topdir

        TODO: why do we need it???
        """
        if not isabs(archive) and self._toppath:
            out = normpath(opj(self._toppath, archive))
            if relpath(out, self._toppath).startswith(pardir):
                raise RuntimeError("%s points outside of the topdir %s"
                                   % (archive, self._toppath))
            if isdir(out):
                raise RuntimeError("got a directory here... bleh")
            return out
        return archive

    def get_archive(self, archive):
        archive = self._get_normalized_archive_path(archive)

        if archive not in self._archives:
            self._archives[archive] = \
                ExtractedArchive(archive,
                                 opj(self.path, _get_cached_filename(archive)),
                                 persistent=self.persistent)

        return self._archives[archive]

    def __getitem__(self, archive):
        return self.get_archive(archive)

    def __delitem__(self, archive):
        archive = self._get_normalized_archive_path(archive)
        self._archives[archive].clean()
        del self._archives[archive]

    def __del__(self):
        try:
            # we can at least try
            if not self.persistent:
                self.clean()
        except:  # MIH: IOError?
            pass


class ExtractedArchive(object):
    """Container for the extracted archive
    """

    # suffix to use for a stamp so we could guarantee that extracted archive is
    STAMP_SUFFIX = '.stamp'

    def __init__(self, archive, path=None, persistent=False):
        self._archive = archive
        # TODO: bad location for extracted archive -- use tempfile
        if not path:
            path = tempfile.mktemp(**get_tempfile_kwargs(prefix=_get_cached_filename(archive)))

        if exists(path) and not persistent:
            raise RuntimeError("Directory %s already exists whenever it should not "
                               "persist" % path)
        self._persistent = persistent
        self._path = path

    def __repr__(self):
        return "%s(%r, path=%r)" % (self.__class__.__name__, self._archive, self.path)

    def clean(self, force=False):
        # would interfere with tests
        # if os.environ.get('DATALAD_TESTS_TEMP_KEEP'):
        #     lgr.info("As instructed, not cleaning up the cache under %s"
        #              % self._path)
        #     return

        for path, name in [
            (self._path, 'cache'),
            (self.stamp_path, 'stamp file')
        ]:
            if exists(path):
                if (not self._persistent) or force:
                    lgr.debug("Cleaning up the %s for %s under %s", name, self._archive, path)
                    # TODO:  we must be careful here -- to not modify permissions of files
                    #        only of directories
                    (rmtree if isdir(path) else unlink)(path)

    @property
    def path(self):
        """Given an archive -- return full path to it within cache (extracted)
        """
        return self._path

    @property
    def stamp_path(self):
        return self._path + self.STAMP_SUFFIX

    @property
    def is_extracted(self):
        return exists(self.path) and exists(self.stamp_path) \
            and os.stat(self.stamp_path).st_mtime >= os.stat(self.path).st_mtime

    def assure_extracted(self):
        """Return path to the extracted `archive`.  Extract archive if necessary
        """
        path = self.path

        with lock_if_check_fails(
            check=(lambda s: s.is_extracted, (self,)),
            lock_path=path,
            operation="extract"
        ) as (check, lock):
            if lock:
                assert not check
                self._extract_archive(path)
        return path

    def _extract_archive(self, path):
        # we need to extract the archive
        # TODO: extract to _tmp and then move in a single command so we
        # don't end up picking up broken pieces
        lgr.debug(u"Extracting {self._archive} under {path}".format(**locals()))
        if exists(path):
            lgr.debug(
                "Previous extracted (but probably not fully) cached archive "
                "found. Removing %s",
                path)
            rmtree(path)
        os.makedirs(path)
        assert (exists(path))
        # remove old stamp
        if exists(self.stamp_path):
            rmtree(self.stamp_path)
        decompress_file(self._archive, path, leading_directories=None)
        # TODO: must optional since we might to use this content, move it
        # into the tree etc
        # lgr.debug("Adjusting permissions to R/O for the extracted content")
        # rotree(path)
        assert (exists(path))
        # create a stamp
        with open(self.stamp_path, 'wb') as f:
            f.write(ensure_bytes(self._archive))
        # assert that stamp mtime is not older than archive's directory
        assert (self.is_extracted)

    # TODO: remove?
    #def has_file_ready(self, afile):
    #    lgr.debug(u"Checking file {afile} from archive {archive}".format(**locals()))
    #    return exists(self.get_extracted_filename(afile))

    def get_extracted_filename(self, afile):
        """Return full path to the `afile` within extracted `archive`

        It does not actually extract any archive
        """
        return opj(self.path, afile)

    def get_extracted_files(self):
        """Generator to provide filenames which are available under extracted archive
        """
        path = self.assure_extracted()
        path_len = len(path) + (len(os.sep) if not path.endswith(os.sep) else 0)
        for root, dirs, files in os.walk(path):  # TEMP
            for name in files:
                yield ensure_unicode(opj(root, name)[path_len:])

    def get_leading_directory(self, depth=None, consider=None, exclude=None):
        """Return leading directory of the content within archive

        Parameters
        ----------
        depth: int or None, optional
          Maximal depth of leading directories to consider.  If None - no upper
          limit
        consider : list of str, optional
          Regular expressions for file/directory names to be considered (before
          exclude). Applied to the entire relative path to the file as in the archive
        exclude: list of str, optional
          Regular expressions for file/directory names to be excluded from consideration.
          Applied to the entire relative path to the file as in the archive

        Returns
        -------
        str or None:
          If there is no single leading directory -- None returned
        """
        leading = None
        # returns only files, so no need to check if a dir or not
        for fpath in self.get_extracted_files():
            if consider and not any_re_search(consider, fpath):
                continue
            if exclude and any_re_search(exclude, fpath):
                continue

            lpath = fpath.split(opsep)
            dpath = lpath[:-1]  # directory path components
            if leading is None:
                leading = dpath if depth is None else dpath[:depth]
            else:
                if dpath[:len(leading)] != leading:
                    # find smallest common path
                    leading_ = []
                    # TODO: there might be more efficient pythonic way
                    for d1, d2 in zip(leading, dpath):
                        if d1 != d2:
                            break
                        leading_.append(d1)
                    leading = leading_
            if not len(leading):
                # no common leading - ready to exit
                return None
        return leading if leading is None else opj(*leading)

    def get_extracted_file(self, afile):
        lgr.debug(u"Requested file {afile} from archive {self._archive}".format(**locals()))
        # TODO: That could be a good place to provide "compatibility" layer if
        # filenames within archive are too obscure for local file system.
        # We could somehow adjust them while extracting and here channel back
        # "fixed" up names since they are only to point to the load
        self.assure_extracted()
        path = self.get_extracted_filename(afile)
        # TODO: make robust
        lgr.log(2, "Verifying that %s exists", abspath(path))
        assert exists(path), "%s must exist" % path
        return path

    def __del__(self):
        try:
            if self._persistent:
                self.clean()
        except Exception as e:  # MIH: IOError?
            pass
