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

import os
# All this should be replaced with a use of patoolib, but
# after figure out why
# https://github.com/wummel/patool/issues/2
# Fixed in 1.2 release, but there is no __version__ to assess reliably (yet)
import patoolib
import re

from os.path import join

import logging
lgr = logging.getLogger('datalad.files')

DECOMPRESSORS = {
    '\.(tar\.bz|tbz)$' : 'tar -xjvf %(file)s -C %(dir)s',
    '\.(tar\.xz)$' : 'tar -xJvf %(file)s -C %(dir)s',
    '\.(tar\.gz|tgz)$' : 'tar -xzvf %(file)s -C %(dir)s',
    '\.(zip)$' : 'unzip %(file)s -d %(dir)s',
    }


def decompress_file(file, dir, directories='strip'):
    fullcmd = None
    for ptr, cmd in DECOMPRESSORS.iteritems():
        if re.search(ptr, file):
            fullcmd = cmd % locals()
            break
#    if fullcmd is not None:
#        lgr.debug("Extracting file: %s" % fullcmd)
#        status, output = getstatusoutput(fullcmd)  # getstatusoutput is deprecated. Use cmd.Runner.run() instead.
#        if status:
#            lgr.debug("Failed to extract: status %d output %s" % (status, output))
#    else:
    #lgr.debug("Have no clue how to extract %s -- using patool" % file)
    verbosity = -1                        # silent by default
    ef_level = lgr.getEffectiveLevel() 
    if ef_level and lgr.getEffectiveLevel() <= logging.DEBUG:
        verbosity = 1
    #elif lgr.getEffectiveLevel() <= logging.INFO:
    #    verbosity = 0
    patoolib.extract_archive(file, outdir=dir, verbosity=verbosity)
    if directories == 'strip':
        _, dirs, files = os.walk(dir).next()
        if not len(files) and len(dirs) == 1:
            # move all the content under dirs[0] up 1 level
            subdir, subdirs_, files_ = os.walk(join(dir, dirs[0])).next()
            for f in subdirs_ + files_:
                os.rename(join(subdir, f), join(dir, f))
    else:
        raise NotImplementedError("Not supported %s" % directories)
    # TODO: (re)move containing directory

