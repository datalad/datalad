# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provides helper to compute digests (md5 etc) on files
"""

import sys
import hashlib

from ..utils import auto_repr

import logging
lgr = logging.getLogger('datalad.support.digests')


@auto_repr
class Digester(object):
    """Helper to compute multiple digests in one pass for a file

    Loosely based on snippet by PM 2Ring 2014.10.23
    http://unix.stackexchange.com/a/163769/55543

    Ideally we should find an efficient way to parallelize this but
    atm this one is sufficiently speedy
    """

    DEFAULT_DIGESTS = ['md5', 'sha1', 'sha256', 'sha512']

    def __init__(self, digests=None, blocksize=1<<16):
        self._digests = digests or self.DEFAULT_DIGESTS
        self._digest_funcs = [getattr(hashlib, digest) for digest in self._digests]
        self.blocksize = blocksize

    @property
    def digests(self):
        return self._digests

    def __call__(self, fpath):
        lgr.debug("Estimating digests for %s" % fpath)
        digests = [x() for x in self._digest_funcs]
        with open(fpath, 'rb') as f:
            while True:
                block = f.read(self.blocksize)
                if not block:
                    break
                [d.update(block) for d in digests]

        return {n: d.hexdigest() for n, d in zip(self.digests, digests)}