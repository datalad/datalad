#emacs: -*- mode: python-mode; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 noet:

import os, tempfile, time
from os.path import join, exists, lexists, isdir

from StringIO import StringIO
from mock import patch
from .utils import eq_, ok_, assert_greater, \
     with_tree, with_tempfile, sorted_files, rmtree, create_archive, \
     md5sum, ok_clean_git, ok_file_under_git

from ..support.archives import decompress_file

tree_simplearchive = dict(
    tree=(
        ('simple.tar.gz', (
            ('2copy.txt', '2 load'),
            ('3.txt', '3 load'))),),
    prefix='datalad-')

# TODO: finish it up
#  - needs to establish high loglevel for our logger and dump it temporarily
#    at least to stdout
#  - below trick didn't catch patool's stdout output
@with_tree(**tree_simplearchive)
def _test_decompress_file(path):
    print "path: {}".format(path)
    outdir = join(path, 'simple-extracted')
    os.mkdir(outdir)

    with patch('sys.stdout', new_callable=StringIO) as cm:
        decompress_file(join(path, 'simple.tar.gz'), outdir)
        stdout = cm.getvalue()
    print "> %r" % stdout
    pass
