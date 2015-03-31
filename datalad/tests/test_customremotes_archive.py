    # emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for customremotes archives providing dl+archive URLs handling"""

import shlex
from os import readlink
from os.path import realpath, pardir, join as opj, dirname, pathsep
from ..customremotes.base import AnnexExchangeProtocol
from ..customremotes.archive import AnnexArchiveCustomRemote
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

# both files will have the same content
#fn_inarchive = 'test.dat'
#fn_extracted = 'test2.dat'
fn_inarchive = get_most_obscure_supported_name()
fn_extracted = fn_inarchive.replace('a', 'z')
# TODO -- obscure one for the tarball itself

# TODO: with_tree ATM for archives creates this nested top directory
# matching archive name, so it will be a/d/test.dat ... we don't want that probably
@with_tree(
    tree=(('a.tar.gz', (('d', ((fn_inarchive, '123'),)),)),
          (fn_extracted, '123')
         ))
@with_tempfile()
def test_basic_scenario(d, d2):
    # We could just propagate current environ I guess to versatile our testing
    env = os.environ.copy()
    env.update({'PATH': get_bindir_PATH(),
                'DATALAD_LOGTARGET': 'stderr'})
    if os.environ.get('DATALAD_LOGLEVEL'):
        env['DATALAD_LOGLEVEL'] = os.environ.get('DATALAD_LOGLEVEL')

    r = Runner(cwd=d, env=env)

    if os.environ.get('DATALAD_PROTOCOL_REMOTE'):
        protocol = AnnexExchangeProtocol(d, 'dl+archive:')
    else:
        protocol = None


    def rok(cmd, *args, **kwargs):
        if protocol:
            protocol.write_section(cmd)
        ret = r(cmd, *args, **kwargs)
        if isinstance(ret, tuple):
            assert_false(ret[0])
        else:
            assert_false(ret)
        return ret

    annex_opts = ['--debug'] if lgr.getEffectiveLevel() <= logging.DEBUG else []

    def annex(cmd, *args, **kwargs):
        cmd = shlex.split(cmd) if isinstance(cmd, basestring) else cmd
        return rok(["git", "annex"] + annex_opts + cmd, *args, **kwargs)

    def git(cmd, *args, **kwargs):
        cmd = shlex.split(cmd) if isinstance(cmd, basestring) else cmd
        return rok(["git"] + cmd, *args, **kwargs)

    git('init')
    annex('init')
    annex('initremote annexed-archives encryption=none type=external externaltype=dl+archive')
    # We want two maximally obscure names, which are also different
    assert(fn_extracted != fn_inarchive)
    annex('add a.tar.gz')
    git('commit -m "Added tarball"')
    annex(['add', fn_extracted])
    git('commit -m "Added the load file"')

    # Operations with archive remote URL
    file_url = AnnexArchiveCustomRemote(path=d).get_file_url(
        archive_file='a.tar.gz', file='a/d/'+fn_inarchive)

    annex(['addurl', '--file',  fn_extracted, '--relaxed', file_url])
    annex(['drop', fn_extracted])

    status, (out, err) = annex(['whereis', fn_extracted], return_output=True)
    in_('-- [annexed-archives]', out)
    in_('annexed-archives: %s' % file_url, out)

    ok_broken_symlink(opj(d, fn_extracted))
    annex(['get', fn_extracted])
    #ok_(exists(readlink(opj(d, fn_extracted))))

    annex(['rmurl', fn_extracted, file_url])
    with swallow_logs() as cm:
        assert_raises(RuntimeError, annex, ['drop', fn_extracted]) # no copies
        in_("git-annex: drop: 1 failed", cm.out)

    annex(['addurl', '--file',  fn_extracted, file_url])
    annex(['drop', fn_extracted])
    annex(['get', fn_extracted])
    annex(['drop', fn_extracted]) # so we don't get from this one in next part

    # Let's create a clone and verify chain of getting file by getting the tarball
    git(['clone', d, d2], expect_stderr=True)
    # we would still need to enable manually atm that special remote for archives
    annex('enableremote annexed-archives', cwd=d2)


    ok_broken_symlink(opj(d2, 'a.tar.gz'))
    ok_broken_symlink(opj(d2, fn_extracted))
    annex(['get', fn_extracted], cwd=d2)
    ok_broken_symlink(opj(d2, fn_extracted))
    # as a result it would also fetch tarball
    ok_broken_symlink(opj(d2, 'a.tar.gz'))

    # TODO: dropurl, addurl without --relaxed, addurl to non-existing file