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
from os.path import realpath, pardir, join as opj, dirname, pathsep
from ..customremotes.base import AnnexExchangeProtocol
from ..customremotes.archive import AnnexArchiveCustomRemote
from ..cmd import Runner
from ..support.handlerepo import HandleRepo
from ..consts import ARCHIVES_SPECIAL_REMOTE
from .utils import *


def get_bindir_PATH():
    # we will need to adjust PATH
    bindir = realpath(opj(dirname(__file__), pardir, pardir, 'bin'))
    PATH = os.environ['PATH']
    if bindir not in PATH:
        PATH = '%s%s%s' % (bindir, pathsep, PATH)
        lgr.log(5, "Adjusted PATH to become {}".format(os.environ['PATH']))
    return PATH

# both files will have the same content
# fn_inarchive_obscure = 'test.dat'
# fn_extracted_obscure = 'test2.dat'
fn_inarchive_obscure = get_most_obscure_supported_name()
fn_archive_obscure = fn_inarchive_obscure.replace('a', 'b') + '.tar.gz'
fn_extracted_obscure = fn_inarchive_obscure.replace('a', 'z')

#import line_profiler
#prof = line_profiler.LineProfiler()

# TODO: with_tree ATM for archives creates this nested top directory
# matching archive name, so it will be a/d/test.dat ... we don't want that probably
@with_tree(
    tree=(('a.tar.gz', (('d', ((fn_inarchive_obscure, '123'),)),)),
          ('simple.txt', '123'),
          (fn_archive_obscure, (('d', ((fn_inarchive_obscure, '123'),)),)),
          (fn_extracted_obscure, '123')))
@with_tempfile()
#@prof
def check_basic_scenario(fn_archive, fn_extracted, direct, d, d2):
    # We could just propagate current environ I guess to versatile our testing
    env = os.environ.copy()
    env.update({'PATH': get_bindir_PATH(),
                'DATALAD_LOGTARGET': d2 + "_custom.log"})

    if os.environ.get('DATALAD_LOGLEVEL'):
        env['DATALAD_LOGLEVEL'] = os.environ.get('DATALAD_LOGLEVEL')

    if os.environ.get('DATALAD_PROTOCOL_REMOTE'):
        protocol = AnnexExchangeProtocol(d, 'dl+archive:')
    else:
        protocol = None

    r = Runner(cwd=d, env=env, protocol=protocol)

    handle = HandleRepo(d, runner=r, direct=direct)
    handle.annex_initremote(
        ARCHIVES_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=dl+archive',
         'autoenable=true'
         ])
    # We want two maximally obscure names, which are also different
    assert(fn_extracted != fn_inarchive_obscure)
    handle.add_to_annex(fn_archive, "Added tarball")
    handle.add_to_annex(fn_extracted, "Added the load file")

    # Operations with archive remote URL
    file_url = AnnexArchiveCustomRemote(path=d).get_file_url(
        archive_file=fn_archive,
        file=fn_archive.replace('.tar.gz', '') + '/d/'+fn_inarchive_obscure)

    handle.annex_addurl_to_file(fn_extracted, file_url, ['--relaxed'])
    handle.annex_drop(fn_extracted)

    list_of_remotes = handle.annex_whereis(fn_extracted)
    in_('[%s]' % ARCHIVES_SPECIAL_REMOTE, list_of_remotes)

    assert_false(handle.file_has_content(fn_extracted))
    handle.get(fn_extracted)
    assert_true(handle.file_has_content(fn_extracted))

    handle.annex_rmurl(fn_extracted, file_url)
    with swallow_logs() as cm:
        assert_raises(RuntimeError, handle.annex_drop, fn_extracted)
        in_("git-annex: drop: 1 failed", cm.out)

    handle.annex_addurl_to_file(fn_extracted, file_url)
    handle.annex_drop(fn_extracted)
    handle.get(fn_extracted)
    handle.annex_drop(fn_extracted)  # so we don't get from this one next

    # Let's create a clone and verify chain of getting file through the tarball
    cloned_handle = HandleRepo(d2, d,
                           runner=Runner(cwd=d2, env=env, protocol=protocol),
                           direct=direct)
    # we still need to enable manually atm that special remote for archives
    # cloned_handle.annex_enableremote('annexed-archives')

    assert_false(cloned_handle.file_has_content(fn_archive))
    assert_false(cloned_handle.file_has_content(fn_extracted))
    cloned_handle.get(fn_extracted)
    assert_true(cloned_handle.file_has_content(fn_extracted))
    # as a result it would also fetch tarball
    assert_true(cloned_handle.file_has_content(fn_archive))

    # TODO: dropurl, addurl without --relaxed, addurl to non-existing file
    #prof.print_stats()


def test_basic_scenario():
    yield check_basic_scenario, 'a.tar.gz', 'simple.txt', False
    if not on_windows:
        yield check_basic_scenario, 'a.tar.gz', 'simple.txt', True
    #yield check_basic_scenario, 'a.tar.gz', fn_extracted_obscure, False
    #yield check_basic_scenario, fn_archive_obscure, 'simple.txt', False
    yield check_basic_scenario, fn_archive_obscure, fn_extracted_obscure, False