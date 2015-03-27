    # emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for customremotes archives providing dl+archive URLs handling"""

import os
from os.path import realpath, pardir, join as opj, dirname

import sys
from ..cmd import Runner
from .utils import *

def get_bindir_PATH():
    # we will need to adjust PATH
    bindir = realpath(opj(dirname(__file__), pardir, pardir, 'bin'))
    PATH = os.environ['PATH']
    if bindir not in PATH:
        PATH = '%s:%s' % (bindir, PATH)
        #lgr.debug("Adjusted PATH to become {}".format(os.environ['PATH']))
    return PATH

def teardown_module():
    pass # may be cleanup PATH

@with_tree(
    tree=(('d.tar.gz', (('d', (('test.dat', '123'),)),)),
          ('test2.dat', '123')
         ))
def test_basic_scenario(d):
    r = Runner(cwd=d, env={'PATH': get_bindir_PATH()})

    def rok(cmd, *args, **kwargs):
        ret = r(cmd, *args, **kwargs)
        if isinstance(ret, tuple):
            assert_false(ret[0])
        else:
            assert_false(ret)
        return ret

    rok('git init; git annex init;')
    rok('git annex initremote annexed-archives encryption=none type=external externaltype=dl+archive')
    rok('git annex add d.tar.gz')
    rok('git commit -m "Added tarball"')
    exitcode, (out, err) = rok('git annex lookupkey d.tar.gz', return_output=True)
    rok('git annex add test2.dat')
    rok('git commit -m "Added the load file"')
    rok('git annex --debug addurl --file test2.dat dl+archive:%s/d/test.dat' % out.rstrip())
    rok('git annex drop test2.dat') # TODO: should not require --force
    rok('git annex --debug get test2.dat')