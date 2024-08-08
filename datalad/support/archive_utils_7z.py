# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""7-zip based implementation for datalad.support.archives utilities"""


from datalad.support.external_versions import external_versions

external_versions.check(
    "cmd:7z",
    msg='The 7z binary (7-Zip) is required for archive handling, but is missing. '
        "Setting the config flag 'datalad.runtime.use-patool' enables an "
        "alternative implementation that may not need 7z.")

import logging

from datalad.utils import (
    Path,
    join_cmdline,
    quote_cmdlinearg,
)

lgr = logging.getLogger('datalad.support.archive_utils_7z')

from datalad.cmd import KillOutput
from datalad.cmd import WitlessRunner as Runner


def _normalize_fname_suffixes(suffixes):
    if suffixes == ['.tgz']:
        suffixes = ['.tar', '.gz']
    elif suffixes == ['.tbz2']:
        suffixes = ['.tar', '.bzip2']
    return suffixes


def decompress_file(archive, dir_):
    """Decompress `archive` into a directory `dir_`

    This is an alternative implementation without patool, but directly calling 7z.

    Parameters
    ----------
    archive: str
    dir_: str
    """
    apath = Path(archive)
    runner = Runner(cwd=dir_)
    suffixes = _normalize_fname_suffixes(apath.suffixes)
    if len(suffixes) > 1 and suffixes[-2] == '.tar':
        # we have a compressed tar file that needs to be fed through the
        # decompressor first
        cmd = '7z x {} -so | 7z x -si -ttar'.format(quote_cmdlinearg(archive))
    else:
        # fire and forget
        cmd = ['7z', 'x', archive]
    runner.run(cmd, protocol=KillOutput)


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
    runner = Runner(cwd=path)
    apath = Path(archive)
    if apath.exists():
        if overwrite:
            apath.unlink()
        else:
            raise ValueError(
                'Target archive {} already exists and overwrite is forbidden'.format(
                    apath)
            )
    suffixes = _normalize_fname_suffixes(apath.suffixes)
    if len(suffixes) > 1 and suffixes[-2] == '.tar':
        cmd = '7z u .tar -so -- {} | 7z u -si -- {}'.format(
            join_cmdline(files),
            quote_cmdlinearg(str(apath)),
        )
    else:
        cmd = ['7z', 'u', str(apath), '--'] + files
    runner.run(cmd, protocol=KillOutput)
