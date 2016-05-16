# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for customremotes archives providing dl+archive URLs handling"""

from ..archives import ArchiveAnnexCustomRemote
from ...support.annexrepo import AnnexRepo
from ...consts import ARCHIVES_SPECIAL_REMOTE
from ...tests.utils import *

from . import _get_custom_runner

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
def check_basic_scenario(fn_archive, fn_extracted, direct, d, d2):
    annex = AnnexRepo(d, runner=_get_custom_runner(d), direct=direct)
    annex.annex_initremote(
        ARCHIVES_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % ARCHIVES_SPECIAL_REMOTE,
         'autoenable=true'
         ])
    # We want two maximally obscure names, which are also different
    assert(fn_extracted != fn_inarchive_obscure)
    annex.add_to_annex(fn_archive, "Added tarball")
    annex.add_to_annex(fn_extracted, "Added the load file")

    # Operations with archive remote URL
    annexcr = ArchiveAnnexCustomRemote(path=d)
    # few quick tests for get_file_url

    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat"), "dl+archive:xyz/a.dat")
    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat", size=999), "dl+archive:xyz/a.dat#size=999")

    eq_(annexcr._parse_url("dl+archive:xyz/a.dat#size=999"), ("xyz", "a.dat", {'size': 999}))
    eq_(annexcr._parse_url("dl+archive:xyz/a.dat"), ("xyz", "a.dat", {}))  # old format without size

    file_url = annexcr.get_file_url(
        archive_file=fn_archive,
        file=fn_archive.replace('.tar.gz', '') + '/d/'+fn_inarchive_obscure)

    annex.annex_addurl_to_file(fn_extracted, file_url, ['--relaxed'])
    annex.annex_drop(fn_extracted)

    list_of_remotes = annex.annex_whereis(fn_extracted, output='descriptions')
    in_('[%s]' % ARCHIVES_SPECIAL_REMOTE, list_of_remotes)

    assert_false(annex.file_has_content(fn_extracted))
    annex.get(fn_extracted)
    assert_true(annex.file_has_content(fn_extracted))

    annex.annex_rmurl(fn_extracted, file_url)
    with swallow_logs() as cm:
        assert_raises(RuntimeError, annex.annex_drop, fn_extracted)
        in_("git-annex: drop: 1 failed", cm.out)

    annex.annex_addurl_to_file(fn_extracted, file_url)
    annex.annex_drop(fn_extracted)
    annex.get(fn_extracted)
    annex.annex_drop(fn_extracted)  # so we don't get from this one next

    # Let's create a clone and verify chain of getting file through the tarball
    cloned_annex = AnnexRepo(d2, d,
                           runner=_get_custom_runner(d2),
                           direct=direct)
    # we still need to enable manually atm that special remote for archives
    # cloned_annex.annex_enableremote('annexed-archives')

    assert_false(cloned_annex.file_has_content(fn_archive))
    assert_false(cloned_annex.file_has_content(fn_extracted))
    cloned_annex.get(fn_extracted)
    assert_true(cloned_annex.file_has_content(fn_extracted))
    # as a result it would also fetch tarball
    assert_true(cloned_annex.file_has_content(fn_archive))

    # verify that we can drop if original archive gets dropped but available online:
    #  -- done as part of the test_add_archive_content.py
    # verify that we can't drop a file if archive key was dropped and online archive was removed or changed size! ;)


def test_basic_scenario():
    yield check_basic_scenario, 'a.tar.gz', 'simple.txt', False
    if not on_windows:
        yield check_basic_scenario, 'a.tar.gz', 'simple.txt', True
    #yield check_basic_scenario, 'a.tar.gz', fn_extracted_obscure, False
    #yield check_basic_scenario, fn_archive_obscure, 'simple.txt', False
    yield check_basic_scenario, fn_archive_obscure, fn_extracted_obscure, False


def test_no_rdflib_loaded():
    # rely on rdflib polluting stdout to see that it is not loaded whenever we load this remote
    # since that adds 300ms delay for no immediate use
    from ...cmd import Runner
    runner = Runner()
    with swallow_outputs() as cmo:
        runner.run([sys.executable, '-c', 'import datalad.customremotes.archives, sys; print([k for k in sys.modules if k.startswith("rdflib")])'],
               log_stdout=False, log_stderr=False)
        # print cmo.out
        assert_not_in("rdflib", cmo.out)
        assert_not_in("rdflib", cmo.err)
