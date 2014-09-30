#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*- 
#ex: set sts=4 ts=4 sw=4 noet:
"""Various handlers/functionality for different types of files (e.g. for archives)

 COPYRIGHT: Yaroslav Halchenko 2013

 LICENSE: MIT

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
"""

__author__ = 'Yaroslav Halchenko'
__copyright__ = 'Copyright (c) 2013 Yaroslav Halchenko'
__license__ = 'MIT'

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
#        status, output = getstatusoutput(fullcmd)
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

