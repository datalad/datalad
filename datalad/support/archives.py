# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Various handlers/functionality for different types of files (e.g. for archives)

"""

from distutils.version import StrictVersion
import patoolib
# There were issues, so let's stay consistently with recent version
assert(StrictVersion(patoolib.__version__) >= "1.7")

import os
from os.path import join as opj, exists

import logging
lgr = logging.getLogger('datalad.files')

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


def _patool_run(cmd, verbosity=0, **kwargs):
    """Decorated runner for patool so it doesn't spit out outputs to stdout"""
    # use our runner
    from ..cmd import Runner
    runner = Runner()
    try:
        runner.run(cmd, **kwargs)
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
    '\.(tar\.bz|tbz)$': 'tar -xjvf %(file)s -C %(dir)s',
    '\.(tar\.xz)$': 'tar -xJvf %(file)s -C %(dir)s',
    '\.(tar\.gz|tgz)$': 'tar -xzvf %(file)s -C %(dir)s',
    '\.(zip)$': 'unzip %(file)s -d %(dir)s',
    }


def decompress_file(file_, dir_, leading_directories='strip'):
    """Decompress `file_` into a directory `dir_`

    Parameters
    ----------
    file_: str
    dir_: str
    leading_directories: {'strip', None}
    """
    if not exists(dir_):
        lgr.debug("Creating directory %s to extract archive into" % dir_)
        os.makedirs(dir_)

    from ..tests.utils import swallow_outputs
    with swallow_outputs() as cmo:
        patoolib.extract_archive(file_, outdir=dir_, verbosity=100)
        if cmo.out:
            lgr.debug("patool gave stdout:\n%s" % cmo.out)
        if cmo.err:
            lgr.debug("patool gave stderr:\n%s" % cmo.err)

    if leading_directories == 'strip':
        _, dirs, files = os.walk(dir_).next()
        if not len(files) and len(dirs) == 1:
            # move all the content under dirs[0] up 1 level
            widow_dir = opj(dir_, dirs[0])
            lgr.debug("Moving content within %s upstairs" % widow_dir)
            subdir, subdirs_, files_ = os.walk(opj(dir_, dirs[0])).next()
            for f in subdirs_ + files_:
                os.rename(opj(subdir, f), opj(dir_, f))
            os.rmdir(widow_dir)
    elif leading_directories is None:
        pass   # really do nothing
    else:
        raise NotImplementedError("Not supported %s" % leading_directories)

