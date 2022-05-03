# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for customremotes archives providing dl+archive URLs handling"""

import glob
import logging
import os
import os.path as op
import sys
from time import sleep
from unittest.mock import patch

from datalad.api import Dataset
from datalad.cmd import (
    GitWitlessRunner,
    KillOutput,
    StdOutErrCapture,
    WitlessRunner,
)
from datalad.support.exceptions import CommandError

from ...consts import ARCHIVES_SPECIAL_REMOTE
from ...support.annexrepo import AnnexRepo
from ...tests.test_archives import (
    fn_archive_obscure,
    fn_archive_obscure_ext,
    fn_in_archive_obscure,
)
from ...tests.utils_pytest import (
    abspath,
    assert_equal,
    assert_false,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_true,
    chpwd,
    eq_,
    in_,
    known_failure_githubci_win,
    ok_,
    serve_path_via_http,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from ...utils import unlink
from ..archives import (
    ArchiveAnnexCustomRemote,
    link_file_load,
)


# TODO: with_tree ATM for archives creates this nested top directory
# matching archive name, so it will be a/d/test.dat ... we don't want that probably
@known_failure_githubci_win
@with_tree(
    tree=(('a.tar.gz', {'d': {fn_in_archive_obscure: '123'}}),
          ('simple.txt', '123'),
          (fn_archive_obscure_ext, (('d', ((fn_in_archive_obscure, '123'),)),)),
          (fn_archive_obscure, '123')))
@with_tempfile()
def test_basic_scenario(d=None, d2=None):
    fn_archive, fn_extracted = fn_archive_obscure_ext, fn_archive_obscure
    annex = AnnexRepo(d, backend='MD5E')
    annex.init_remote(
        ARCHIVES_SPECIAL_REMOTE,
        ['encryption=none', 'type=external', 'externaltype=%s' % ARCHIVES_SPECIAL_REMOTE,
         'autoenable=true'
         ])
    assert annex.is_special_annex_remote(ARCHIVES_SPECIAL_REMOTE)
    # We want two maximally obscure names, which are also different
    assert(fn_extracted != fn_in_archive_obscure)
    annex.add(fn_archive)
    annex.commit(msg="Added tarball")
    annex.add(fn_extracted)
    annex.commit(msg="Added the load file")

    # Operations with archive remote URL
    # this is not using this class for its actual purpose
    # being a special remote implementation
    # likely all this functionality should be elsewhere
    annexcr = ArchiveAnnexCustomRemote(annex=None, path=d)
    # few quick tests for get_file_url

    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat"), "dl+archive:xyz#path=a.dat")
    eq_(annexcr.get_file_url(archive_key="xyz", file="a.dat", size=999), "dl+archive:xyz#path=a.dat&size=999")

    # see https://github.com/datalad/datalad/issues/441#issuecomment-223376906
    # old style
    eq_(annexcr._parse_url("dl+archive:xyz/a.dat#size=999"), ("xyz", "a.dat", {'size': 999}))
    eq_(annexcr._parse_url("dl+archive:xyz/a.dat"), ("xyz", "a.dat", {}))  # old format without size
    # new style
    eq_(annexcr._parse_url("dl+archive:xyz#path=a.dat&size=999"), ("xyz", "a.dat", {'size': 999}))
    eq_(annexcr._parse_url("dl+archive:xyz#path=a.dat"), ("xyz", "a.dat", {}))  # old format without size

    file_url = annexcr.get_file_url(
        archive_file=fn_archive,
        file=fn_archive.replace('.tar.gz', '') + '/d/' + fn_in_archive_obscure)

    annex.add_url_to_file(fn_extracted, file_url, ['--relaxed'])
    annex.drop(fn_extracted)

    list_of_remotes = annex.whereis(fn_extracted, output='descriptions')
    in_('[%s]' % ARCHIVES_SPECIAL_REMOTE, list_of_remotes)

    assert_false(annex.file_has_content(fn_extracted))

    with swallow_logs(new_level=logging.INFO) as cml:
        annex.get(fn_extracted)
        # Hint users to the extraction cache (and to datalad clean)
        cml.assert_logged(msg="datalad-archives special remote is using an "
                              "extraction", level="INFO", regex=False)
    assert_true(annex.file_has_content(fn_extracted))

    annex.rm_url(fn_extracted, file_url)
    assert_raises(CommandError, annex.drop, fn_extracted)

    annex.add_url_to_file(fn_extracted, file_url)
    annex.drop(fn_extracted)
    annex.get(fn_extracted)
    annex.drop(fn_extracted)  # so we don't get from this one next

    # Let's create a clone and verify chain of getting file through the tarball
    cloned_annex = AnnexRepo.clone(d, d2)
    # we still need to enable manually atm that special remote for archives
    # cloned_annex.enable_remote('annexed-archives')

    assert_false(cloned_annex.file_has_content(fn_archive))
    assert_false(cloned_annex.file_has_content(fn_extracted))
    cloned_annex.get(fn_extracted)
    assert_true(cloned_annex.file_has_content(fn_extracted))
    # as a result it would also fetch tarball
    assert_true(cloned_annex.file_has_content(fn_archive))

    # verify that we can drop if original archive gets dropped but available online:
    #  -- done as part of the test_add_archive_content.py
    # verify that we can't drop a file if archive key was dropped and online archive was removed or changed size! ;)


@known_failure_githubci_win
@with_tree(
    tree={'a.tar.gz': {'d': {fn_in_archive_obscure: '123'}}}
)
def test_annex_get_from_subdir(topdir=None):
    ds = Dataset(topdir)
    ds.create(force=True)
    ds.save('a.tar.gz')
    ds.add_archive_content('a.tar.gz', delete=True)
    fpath = op.join(topdir, 'a', 'd', fn_in_archive_obscure)

    with chpwd(op.join(topdir, 'a', 'd')):
        runner = WitlessRunner()
        runner.run(
            ['git', 'annex', 'drop', '--', fn_in_archive_obscure],
            protocol=KillOutput)  # run git annex drop
        assert_false(ds.repo.file_has_content(fpath))             # and verify if file deleted from directory
        runner.run(
            ['git', 'annex', 'get', '--', fn_in_archive_obscure],
            protocol=KillOutput)   # run git annex get
        assert_true(ds.repo.file_has_content(fpath))              # and verify if file got into directory


def test_get_git_environ_adjusted():
    gitrunner = GitWitlessRunner()
    env = {"GIT_DIR": "../../.git", "GIT_WORK_TREE": "../../", "TEST_VAR": "Exists"}

    # test conversion of relevant env vars from relative_path to correct absolute_path
    adj_env = gitrunner.get_git_environ_adjusted(env)
    assert_equal(adj_env["GIT_DIR"], abspath(env["GIT_DIR"]))
    assert_equal(adj_env["GIT_WORK_TREE"], abspath(env["GIT_WORK_TREE"]))

    # test if other environment variables passed to function returned unaltered
    assert_equal(adj_env["TEST_VAR"], env["TEST_VAR"])

    # test import of sys_env if no environment passed to function
    with patch.dict('os.environ', {'BOGUS': '123'}):
        sys_env = gitrunner.get_git_environ_adjusted()
        assert_equal(sys_env["BOGUS"], "123")


def test_no_rdflib_loaded():
    # rely on rdflib polluting stdout to see that it is not loaded whenever we load this remote
    # since that adds 300ms delay for no immediate use
    runner = WitlessRunner()
    out = runner.run(
        [sys.executable,
         '-c',
         'import datalad.customremotes.archives, sys; '
         'print([k for k in sys.modules if k.startswith("rdflib")])'],
        protocol=StdOutErrCapture)
    # print cmo.out
    assert_not_in("rdflib", out['stdout'])
    assert_not_in("rdflib", out['stderr'])


@with_tree(tree=
    {'1.tar.gz':
         {
             'bu.dat': '52055957098986598349795121365535' * 10000,
             'bu3.dat': '8236397048205454767887168342849275422' * 10000
          },
    '2.tar.gz':
         {
             'bu2.dat': '17470674346319559612580175475351973007892815102' * 10000
          },
    }
)
@serve_path_via_http()
@with_tempfile
def check_observe_tqdm(topdir=None, topurl=None, outdir=None):
    # just a helper to enable/use when want quickly to get some
    # repository with archives and observe tqdm
    from datalad.api import (
        add_archive_content,
        create,
    )
    ds = create(outdir)
    for f in '1.tar.gz', '2.tar.gz':
        with chpwd(outdir):
            ds.repo.add_url_to_file(f, topurl + f)
            ds.save(f)
            add_archive_content(f, delete=True, drop_after=True)
    files = glob.glob(op.join(outdir, '*'))
    ds.drop(files) # will not drop tarballs
    ds.repo.drop([], options=['--all', '--fast'])
    ds.get(files)
    ds.repo.drop([], options=['--all', '--fast'])
    # now loop so we could play with it outside
    print(outdir)
    # import pdb; pdb.set_trace()
    while True:
        sleep(0.1)


@known_failure_githubci_win
@with_tempfile
def test_link_file_load(tempfile=None):
    tempfile2 = tempfile + '_'

    with open(tempfile, 'w') as f:
        f.write("LOAD")

    link_file_load(tempfile, tempfile2)  # this should work in general

    ok_(os.path.exists(tempfile2))

    with open(tempfile2, 'r') as f:
        assert_equal(f.read(), "LOAD")

    def inode(fname):
        with open(fname) as fd:
            return os.fstat(fd.fileno()).st_ino

    def stats(fname, times=True):
        """Return stats on the file which should have been preserved"""
        with open(fname) as fd:
            st = os.fstat(fd.fileno())
            stats = (st.st_mode, st.st_uid, st.st_gid, st.st_size)
            if times:
                return stats + (st.st_atime, st.st_mtime)
            else:
                return stats
            # despite copystat mtime is not copied. TODO
            #        st.st_mtime)

    # TODO: fix up the test to not rely on OS assumptions but rather
    # first sense filesystem about linking support.
    # For Yarik's Windows 10 VM test was failing under assumption that
    # linking is not supported at all, but I guess it does.
    if True:  # on_linux or on_osx:
        # above call should result in the hardlink
        assert_equal(inode(tempfile), inode(tempfile2))
        assert_equal(stats(tempfile), stats(tempfile2))

        # and if we mock absence of .link
        def raise_AttributeError(*args):
            raise AttributeError("TEST")

        with patch('os.link', raise_AttributeError):
            with swallow_logs(logging.WARNING) as cm:
                link_file_load(tempfile, tempfile2)  # should still work
                ok_("failed (TEST), copying file" in cm.out)

        # should be a copy (after mocked call)
        assert_not_equal(inode(tempfile), inode(tempfile2))
    with open(tempfile2, 'r') as f:
        assert_equal(f.read(), "LOAD")
    assert_equal(stats(tempfile, times=False), stats(tempfile2, times=False))
    unlink(tempfile2)  # TODO: next two with_tempfile
