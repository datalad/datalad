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
from os.path import realpath, pardir, join as opj, dirname, pathsep

import logging
import sys
from ..cmd import Runner
from .utils import *


def get_bindir_PATH():
    # we will need to adjust PATH
    bindir = realpath(opj(dirname(__file__), pardir, pardir, 'bin'))
    PATH = os.environ['PATH']
    if bindir not in PATH:
        PATH = '%s%s%s' % (bindir, pathsep, PATH)
        #lgr.debug("Adjusted PATH to become {}".format(os.environ['PATH']))
    return PATH


# TODO: with_tree ATM for archives creates this nested top directory
# matching archive name, so it will be a/d/test.dat ... we don't want that probably
@with_tree(
    tree=(('a.tar.gz', (('d', (('test.dat', '123'),)),)),
          ('test2.dat', '123')
         ))
def test_basic_scenario(d):
    # We could just propagate current environ I guess to versatile our testing
    env = os.environ.copy()
    env.update({'PATH': get_bindir_PATH(),
                'DATALAD_LOGTARGET': 'stderr'})
    if os.environ.get('DATALAD_LOGLEVEL'):
        env['DATALAD_LOGLEVEL'] = os.environ.get('DATALAD_LOGLEVEL')

    r = Runner(cwd=d, env=env)

    def rok(cmd, *args, **kwargs):
        ret = r(cmd, *args, **kwargs)
        if isinstance(ret, tuple):
            assert_false(ret[0])
        else:
            assert_false(ret)
        return ret

    annex_opts = ' --debug' if lgr.getEffectiveLevel() <= logging.DEBUG else ""

    def annex(cmd, *args, **kwargs):
        return rok("git annex%s %s" % (annex_opts, cmd), *args, **kwargs)

    def git(cmd, *args, **kwargs):
        return rok("git %s" % (cmd), *args, **kwargs)

    git('init')
    annex('init')
    annex('initremote annexed-archives encryption=none type=external externaltype=dl+archive')
    annex('add a.tar.gz')
    git('commit -m "Added tarball"')
    exitcode, (out, err) = \
        annex('lookupkey a.tar.gz', return_output=True)
    annex('add test2.dat')
    git('commit -m "Added the load file"')
    annex('addurl --file test2.dat --relaxed dl+archive:%s/a/d/test.dat' % (out.rstrip()))
    annex('drop test2.dat')
    annex('get test2.dat')