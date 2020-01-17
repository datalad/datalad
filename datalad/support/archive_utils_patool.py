# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""patool based implementation for datalad.support.archives utilities"""

import patoolib
from .external_versions import external_versions
# There were issues, so let's stay consistently with recent version
assert(external_versions["patoolib"] >= "1.7")

import os
from .exceptions import MissingExternalDependency
from .path import (
    basename,
    join as opj,
    exists,
)

from datalad.utils import (
    assure_bytes,
    chpwd,
    rmdir,
)

import logging
lgr = logging.getLogger('datalad.support.archive_utils_patool')

# Monkey-patch patoolib's logging, so it logs coherently with the rest of
# datalad
import patoolib.util
#
# Seems have managed with swallow_outputs
#
# def _patool_log(level, msg):
#     lgr.log(level, "patool: %s" % msg)
#
# def _patool_log_info(msg, *args, **kwargs):
#     _patool_log(logging.DEBUG, msg)
#
# def _patool_log_error(msg, *args, **kwargs):
#     _patool_log(logging.ERROR, msg)
#
# patoolib.util.log_info = _patool_log_info
# patoolib.util.log_error = _patool_log_error
# patoolib.util.log_internal_error = _patool_log_error

# we need to decorate patool.util.run
# because otherwise it just lets processes to spit out everything to std and we
# do want to use it at "verbosity>=0" so we could get idea on what is going on.
# And I don't want to mock for every invocation
from ..support.exceptions import CommandError
from ..utils import swallow_outputs
from ..cmd import Runner
from ..utils import assure_unicode

from ..utils import on_windows

_runner = Runner()


def _patool_run(cmd, verbosity=0, **kwargs):
    """Decorated runner for patool so it doesn't spit out outputs to stdout"""
    # use our runner
    try:
        # kwargs_ = kwargs[:];         kwargs_['shell'] = True
        # Any debug/progress output could be spit out to stderr so let's
        # "expect" it.
        #
        if isinstance(cmd, (list, tuple)) and kwargs.get('shell'):
            # patool (as far as I see it) takes care about quoting args
            cmd = ' '.join(cmd)
        out, err = _runner.run(cmd,
                    #log_stdout='offline',
                    #log_stderr='offline',
                    #expect_stderr=True,
                    #stdin=open('/dev/null'),
                    **kwargs)
        lgr.debug("Finished running for patool. stdout=%s, stderr=%s", out, err)
        return 0
    except CommandError as e:
        return e.code
    except Exception as e:
        lgr.error("While invoking runner caught unexpected exception: %s" % e)
        return 100  # unknown beast
patoolib.util.run = _patool_run


# yoh: only keys are used atm, logic in decompress_file is replaced to use
# patool

DECOMPRESSORS = {
    r'\.(tar\.bz|tbz)$': 'tar -xjvf %(file)s -C %(dir)s',
    r'\.(tar\.xz)$': 'tar -xJvf %(file)s -C %(dir)s',
    r'\.(tar\.gz|tgz)$': 'tar -xzvf %(file)s -C %(dir)s',
    r'\.(zip)$': 'unzip %(file)s -d %(dir)s',
}


def unixify_path(path):
    r"""On windows convert paths from drive:\d\file to /drive/d/file

    This overcomes problems with various cmdline tools we are to use,
    such as tar etc
    """
    if on_windows:
        drive, path_ = os.path.splitdrive(path)
        path_ = path_.split(os.sep)
        path_ = '/'.join(path_)
        if drive:
            # last one must be :
            assert(drive[-1] == ":")
            return '/%s%s' % (drive[:-1], path_)
        else:
            return path_
    else:
        return path


def decompress_file(archive, dir_):
    """Decompress `archive` into a directory `dir_`

    Parameters
    ----------
    archive: str
    dir_: str
    """
    with swallow_outputs() as cmo:
        archive = assure_bytes(archive)
        dir_ = assure_bytes(dir_)
        patoolib.util.check_existing_filename(archive)
        patoolib.util.check_existing_filename(dir_, onlyfiles=False)
        # Call protected one to avoid the checks on existence on unixified path
        outdir = unixify_path(dir_)
        # should be supplied in PY3 to avoid b''
        outdir = assure_unicode(outdir)
        archive = assure_unicode(archive)

        format_compression = patoolib.get_archive_format(archive)
        if format_compression == ('gzip', None):
            # Yarik fell into the trap of being lazy and not providing proper
            # support for .gz .xz etc "stream archivers" formats in handling
            # of archives. ATM out support for .gz relies on behavior of 7z while
            # extracting them and respecting possibly present .gz filename
            # header field.
            # See more https://github.com/datalad/datalad/pull/3176#issuecomment-466819861
            # TODO: provide proper handling of all those archives without
            # relying on any filename been stored in the header
            program = patoolib.find_archive_program(
                format_compression[0], 'extract')
            if basename(program) != '7z':
                raise MissingExternalDependency(
                    "cmd:7z",
                    msg="(Not) Funny enough but ATM we need p7zip installation "
                        "to handle .gz files extraction 'correctly'"
                )

        patoolib._extract_archive(unixify_path(archive),
                                  outdir=outdir,
                                  verbosity=100)
        if cmo.out:
            lgr.debug("patool gave stdout:\n%s" % cmo.out)
        if cmo.err:
            lgr.debug("patool gave stderr:\n%s" % cmo.err)

    # Note: (ben) Experienced issue, where extracted tarball
    # lacked execution bit of directories, leading to not being
    # able to delete them while having write permission.
    # Can't imagine a situation, where we would want to fail on
    # that kind of mess. So, to be sure set it.

    if not on_windows:
        os.chmod(dir_,
                 os.stat(dir_).st_mode |
                 os.path.stat.S_IEXEC)
        for root, dirs, files in os.walk(dir_, followlinks=False):
            for d in dirs:
                subdir = opj(root, d)
                os.chmod(subdir,
                         os.stat(subdir).st_mode |
                         os.path.stat.S_IEXEC)


def compress_files(files, archive, path=None, overwrite=True):
    """Compress `files` into an `archive` file

    Parameters
    ----------
    files : list of str
    archive : str
    path : str
      Alternative directory under which compressor will be invoked, to e.g.
      take into account relative paths of files and/or archive
    overwrite : bool
      Whether to allow overwriting the target archive file if one already exists
    """
    with swallow_outputs() as cmo:
        with chpwd(path):
            if not overwrite:
                patoolib.util.check_new_filename(archive)
            patoolib.util.check_archive_filelist(files)
            # Call protected one to avoid the checks on existence on unixified path
            patoolib._create_archive(unixify_path(archive),
                                     [unixify_path(f) for f in files],
                                     verbosity=100)
        if cmo.out:
            lgr.debug("patool gave stdout:\n%s" % cmo.out)
        if cmo.err:
            lgr.debug("patool gave stderr:\n%s" % cmo.err)
