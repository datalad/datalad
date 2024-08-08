# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class AnnexRepo

"""

import gc
import json
import logging
import os
import re
import sys
import unittest.mock
from functools import partial
from glob import glob
from os import mkdir
from os.path import (
    basename,
    curdir,
    exists,
)
from os.path import join as opj
from os.path import (
    pardir,
    relpath,
)
from queue import Queue
from shutil import copyfile
from unittest.mock import patch
from urllib.parse import (
    urljoin,
    urlsplit,
)

import pytest

from datalad import cfg as dl_cfg
from datalad.api import clone
from datalad.cmd import GitWitlessRunner
from datalad.cmd import WitlessRunner as Runner
from datalad.consts import (
    DATALAD_SPECIAL_REMOTE,
    DATALAD_SPECIAL_REMOTES_UUIDS,
    WEB_SPECIAL_REMOTE_UUID,
)
from datalad.distribution.dataset import Dataset
from datalad.runner.gitrunner import GitWitlessRunner
from datalad.support import path as op
# imports from same module:
from datalad.support.annexrepo import (
    AnnexJsonProtocol,
    AnnexRepo,
    GeneratorAnnexJsonNoStderrProtocol,
    GeneratorAnnexJsonProtocol,
)
from datalad.support.exceptions import (
    AnnexBatchCommandError,
    CommandError,
    FileInGitError,
    FileNotInAnnexError,
    FileNotInRepositoryError,
    IncompleteResultsError,
    InsufficientArgumentsError,
    MissingExternalDependency,
    OutdatedExternalDependency,
    OutOfSpaceError,
    RemoteNotAvailableError,
)
from datalad.support.external_versions import external_versions
from datalad.support.gitrepo import GitRepo
from datalad.support.sshconnector import get_connection_hash
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    OBSCURE_FILENAME,
    SkipTest,
    assert_cwd_unchanged,
)
from datalad.tests.utils_pytest import assert_dict_equal as deq_
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_false,
    assert_in,
    assert_is_instance,
    assert_not_equal,
    assert_not_in,
    assert_not_is_instance,
    assert_raises,
    assert_re_in,
    assert_repo_status,
    assert_result_count,
    assert_true,
    create_tree,
    eq_,
    find_files,
    get_most_obscure_supported_name,
    known_failure_githubci_win,
    known_failure_windows,
    maybe_adjust_repo,
    ok_,
    ok_annex_get,
    ok_file_has_content,
    ok_file_under_git,
    ok_git_config_not_empty,
    on_github,
    on_nfs,
    on_travis,
    serve_path_via_http,
    set_annex_version,
    skip_if,
    skip_if_adjusted_branch,
    skip_if_on_windows,
    skip_if_root,
    skip_nomultiplex_ssh,
    slow,
    swallow_logs,
    swallow_outputs,
    with_parametric_batch,
    with_sameas_remote,
    with_tempfile,
    with_tree,
    xfail_buggy_annex_info,
)
from datalad.utils import (
    Path,
    chpwd,
    get_linux_distribution,
    on_windows,
    quote_cmdlinearg,
    rmtree,
    unlink,
)

_GIT_ANNEX_VERSIONS_INFO = AnnexRepo.check_repository_versions()


@assert_cwd_unchanged
@with_tempfile
@with_tempfile
def test_AnnexRepo_instance_from_clone(src=None, dst=None):

    origin = AnnexRepo(src, create=True)
    ar = AnnexRepo.clone(src, dst)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise ValueError since git will notice
    # there's already a git-repo at that path and therefore can't clone to `dst`
    with swallow_logs(new_level=logging.WARN) as cm:
        assert_raises(ValueError, AnnexRepo.clone, src, dst)


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_from_existing(path=None):
    AnnexRepo(path, create=True)

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path=None):

    GitRepo(path)
    assert_raises(RuntimeError, AnnexRepo, path, create=False)

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_crippled_filesystem(dst=None):

    ar = AnnexRepo(dst)

    # fake git-annex entries in .git/config:
    ar.config.set(
        "annex.crippledfilesystem",
        'true',
        scope='local')
    ok_(ar.is_crippled_fs())
    ar.config.set(
        "annex.crippledfilesystem",
        'false',
        scope='local')
    assert_false(ar.is_crippled_fs())
    # since we can't remove the entry, just rename it to fake its absence:
    ar.config.rename_section("annex", "removed", scope='local')
    ar.config.set("annex.something", "value", scope='local')
    assert_false(ar.is_crippled_fs())


@known_failure_githubci_win
@with_tempfile
@assert_cwd_unchanged
def test_AnnexRepo_is_direct_mode(path=None):

    ar = AnnexRepo(path)
    eq_(ar.config.getbool("annex", "direct", False),
        ar.is_direct_mode())


@known_failure_githubci_win
@with_tempfile()
def test_AnnexRepo_is_direct_mode_gitrepo(path=None):
    repo = GitRepo(path, create=True)
    # artificially make .git/annex so no annex section gets initialized
    # in .git/config.  We did manage somehow to make this happen (via publish)
    # but didn't reproduce yet, so just creating manually
    mkdir(opj(repo.path, '.git', 'annex'))
    ar = AnnexRepo(path, init=False, create=False)
    # It is unlikely though that annex would be in direct mode (requires explicit)
    # annex magic, without having annex section under .git/config
    dm = ar.is_direct_mode()
    # no direct mode, ever
    assert_false(dm)


# ignore warning since we are testing that function here. Remove upon full deprecation
@pytest.mark.filterwarnings(r"ignore: AnnexRepo.get_file_key\(\) is deprecated")
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_get_file_key(annex_path=None):

    ar = AnnexRepo(annex_path)
    (ar.pathobj / 'test.dat').write_text('123\n')
    ar.save('test.dat', git=True)
    (ar.pathobj / 'test-annex.dat').write_text(
        "content to be annex-addurl'd")
    ar.save('some')

    # test-annex.dat should return the correct key:
    test_annex_key = \
        'SHA256E-s28' \
        '--2795fb26981c5a687b9bf44930cc220029223f472cea0f0b17274f4473181e7b.dat'
    eq_(ar.get_file_key("test-annex.dat"), test_annex_key)

    # and should take a list with an empty string as result, if a file wasn't
    # in annex:
    eq_(
        ar.get_file_key(["filenotpresent.wtf", "test-annex.dat"]),
        ['', test_annex_key]
    )

    # test.dat is actually in git
    # should raise Exception; also test for polymorphism
    assert_raises(IOError, ar.get_file_key, "test.dat")
    assert_raises(FileNotInAnnexError, ar.get_file_key, "test.dat")
    assert_raises(FileInGitError, ar.get_file_key, "test.dat")

    # filenotpresent.wtf doesn't even exist
    assert_raises(IOError, ar.get_file_key, "filenotpresent.wtf")

    # if we force batch mode, no failure for not present or not annexed files
    eq_(ar.get_file_key("filenotpresent.wtf", batch=True), '')
    eq_(ar.get_file_key("test.dat", batch=True), '')
    eq_(ar.get_file_key("test-annex.dat", batch=True), test_annex_key)


@with_tempfile(mkdir=True)
def test_AnnexRepo_get_outofspace(annex_path=None):
    ar = AnnexRepo(annex_path, create=True)

    def raise_cmderror(*args, **kwargs):
        raise CommandError(
            cmd="whatever",
            stderr="junk around not enough free space, need 905.6 MB more and after"
        )

    with patch.object(GitWitlessRunner, 'run_on_filelist_chunks', raise_cmderror) as cma, \
            assert_raises(OutOfSpaceError) as cme:
        ar.get("file")
    exc = cme.value
    eq_(exc.sizemore_msg, '905.6 MB')
    assert_re_in(".*annex.*(find|get).*needs 905.6 MB more", str(exc), re.DOTALL)


@with_tempfile
@with_tempfile
def test_AnnexRepo_get_remote_na(src=None, path=None):
    origin = AnnexRepo(src, create=True)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save()
    ar = AnnexRepo.clone(src, path)

    with assert_raises(RemoteNotAvailableError) as cme:
        ar.get('test-annex.dat', options=["--from=NotExistingRemote"])
    eq_(cme.value.remote, "NotExistingRemote")

    # and similar one whenever invoking with remote parameter
    with assert_raises(RemoteNotAvailableError) as cme:
        ar.get('test-annex.dat', remote="NotExistingRemote")
    eq_(cme.value.remote, "NotExistingRemote")


@with_sameas_remote
def test_annex_repo_sameas_special(repo=None):
    remotes = repo.get_special_remotes()
    eq_(len(remotes), 2)
    rsync_info = [v for v in remotes.values()
                  if v.get("sameas-name") == "r_rsync"]
    eq_(len(rsync_info), 1)
    # r_rsync is a sameas remote that points to r_dir. Its sameas-name value
    # has been copied under "name".
    eq_(rsync_info[0]["name"], rsync_info[0]["sameas-name"])


# 1 is enough to test file_has_content
@with_parametric_batch
@with_tempfile
@with_tempfile
def test_AnnexRepo_file_has_content(src=None, annex_path=None, *, batch):
    origin = AnnexRepo(src)
    (origin.pathobj / 'test.dat').write_text('123\n')
    origin.save('test.dat', git=True)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save('some')
    ar = AnnexRepo.clone(src, annex_path)
    testfiles = ["test-annex.dat", "test.dat"]

    eq_(ar.file_has_content(testfiles), [False, False])

    ok_annex_get(ar, "test-annex.dat")
    eq_(ar.file_has_content(testfiles, batch=batch), [True, False])
    eq_(ar.file_has_content(testfiles[:1], batch=batch), [True])

    eq_(ar.file_has_content(testfiles + ["bogus.txt"], batch=batch),
        [True, False, False])

    assert_false(ar.file_has_content("bogus.txt", batch=batch))
    ok_(ar.file_has_content("test-annex.dat", batch=batch))

    ar.unlock(["test-annex.dat"])
    eq_(ar.file_has_content(["test-annex.dat"], batch=batch),
        [True])
    with open(opj(annex_path, "test-annex.dat"), "a") as ofh:
        ofh.write("more")
    eq_(ar.file_has_content(["test-annex.dat"], batch=batch),
        [False])


# 1 is enough to test
@xfail_buggy_annex_info
@with_parametric_batch
@with_tempfile
@with_tempfile
def test_AnnexRepo_is_under_annex(src=None, annex_path=None, *, batch):
    origin = AnnexRepo(src)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save('some')
    ar = AnnexRepo.clone(src, annex_path)

    with open(opj(annex_path, 'not-committed.txt'), 'w') as f:
        f.write("aaa")

    testfiles = ["test-annex.dat", "not-committed.txt", "INFO.txt"]
    # wouldn't change
    target_value = [True, False, False]
    eq_(ar.is_under_annex(testfiles, batch=batch), target_value)

    ok_annex_get(ar, "test-annex.dat")
    eq_(ar.is_under_annex(testfiles, batch=batch), target_value)
    eq_(ar.is_under_annex(testfiles[:1], batch=batch), target_value[:1])
    eq_(ar.is_under_annex(testfiles[1:], batch=batch), target_value[1:])

    eq_(ar.is_under_annex(testfiles + ["bogus.txt"], batch=batch),
                 target_value + [False])

    assert_false(ar.is_under_annex("bogus.txt", batch=batch))
    ok_(ar.is_under_annex("test-annex.dat", batch=batch))

    ar.unlock(["test-annex.dat"])
    eq_(ar.is_under_annex(["test-annex.dat"], batch=batch),
        [True])
    with open(opj(annex_path, "test-annex.dat"), "a") as ofh:
        ofh.write("more")
    eq_(ar.is_under_annex(["test-annex.dat"], batch=batch),
        [False])


@xfail_buggy_annex_info
@with_tree(tree=(('about.txt', 'Lots of abouts'),
                 ('about2.txt', 'more abouts'),
                 ('d', {'sub.txt': 'more stuff'})))
@serve_path_via_http()
@with_tempfile
def test_AnnexRepo_web_remote(sitepath=None, siteurl=None, dst=None):

    ar = AnnexRepo(dst, create=True)
    testurl = urljoin(siteurl, 'about.txt')
    testurl2 = urljoin(siteurl, 'about2.txt')
    testurl3 = urljoin(siteurl, 'd/sub.txt')
    url_file_prefix = urlsplit(testurl).netloc.split(':')[0]
    testfile = '%s_about.txt' % url_file_prefix
    testfile2 = '%s_about2.txt' % url_file_prefix
    testfile3 = opj('d', 'sub.txt')

    # get the file from remote
    with swallow_outputs() as cmo:
        ar.add_url_to_file(testfile, testurl)
    l = ar.whereis(testfile)
    assert_in(WEB_SPECIAL_REMOTE_UUID, l)
    eq_(len(l), 2)
    ok_(ar.file_has_content(testfile))

    # output='full'
    lfull = ar.whereis(testfile, output='full')
    eq_(set(lfull), set(l))  # the same entries
    non_web_remote = l[1 - l.index(WEB_SPECIAL_REMOTE_UUID)]
    assert_in('urls', lfull[non_web_remote])
    eq_(lfull[non_web_remote]['urls'], [])
    assert_not_in('uuid', lfull[WEB_SPECIAL_REMOTE_UUID])  # no uuid in the records
    eq_(lfull[WEB_SPECIAL_REMOTE_UUID]['urls'], [testurl])
    assert_equal(lfull[WEB_SPECIAL_REMOTE_UUID]['description'], 'web')

    # --all and --key are incompatible
    assert_raises(CommandError, ar.whereis, [testfile], options='--all', output='full', key=True)

    # output='descriptions'
    ldesc = ar.whereis(testfile, output='descriptions')
    eq_(set(ldesc), set([v['description'] for v in lfull.values()]))

    # info w/ and w/o fast mode
    for fast in [True, False]:
        info = ar.info(testfile, fast=fast)
        eq_(info['size'], 14)
        assert(info['key'])  # that it is there
        info_batched = ar.info(testfile, batch=True, fast=fast)
        eq_(info, info_batched)
        # while at it ;)
        with swallow_outputs() as cmo:
            eq_(ar.info('nonexistent', batch=False), None)
            eq_(ar.info('nonexistent-batch', batch=True), None)
            eq_(cmo.out, '')
            eq_(cmo.err, '')
            ar.precommit()  # to stop all the batched processes for swallow_outputs

    # annex repo info
    repo_info = ar.repo_info(fast=False)
    eq_(repo_info['local annex size'], 14)
    eq_(repo_info['backend usage'], {'SHA256E': 1})
    # annex repo info in fast mode
    repo_info_fast = ar.repo_info(fast=True)
    # doesn't give much testable info, so just comparing a subset for match with repo_info info
    eq_(repo_info_fast['semitrusted repositories'], repo_info['semitrusted repositories'])
    #import pprint; pprint.pprint(repo_info)

    # remove the remote
    ar.rm_url(testfile, testurl)
    l = ar.whereis(testfile)
    assert_not_in(WEB_SPECIAL_REMOTE_UUID, l)
    eq_(len(l), 1)

    # now only 1 copy; drop should fail
    try:
        res = ar.drop(testfile)
    except CommandError as e:
        # there should be at least one result that was captured
        # TODO think about a more standard way of accessing such
        # records in a CommandError, maybe having a more specialized
        # exception derived from CommandError
        res = e.kwargs['stdout_json'][0]
        eq_(res['command'], 'drop')
        eq_(res['success'], False)
        assert_in('adjust numcopies', res['note'])

    # read the url using different method
    ar.add_url_to_file(testfile, testurl)
    l = ar.whereis(testfile)
    assert_in(WEB_SPECIAL_REMOTE_UUID, l)
    eq_(len(l), 2)
    ok_(ar.file_has_content(testfile))

    # 2 known copies now; drop should succeed
    ar.drop(testfile)
    l = ar.whereis(testfile)
    assert_in(WEB_SPECIAL_REMOTE_UUID, l)
    eq_(len(l), 1)
    assert_false(ar.file_has_content(testfile))
    lfull = ar.whereis(testfile, output='full')
    assert_not_in(non_web_remote, lfull) # not present -- so not even listed

    # multiple files/urls
    # get the file from remote
    with swallow_outputs() as cmo:
        ar.add_url_to_file(testfile2, testurl2)

    # TODO: if we ask for whereis on all files, we should get for all files
    lall = ar.whereis('.')
    eq_(len(lall), 2)
    for e in lall:
        assert(isinstance(e, list))
    # but we don't know which one for which file. need a 'full' one for that
    lall_full = ar.whereis('.', output='full')
    ok_(ar.file_has_content(testfile2))
    ok_(lall_full[testfile2][non_web_remote]['here'])
    eq_(set(lall_full), {testfile, testfile2})

    # add a bogus 2nd url to testfile

    someurl = "http://example.com/someurl"
    ar.add_url_to_file(testfile, someurl, options=['--relaxed'])
    lfull = ar.whereis(testfile, output='full')
    eq_(set(lfull[WEB_SPECIAL_REMOTE_UUID]['urls']), {testurl, someurl})

    # and now test with a file in subdirectory
    subdir = opj(dst, 'd')
    os.mkdir(subdir)
    with swallow_outputs() as cmo:
        ar.add_url_to_file(testfile3, url=testurl3)
    ok_file_has_content(opj(dst, testfile3), 'more stuff')
    eq_(set(ar.whereis(testfile3)), {WEB_SPECIAL_REMOTE_UUID, non_web_remote})
    eq_(set(ar.whereis(testfile3, output='full').keys()), {WEB_SPECIAL_REMOTE_UUID, non_web_remote})

    # and if we ask for both files
    info2 = ar.info([testfile, testfile3])
    eq_(set(info2), {testfile, testfile3})
    eq_(info2[testfile3]['size'], 10)

    full = ar.whereis([], options='--all', output='full')
    eq_(len(full.keys()), 3)  # we asked for all files -- got 3 keys
    assert_in(WEB_SPECIAL_REMOTE_UUID, full['SHA256E-s10--a978713ea759207f7a6f9ebc9eaebd1b40a69ae408410ddf544463f6d33a30e1.txt'])

    # which would work even if we cd to that subdir, but then we should use explicit curdir
    with chpwd(subdir):
        cur_subfile = opj(curdir, 'sub.txt')
        eq_(set(ar.whereis(cur_subfile)), {WEB_SPECIAL_REMOTE_UUID, non_web_remote})
        eq_(set(ar.whereis(cur_subfile, output='full').keys()), {WEB_SPECIAL_REMOTE_UUID, non_web_remote})
        testfiles = [cur_subfile, opj(pardir, testfile)]
        info2_ = ar.info(testfiles)
        # Should maintain original relative file names
        eq_(set(info2_), set(testfiles))
        eq_(info2_[cur_subfile]['size'], 10)


@with_tree(tree={"a.txt": "a",
                 "b": "b",
                 OBSCURE_FILENAME: "c",
                 "subdir": {"d": "d", "e": "e"}})
def test_find_batch_equivalence(path=None):
    ar = AnnexRepo(path)
    files = ["a.txt", "b", OBSCURE_FILENAME]
    ar.add(files + ["subdir"])
    ar.commit("add files")
    query = ["not-there"] + files
    expected = {f: f for f in files}
    expected.update({"not-there": ""})
    eq_(expected, ar.find(query, batch=True))
    eq_(expected, ar.find(query))
    # If we give a subdirectory, we split that output.
    eq_(set(ar.find(["subdir"])["subdir"]), {"subdir/d", "subdir/e"})
    eq_(ar.find(["subdir"]), ar.find(["subdir"], batch=True))
    # manually ensure that no annex batch processes are around anymore
    # that make the test cleanup break on windows.
    # story at https://github.com/datalad/datalad/issues/4190
    # even an explicit `del ar` does not get it done
    ar._batched.close()


@with_tempfile(mkdir=True)
def test_repo_info(path=None):
    repo = AnnexRepo(path)
    info = repo.repo_info()  # works in empty repo without crashing
    eq_(info['local annex size'], 0)
    eq_(info['size of annexed files in working tree'], 0)

    def get_custom(custom={}):
        """Need a helper since repo_info modifies in place so we should generate
        new each time
        """
        custom_json = {
            'available local disk space': 'unknown',
            'size of annexed files in working tree': "0",
            'success': True,
            'command': 'info',
        }
        if custom:
            custom_json.update(custom)
        return [custom_json]

    with patch.object(
            repo, '_call_annex_records',
            return_value=get_custom()):
        info = repo.repo_info()
        eq_(info['available local disk space'], None)

    with patch.object(
        repo, '_call_annex_records',
        return_value=get_custom({
            "available local disk space": "19193986496 (+100000 reserved)"})):
        info = repo.repo_info()
        eq_(info['available local disk space'], 19193986496)


@with_tempfile
@with_tempfile
def test_AnnexRepo_migrating_backends(src=None, dst=None):
    origin = AnnexRepo(src)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save('some')
    ar = AnnexRepo.clone(src, dst, backend='MD5')
    eq_(ar.default_backends, ['MD5'])
    # GitPython has a bug which causes .git/config being wiped out
    # under Python3, triggered by collecting its config instance I guess
    gc.collect()
    ok_git_config_not_empty(ar)  # Must not blow, see https://github.com/gitpython-developers/GitPython/issues/333

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    f = open(filename_abs, 'w')
    f.write("What to write?")
    f.close()

    ar.add(filename, backend='MD5')
    eq_(ar.get_file_backend(filename), 'MD5')
    eq_(ar.get_file_backend('test-annex.dat'), 'SHA256E')

    # migrating will only do, if file is present
    ok_annex_get(ar, 'test-annex.dat')

    eq_(ar.get_file_backend('test-annex.dat'), 'SHA256E')
    ar.migrate_backend('test-annex.dat')
    eq_(ar.get_file_backend('test-annex.dat'), 'MD5')

    ar.migrate_backend('', backend='SHA1')
    eq_(ar.get_file_backend(filename), 'SHA1')
    eq_(ar.get_file_backend('test-annex.dat'), 'SHA1')


tree1args = dict(
    tree=(
        ('firstfile', 'whatever'),
        ('secondfile', 'something else'),
        ('remotefile', 'pretends to be remote'),
        ('faraway', 'incredibly remote')),
)

# keys for files if above tree is generated and added to annex with MD5E backend
tree1_md5e_keys = {
    'firstfile': 'MD5E-s8--008c5926ca861023c1d2a36653fd88e2',
    'faraway': 'MD5E-s17--5b849ed02f914d3bbb5038fe4e3fead9',
    'secondfile': 'MD5E-s14--6c7ba9c5a141421e1c03cb9807c97c74',
    'remotefile': 'MD5E-s21--bf7654b3de20d5926d407ea7d913deb0'
}

# this code is only here for documentation purposes
# @with_tree(**tree1args)
# def __test_get_md5s(path):
#     # was used just to generate above dict
#     annex = AnnexRepo(path, init=True, backend='MD5E')
#     files = [basename(f) for f in find_files('.*', path)]
#     annex.add(files)
#     annex.commit()
#     print({f: p['key'] for f, p in annex.get_content_annexinfo(files)})


@with_parametric_batch
@with_tree(**tree1args)
def test_dropkey(path=None, *, batch):
    kw = {'batch': batch}
    annex = AnnexRepo(path, init=True, backend='MD5E')
    files = list(tree1_md5e_keys)
    annex.add(files)
    annex.commit()
    # drop one key
    annex.drop_key(tree1_md5e_keys[files[0]], **kw)
    # drop multiple
    annex.drop_key([tree1_md5e_keys[f] for f in files[1:3]], **kw)
    # drop already dropped -- should work as well atm
    # https://git-annex.branchable.com/bugs/dropkey_--batch_--json_--force_is_always_succesfull
    annex.drop_key(tree1_md5e_keys[files[0]], **kw)
    # and a mix with already dropped or not
    annex.drop_key(list(tree1_md5e_keys.values()), **kw)
    # AnnexRepo is not able to guarantee that all batched processes are
    # terminated when test cleanup code runs, avoid a crash (i.e. resource busy)
    annex._batched.close()


@with_tree(**tree1args)
@serve_path_via_http()
def test_AnnexRepo_backend_option(path=None, url=None):
    ar = AnnexRepo(path, backend='MD5')

    # backend recorded in .gitattributes
    eq_(ar.get_gitattributes('.')['.']['annex.backend'], 'MD5')

    ar.add('firstfile', backend='SHA1')
    ar.add('secondfile')
    eq_(ar.get_file_backend('firstfile'), 'SHA1')
    eq_(ar.get_file_backend('secondfile'), 'MD5')

    with swallow_outputs() as cmo:
        # must be added under different name since annex 20160114
        ar.add_url_to_file('remotefile2', url + 'remotefile', backend='SHA1')
    eq_(ar.get_file_backend('remotefile2'), 'SHA1')

    with swallow_outputs() as cmo:
        ar.add_url_to_file('from_faraway', url + 'faraway', backend='SHA1')
    eq_(ar.get_file_backend('from_faraway'), 'SHA1')


@with_tempfile
@with_tempfile
def test_AnnexRepo_get_file_backend(src=None, dst=None):
    origin = AnnexRepo(src, create=True)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save()

    ar = AnnexRepo.clone(src, dst)

    eq_(ar.get_file_backend('test-annex.dat'), 'SHA256E')
    # no migration
    ok_annex_get(ar, 'test-annex.dat', network=False)
    ar.migrate_backend('test-annex.dat', backend='SHA1')
    eq_(ar.get_file_backend('test-annex.dat'), 'SHA1')


@skip_if_adjusted_branch
@with_tempfile
def test_AnnexRepo_always_commit(path=None):

    repo = AnnexRepo(path)

    def get_annex_commit_counts():
        return len(repo.get_revisions("git-annex"))

    n_annex_commits_initial = get_annex_commit_counts()

    file1 = get_most_obscure_supported_name() + "_1"
    file2 = get_most_obscure_supported_name() + "_2"
    with open(opj(path, file1), 'w') as f:
        f.write("First file.")
    with open(opj(path, file2), 'w') as f:
        f.write("Second file.")

    # always_commit == True is expected to be default
    repo.add(file1)

    # Now git-annex log should show the addition:
    out_list = list(repo.call_annex_items_(['log']))
    eq_(len(out_list), 1)

    quote = lambda s: s.replace('"', r'\"')
    def assert_in_out(filename, out):
        filename_quoted = quote(filename)
        if repo._check_version_kludges('quotepath-respected') == "no":
            assert_in(filename, out)
        elif repo._check_version_kludges('quotepath-respected') == "maybe":
            assert filename in out or filename_quoted in out
        else:
            assert_in(filename_quoted, out)
    assert_in_out(file1, out_list[0])

    # check git log of git-annex branch:
    # expected: initial creation, update (by annex add) and another
    # update (by annex log)
    eq_(get_annex_commit_counts(), n_annex_commits_initial + 1)

    with patch.object(repo, "always_commit", False):
        repo.add(file2)

        # No additional git commit:
        eq_(get_annex_commit_counts(), n_annex_commits_initial + 1)

        out = repo.call_annex(['log'])

        # And we see only the file before always_commit was set to false:
        assert_in_out(file1, out)
        assert_not_in(file2, out)
        assert_not_in(quote(file2), out)

    # With always_commit back to True, do something that will trigger a commit
    # on the annex branches.
    repo.call_annex(['sync'])

    out = repo.call_annex(['log'])
    assert_in_out(file1, out)
    assert_in_out(file2, out)

    # Now git knows as well:
    eq_(get_annex_commit_counts(), n_annex_commits_initial + 2)


@with_tempfile
@with_tempfile
def test_AnnexRepo_on_uninited_annex(src=None, path=None):
    origin = AnnexRepo(src, create=True)
    (origin.pathobj / 'test-annex.dat').write_text("content")
    origin.save()
    # "Manually" clone to avoid initialization:
    runner = Runner()
    runner.run(["git", "clone", origin.path, path])

    assert_false(exists(opj(path, '.git', 'annex'))) # must not be there for this test to be valid
    annex = AnnexRepo(path, create=False, init=False)  # so we can initialize without
    # and still can get our things
    assert_false(annex.file_has_content('test-annex.dat'))
    annex.get('test-annex.dat')
    ok_(annex.file_has_content('test-annex.dat'))


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_commit(path=None):

    ds = AnnexRepo(path, create=True)
    filename = opj(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.add(filename, git=True)

    assert_raises(AssertionError, assert_repo_status, path, annex=True)

    ds.commit("test _commit")
    assert_repo_status(path, annex=True)

    # nothing to commit doesn't raise by default:
    ds.commit()
    # but does with careless=False:
    assert_raises(CommandError, ds.commit, careless=False)

    # committing untracked file raises:
    with open(opj(path, "untracked"), "w") as f:
        f.write("some")
    assert_raises(FileNotInRepositoryError, ds.commit, files="untracked")
    # not existing file as well:
    assert_raises(FileNotInRepositoryError, ds.commit, files="not-existing")


@with_tempfile
def test_AnnexRepo_add_to_annex(path=None):
    repo = AnnexRepo(path)

    assert_repo_status(repo, annex=True)
    filename = get_most_obscure_supported_name()
    filename_abs = opj(repo.path, filename)
    with open(filename_abs, "w") as f:
        f.write("some")

    out_json = repo.add(filename)
    # file is known to annex:
    ok_(repo.is_under_annex(filename_abs),
        "Annexed file is not a link.")
    assert_in('key', out_json)
    key = repo.get_file_annexinfo(filename)['key']
    assert_false(key == '')
    assert_equal(key, out_json['key'])
    ok_(repo.file_has_content(filename))

    # uncommitted:
    ok_(repo.dirty)

    repo.commit("Added file to annex.")
    assert_repo_status(repo, annex=True)

    # now using commit/msg options:
    filename = "another.txt"
    with open(opj(repo.path, filename), "w") as f:
        f.write("something else")

    repo.add(filename)
    repo.commit(msg="Added another file to annex.")
    # known to annex:
    fileprops = repo.get_file_annexinfo(filename, eval_availability=True)
    ok_(fileprops['key'])
    ok_(fileprops['has_content'])

    # and committed:
    assert_repo_status(repo, annex=True)


@with_tempfile
def test_AnnexRepo_add_to_git(path=None):
    repo = AnnexRepo(path)

    assert_repo_status(repo, annex=True)
    filename = get_most_obscure_supported_name()
    with open(opj(repo.path, filename), "w") as f:
        f.write("some")
    repo.add(filename, git=True)

    # not in annex, but in git:
    eq_(repo.get_file_annexinfo(filename), {})
    # uncommitted:
    ok_(repo.dirty)
    repo.commit("Added file to annex.")
    assert_repo_status(repo, annex=True)

    # now using commit/msg options:
    filename = "another.txt"
    with open(opj(repo.path, filename), "w") as f:
        f.write("something else")

    repo.add(filename, git=True)
    repo.commit(msg="Added another file to annex.")
    # not in annex, but in git:
    eq_(repo.get_file_annexinfo(filename), {})

    # and committed:
    assert_repo_status(repo, annex=True)


@with_tempfile
@with_tempfile
def test_AnnexRepo_get(src=None, dst=None):
    ar = AnnexRepo(src)
    (ar.pathobj / 'test-annex.dat').write_text(
        "content to be annex-addurl'd")
    ar.save('some')

    annex = AnnexRepo.clone(src, dst)
    assert_is_instance(annex, AnnexRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = opj(dst, testfile)
    assert_false(annex.file_has_content("test-annex.dat"))
    with swallow_outputs():
        annex.get(testfile)
    ok_(annex.file_has_content("test-annex.dat"))
    ok_file_has_content(testfile_abs, "content to be annex-addurl'd", strip=True)

    called = []
    # for some reason yoh failed mock to properly just call original func
    orig_run = annex._git_runner.run_on_filelist_chunks

    def check_run(cmd, files, **kwargs):
        cmd_name = cmd[cmd.index('annex') + 1]
        called.append(cmd_name)
        if cmd_name == 'find':
            assert_not_in('-J5', cmd)
        elif cmd_name == 'get':
            assert_in('-J5', cmd)
        else:
            raise AssertionError(
                "no other commands so far should be ran. Got %s" % cmd
            )
        return orig_run(cmd, files, **kwargs)

    annex.drop(testfile)
    with patch.object(GitWitlessRunner, 'run_on_filelist_chunks',
                      side_effect=check_run), \
            swallow_outputs():
        annex.get(testfile, jobs=5)
    eq_(called, ['find', 'get'])
    ok_file_has_content(testfile_abs, "content to be annex-addurl'd", strip=True)


@with_tree(tree={'file.dat': 'content'})
@with_tempfile
def test_v7_detached_get(opath=None, path=None):
    # http://git-annex.branchable.com/bugs/get_fails_to_place_v7_unlocked_file_content_into_the_file_tree_in_v7_in_repo_with_detached_HEAD/
    origin = AnnexRepo(opath, create=True, version=7)
    GitRepo.add(origin, 'file.dat')  # force direct `git add` invocation
    origin.commit('added')

    AnnexRepo.clone(opath, path)
    repo = AnnexRepo(path)
    # test getting in a detached HEAD
    repo.checkout('HEAD^{}')
    repo.call_annex(['upgrade'])  # TODO: .upgrade ?

    repo.get('file.dat')
    ok_file_has_content(op.join(repo.path, 'file.dat'), "content")


# TODO:
#def init_remote(self, name, options):
#def enable_remote(self, name):

@pytest.mark.parametrize("batch", [False, True])
@with_tempfile
@with_tempfile
@with_tempfile
def test_AnnexRepo_get_contentlocation(src=None, path=None, work_dir_outside=None, *, batch):
    ar = AnnexRepo(src)
    (ar.pathobj / 'test-annex.dat').write_text(
        "content to be annex-addurl'd")
    ar.save('some')

    annex = AnnexRepo.clone(src, path)
    fname = 'test-annex.dat'
    key = annex.get_file_annexinfo(fname)['key']
    # MIH at this point the whole test and get_contentlocation() itself
    # is somewhat moot. The above call already has properties like
    # 'hashdirmixed', 'hashdirlower', and 'key' from which the location
    # could be built.
    # with eval_availability=True, it also has 'objloc' with a absolute
    # path to a verified annex key location

    # TODO: see if we can avoid this or specify custom exception
    eq_(annex.get_contentlocation(key, batch=batch), '')

    with swallow_outputs() as cmo:
        annex.get(fname)
    key_location = annex.get_contentlocation(key, batch=batch)
    assert(key_location)

    if annex.is_managed_branch():
        # the rest of the test assumes annexed files being symlinks
        return

    # they both should point to the same location eventually
    eq_((annex.pathobj / fname).resolve(),
        (annex.pathobj / key_location).resolve())

    # test how it would look if done under a subdir of the annex:
    with chpwd(opj(annex.path, 'subdir'), mkdir=True):
        key_location = annex.get_contentlocation(key, batch=batch)
        # they both should point to the same location eventually
        eq_((annex.pathobj / fname).resolve(),
            (annex.pathobj / key_location).resolve())

    # test how it would look if done under a dir outside of the annex:
    with chpwd(work_dir_outside, mkdir=True):
        key_location = annex.get_contentlocation(key, batch=batch)
        # they both should point to the same location eventually
        eq_((annex.pathobj / fname).resolve(),
            (annex.pathobj / key_location).resolve())


@known_failure_windows
@with_tree(tree=(('about.txt', 'Lots of abouts'),
                 ('about2.txt', 'more abouts'),
                 ('about2_.txt', 'more abouts_'),
                 ('d', {'sub.txt': 'more stuff'})))
@serve_path_via_http()
@with_tempfile
def test_AnnexRepo_addurl_to_file_batched(sitepath=None, siteurl=None, dst=None):

    if dl_cfg.get('datalad.fake-dates'):
        raise SkipTest(
            "Faked dates are enabled; skipping batched addurl tests")

    ar = AnnexRepo(dst, create=True)
    testurl = urljoin(siteurl, 'about.txt')
    testurl2 = urljoin(siteurl, 'about2.txt')
    testurl2_ = urljoin(siteurl, 'about2_.txt')
    testurl3 = urljoin(siteurl, 'd/sub.txt')
    url_file_prefix = urlsplit(testurl).netloc.split(':')[0]
    testfile = 'about.txt'
    testfile2 = 'about2.txt'
    testfile2_ = 'about2_.txt'
    testfile3 = opj('d', 'sub.txt')

    # add to an existing but not committed file
    # TODO: __call__ of the BatchedAnnex must be checked to be called
    copyfile(opj(sitepath, 'about.txt'), opj(dst, testfile))
    # must crash sensibly since file exists, we shouldn't addurl to non-annexed files
    with assert_raises(AnnexBatchCommandError):
        ar.add_url_to_file(testfile, testurl, batch=True)

    # Remove it and re-add
    unlink(opj(dst, testfile))
    ar.add_url_to_file(testfile, testurl, batch=True)

    info = ar.info(testfile)
    eq_(info['size'], 14)
    assert(info['key'])
    # not even added to index yet since we this repo is with default batch_size
    assert_not_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile))

    # TODO: none of the below should re-initiate the batch process

    # add to an existing and staged annex file
    copyfile(opj(sitepath, 'about2.txt'), opj(dst, testfile2))
    ar.add(testfile2)
    ar.add_url_to_file(testfile2, testurl2, batch=True)
    assert(ar.info(testfile2))
    # not committed yet
    # assert_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile2))

    # add to an existing and committed annex file
    copyfile(opj(sitepath, 'about2_.txt'), opj(dst, testfile2_))
    ar.add(testfile2_)
    if ar.is_direct_mode():
        assert_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile))
    else:
        assert_not_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile))
    ar.commit("added about2_.txt and there was about2.txt lingering around")
    # commit causes closing all batched annexes, so testfile gets committed
    assert_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile))
    assert(not ar.dirty)
    ar.add_url_to_file(testfile2_, testurl2_, batch=True)
    assert(ar.info(testfile2_))
    assert_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(testfile2_))

    # add into a new file
    # filename = 'newfile.dat'
    filename = get_most_obscure_supported_name()

    # Note: The following line was necessary, since the test setup just
    # doesn't work with singletons
    # TODO: Singleton mechanic needs a general solution for this
    AnnexRepo._unique_instances.clear()
    ar2 = AnnexRepo(dst, batch_size=1)

    with swallow_outputs():
        eq_(len(ar2._batched), 0)
        ar2.add_url_to_file(filename, testurl, batch=True)
        eq_(len(ar2._batched), 1)  # we added one more with batch_size=1
        ar2.precommit()  # to possibly stop batch process occupying the stdout
    ar2.commit("added new file")  # would do nothing ATM, but also doesn't fail
    assert_in(filename, ar2.get_files())
    assert_in(WEB_SPECIAL_REMOTE_UUID, ar2.whereis(filename))

    ar.commit("actually committing new files")
    assert_in(filename, ar.get_files())
    assert_in(WEB_SPECIAL_REMOTE_UUID, ar.whereis(filename))
    # this poor bugger still wasn't added since we used default batch_size=0 on him

    # and closing the pipes now shouldn't anyhow affect things
    eq_(len(ar._batched), 1)
    ar._batched.close()
    eq_(len(ar._batched), 1)  # doesn't remove them, just closes
    assert(not ar.dirty)

    ar._batched.clear()
    eq_(len(ar._batched), 0)  # .clear also removes

    raise SkipTest("TODO: more, e.g. add with a custom backend")
    # TODO: also with different modes (relaxed, fast)
    # TODO: verify that file is added with that backend and that we got a new batched process


@with_tree(tree={"foo": "foo content"})
@serve_path_via_http()
@with_tree(tree={"bar": "bar content"})
def test_annexrepo_fake_dates_disables_batched(sitepath=None, siteurl=None, dst=None):
    ar = AnnexRepo(dst, create=True, fake_dates=True)

    with swallow_logs(new_level=logging.DEBUG) as cml:
        ar.add_url_to_file("foo-dst", urljoin(siteurl, "foo"), batch=True)
        cml.assert_logged(
            msg="Not batching addurl call because fake dates are enabled",
            level="DEBUG",
            regex=False)

    ar.add("bar")
    ar.commit("add bar")
    key = ar.get_content_annexinfo(["bar"]).popitem()[1]['key']

    with swallow_logs(new_level=logging.DEBUG) as cml:
        ar.drop_key(key, batch=True)
        cml.assert_logged(
            msg="Not batching drop_key call because fake dates are enabled",
            level="DEBUG",
            regex=False)


@with_tempfile(mkdir=True)
def test_annex_backends(path=None):
    path = Path(path)
    repo_default = AnnexRepo(path / "r_default")
    eq_(repo_default.default_backends, None)

    repo_kw = AnnexRepo(path / "repo_kw", backend='MD5E')
    eq_(repo_kw.default_backends, ['MD5E'])

    # persists
    repo_kw = AnnexRepo(path / "repo_kw")
    eq_(repo_kw.default_backends, ['MD5E'])

    repo_config = AnnexRepo(path / "repo_config")
    repo_config.config.set("annex.backend", "MD5E", reload=True)
    eq_(repo_config.default_backends, ["MD5E"])

    repo_compat = AnnexRepo(path / "repo_compat")
    repo_compat.config.set("annex.backends", "MD5E WORM", reload=True)
    eq_(repo_compat.default_backends, ["MD5E", "WORM"])


# ignore deprecation warnings since here we should not use high level
# interface like push
@pytest.mark.filterwarnings(r"ignore: AnnexRepo.copy_to\(\) is deprecated")
@skip_nomultiplex_ssh  # too much of "multiplex" testing
@with_tempfile(mkdir=True)
def test_annex_ssh(topdir=None):
    # On Xenial, this hangs with a recent git-annex. It bisects to git-annex's
    # 7.20191230-142-g75059c9f3. This is likely due to an interaction with an
    # older openssh version. See
    # https://git-annex.branchable.com/bugs/SSH-based_git-annex-init_hang_on_older_systems___40__Xenial__44___Jessie__41__/
    if external_versions['cmd:system-ssh'] < '7.4' and \
       external_versions['cmd:annex'] <= '8.20200720.1':
        raise SkipTest("Test known to hang")

    topdir = Path(topdir)
    rm1 = AnnexRepo(topdir / "remote1", create=True)
    rm2 = AnnexRepo.clone(rm1.path, str(topdir / "remote2"))
    rm2.remove_remote(DEFAULT_REMOTE)

    main_tmp = AnnexRepo.clone(rm1.path, str(topdir / "main"))
    main_tmp.remove_remote(DEFAULT_REMOTE)
    repo_path = main_tmp.path
    del main_tmp
    remote_1_path = rm1.path
    remote_2_path = rm2.path

    from datalad import ssh_manager

    # check whether we are the first to use these sockets:
    hash_1 = get_connection_hash('datalad-test')
    socket_1 = opj(str(ssh_manager.socket_dir), hash_1)
    hash_2 = get_connection_hash('datalad-test2')
    socket_2 = opj(str(ssh_manager.socket_dir), hash_2)
    datalad_test_was_open = exists(socket_1)
    datalad_test2_was_open = exists(socket_2)

    # repo to test:AnnexRepo(repo_path)
    # At first, directly use git to add the remote, which should be recognized
    # by AnnexRepo's constructor
    gr = GitRepo(repo_path, create=True)
    gr.add_remote("ssh-remote-1", "ssh://datalad-test" + remote_1_path)

    ar = AnnexRepo(repo_path, create=False)

    # socket was not touched:
    if datalad_test_was_open:
        ok_(exists(socket_1))
    else:
        ok_(not exists(socket_1))

    # remote interaction causes socket to be created:
    (ar.pathobj / "foo").write_text("foo")
    (ar.pathobj / "bar").write_text("bar")
    ar.add("foo")
    ar.add("bar")
    ar.commit("add files")

    ar.copy_to(["foo"], remote="ssh-remote-1")
    # copy_to() opens it if needed.
    #
    # Note: This isn't racy because datalad-sshrun should not close this itself
    # because the connection was either already open before this test or
    # copy_to(), not the underlying git-annex/datalad-sshrun call, opens it.
    ok_(exists(socket_1))

    # add another remote:
    ar.add_remote('ssh-remote-2', "ssh://datalad-test2" + remote_2_path)

    # socket was not touched:
    if datalad_test2_was_open:
        # FIXME: occasionally(?) fails in V6:
        # ok_(exists(socket_2))
        pass
    else:
        ok_(not exists(socket_2))

    # copy to the new remote:
    #
    # Same racy note as the copy_to() call above.
    ar.copy_to(["foo"], remote="ssh-remote-2")

    if not exists(socket_2):  # pragma: no cover
        # @known_failure (marked for grep)
        raise SkipTest("test_annex_ssh hit known failure (gh-4781)")

    # Check that git-annex is actually using datalad-sshrun.
    fail_cmd = quote_cmdlinearg(sys.executable) + "-c 'assert 0'"
    with patch.dict('os.environ', {'GIT_SSH_COMMAND': fail_cmd}):
        with assert_raises(CommandError):
            ar.copy_to(["bar"], remote="ssh-remote-2")
    ar.copy_to(["bar"], remote="ssh-remote-2")

    ssh_manager.close(ctrl_path=[socket_1, socket_2])


@with_tempfile
def test_annex_remove(path=None):
    ar = AnnexRepo(path)
    (ar.pathobj / 'test-annex.dat').write_text(
        "content to be annex-addurl'd")
    ar.save('some')

    repo = AnnexRepo(path, create=False)

    file_list = list(repo.get_content_annexinfo(init=None))
    assert len(file_list) >= 1
    # remove a single file
    out = repo.remove(str(file_list[0]))
    assert_not_in(file_list[0], repo.get_content_annexinfo(init=None))
    eq_(out[0], str(file_list[0].relative_to(repo.pathobj)))

    with open(opj(repo.path, "rm-test.dat"), "w") as f:
        f.write("whatever")

    # add it
    repo.add("rm-test.dat")

    # remove without '--force' should fail, due to staged changes:
    assert_raises(CommandError, repo.remove, "rm-test.dat")
    assert_in("rm-test.dat", repo.get_annexed_files())

    # now force:
    out = repo.remove("rm-test.dat", force=True)
    assert_not_in("rm-test.dat", repo.get_annexed_files())
    eq_(out[0], "rm-test.dat")


@with_tempfile
@with_tempfile
@with_tempfile
def test_repo_version_upgrade(path1=None, path2=None, path3=None):
    with swallow_logs(new_level=logging.INFO) as cm:
        # Since git-annex 7.20181031, v6 repos upgrade to v7.
        # Future proofing: We will test on v6 as long as it is upgradeable,
        # but would switch to first upgradeable after
        Uversion = 6 if 6 in _GIT_ANNEX_VERSIONS_INFO["upgradable"] \
            else _GIT_ANNEX_VERSIONS_INFO["upgradeable"][0]
        v_first_supported = next(i for i in _GIT_ANNEX_VERSIONS_INFO["supported"] if i >= Uversion)
        annex = AnnexRepo(path1, create=True, version=Uversion)
        assert_repo_status(path1, annex=True)
        v_upgraded_to = int(annex.config.get('annex.version'))

        if external_versions['cmd:annex'] <= '10.20220724':
            eq_(v_upgraded_to, v_first_supported)
            assert_in("will be upgraded to 8", cm.out)
        else:
            # 10.20220724-5-g63cef2ae0 started to auto-upgrade to 10, although 8 was the
            # lowest supported. In general we can only assert that we upgrade into one
            # of the supported
            assert_in(v_upgraded_to, _GIT_ANNEX_VERSIONS_INFO["supported"])
            assert_in("will be upgraded to %s or later version" % v_first_supported, cm.out)

    # default from config item (via env var):
    with patch.dict('os.environ', {'DATALAD_REPO_VERSION': str(Uversion)}):
        # and check consistency of upgrading to the default version:
        annex = AnnexRepo(path2, create=True)
        version = int(annex.config.get('annex.version'))
        eq_(version, v_upgraded_to)


@pytest.mark.parametrize("version", _GIT_ANNEX_VERSIONS_INFO["supported"])
def test_repo_version_supported(version, tmp_path):
        # default from config item (via env var):
        Uversion = _GIT_ANNEX_VERSIONS_INFO["upgradable"][0]
        with patch.dict('os.environ', {'DATALAD_REPO_VERSION': str(Uversion)}):
            # ...parameter `version` still has priority over default config:
            annex = AnnexRepo(str(tmp_path), create=True, version=version)
            annex_version = int(annex.config.get('annex.version'))
            if not annex.is_managed_branch():
                # There is no "upgrade" for any of the supported versions.
                # if we are not in adjusted branch
                eq_(annex_version, version)
            else:
                print("HERE")
                # some annex command might have ran to trigger the update
                assert annex_version in {v for v in _GIT_ANNEX_VERSIONS_INFO["supported"] if v >= version}


@skip_if(external_versions['cmd:annex'] > '8.20210428', "Stopped showing if too quick")
@with_tempfile
def test_init_scanning_message(path=None):
    with swallow_logs(new_level=logging.INFO) as cml:
        AnnexRepo(path, create=True, version=7)
        # somewhere around 8.20210428-186-g428c91606 git annex changed
        # handling of scanning for unlocked files upon init and started to report
        # "scanning for annexed" instead of "scanning for unlocked".
        # Could be a line among many (as on Windows) so match=False so we search
        assert_re_in(".*scanning for .* files", cml.out, flags=re.IGNORECASE, match=False)


# ignore deprecation warnings since that is the test testing that functionality
@pytest.mark.filterwarnings(r"ignore: AnnexRepo.copy_to\(\) is deprecated")
@with_tempfile
@with_tempfile
@with_tempfile
def test_annex_copy_to(src=None, origin=None, clone=None):
    ar = AnnexRepo(src)
    (ar.pathobj / 'test.dat').write_text("123\n")
    ar.save('some', git=True)
    (ar.pathobj / 'test-annex.dat').write_text("content")
    ar.save('some')

    repo = AnnexRepo.clone(src, origin)
    remote = AnnexRepo.clone(origin, clone)
    repo.add_remote("target", clone)

    assert_raises(IOError, repo.copy_to, "doesnt_exist.dat", "target")
    assert_raises(FileInGitError, repo.copy_to, "test.dat", "target")
    assert_raises(ValueError, repo.copy_to, "test-annex.dat", "invalid_target")

    # see #3102
    # "copying" a dir shouldn't do anything and not raise.
    os.mkdir(opj(repo.path, "subdir"))
    repo.copy_to("subdir", "target")

    # test-annex.dat has no content to copy yet:
    eq_(repo.copy_to("test-annex.dat", "target"), [])

    repo.get("test-annex.dat")
    # now it has:
    eq_(repo.copy_to("test-annex.dat", "target"), ["test-annex.dat"])
    # and will not be copied again since it was already copied
    eq_(repo.copy_to(["test.dat", "test-annex.dat"], "target"), [])

    # Test that if we pass a list of items and annex processes them nicely,
    # we would obtain a list back. To not stress our tests even more -- let's mock
    def ok_copy(command, **kwargs):
        # Check that we do pass to annex call only the list of files which we
        #  asked to be copied
        assert_in('copied1', kwargs['files'])
        assert_in('copied2', kwargs['files'])
        assert_in('existed', kwargs['files'])
        return [
                {"command":"copy","note":"to target ...", "success":True,
                 "key":"akey1", "file":"copied1"},
                {"command":"copy","note":"to target ...", "success":True,
                 "key":"akey2", "file":"copied2"},
                {"command":"copy","note":"checking target ...", "success":True,
                 "key":"akey3", "file":"existed"},
        ]
    # Note that we patch _call_annex_records,
    # which is in turn invoked first by copy_to for "find" operation.
    # TODO: provide a dedicated handling within above ok_copy for 'find' command
    with patch.object(repo, '_call_annex_records', ok_copy):
        eq_(repo.copy_to(["copied2", "copied1", "existed"], "target"),
            ["copied1", "copied2"])

    # now let's test that we are correctly raising the exception in case if
    # git-annex execution fails
    orig_run = repo._call_annex

    # Kinda a bit off the reality since no nonex* would not be returned/handled
    # by _get_expected_files, so in real life -- wouldn't get report about Incomplete!?
    def fail_to_copy(command, **kwargs):
        if command[0] == 'copy':
            # That is not how annex behaves
            # http://git-annex.branchable.com/bugs/copy_does_not_reflect_some_failed_copies_in_--json_output/
            # for non-existing files output goes into stderr
            #
            # stderr output depends on config+version of annex, though:
            if not dl_cfg.getbool(
                    section="annex", option="skipunknown",
                    # git-annex switched default for this config:
                    default=bool(
                        external_versions['cmd:annex'] < '10.20220222')):

                stderr = "error: pathspec 'nonex1' did not match any file(s) " \
                         "known to git\n" \
                         "error: pathspec 'nonex2' did not match any file(s) " \
                         "known to git\n"
            else:
                stderr = "git-annex: nonex1 not found\n" \
                         "git-annex: nonex2 not found\n"

            raise CommandError(
                "Failed to run ...",
                stdout_json=[
                    {"command":"copy","note":"to target ...", "success":True,
                     "key":"akey1", "file":"copied"},
                    {"command":"copy","note":"checking target ...",
                     "success":True, "key":"akey2", "file":"existed"},
                ],
                stderr=stderr
            )
        else:
            return orig_run(command, **kwargs)

    def fail_to_copy_get_expected(files, expr):
        assert files == ["copied", "existed", "nonex1", "nonex2"]
        return {'akey1': 10}, ["copied"]

    with patch.object(repo, '_call_annex', fail_to_copy), \
            patch.object(repo, '_get_expected_files', fail_to_copy_get_expected):
        with assert_raises(IncompleteResultsError) as cme:
            repo.copy_to(["copied", "existed", "nonex1", "nonex2"], "target")
    eq_(cme.value.results, ["copied"])
    eq_(cme.value.failed, ['nonex1', 'nonex2'])


@with_tempfile
@with_tempfile
def test_annex_drop(src=None, dst=None):
    ar = AnnexRepo(src)
    (ar.pathobj / 'test-annex.dat').write_text("content")
    ar.save('some')

    ar = AnnexRepo.clone(src, dst)
    testfile = 'test-annex.dat'
    assert_false(ar.file_has_content(testfile))
    ar.get(testfile)
    ok_(ar.file_has_content(testfile))
    eq_(len([f for f in ar.fsck(fast=True) if f['file'] == testfile]), 1)

    # drop file by name:
    result = ar.drop([testfile])
    assert_false(ar.file_has_content(testfile))
    ok_(isinstance(result, list))
    eq_(len(result), 1)
    eq_(result[0]['command'], 'drop')
    eq_(result[0]['success'], True)
    eq_(result[0]['file'], testfile)

    ar.get(testfile)

    # drop file by key:
    testkey = ar.get_file_annexinfo(testfile)['key']
    result = ar.drop([testkey], key=True)
    assert_false(ar.file_has_content(testfile))
    ok_(isinstance(result, list))
    eq_(len(result), 1)
    eq_(result[0]['command'], 'drop')
    eq_(result[0]['success'], True)
    eq_(result[0]['key'], testkey)

    # insufficient arguments:
    assert_raises(TypeError, ar.drop)
    assert_raises(InsufficientArgumentsError, ar.drop, [], options=["--jobs=5"])
    assert_raises(InsufficientArgumentsError, ar.drop, [])

    # too much arguments:
    assert_raises(CommandError, ar.drop, ['.'], options=['--all'])

    (ar.pathobj / 'somefile.txt').write_text('this')
    ar.save()
    with assert_raises(CommandError) as e:
        ar.drop('somefile.txt')
    # CommandError has to pull the errors from the JSON record 'note'
    assert_in('necessary cop', str(e.value))

    with assert_raises(CommandError) as e:
        ar._call_annex_records(['fsck', '-N', '3'])
    # CommandError has to pull the errors from the JSON record 'error-messages'
    assert_in('1 of 3 trustworthy copies', str(e.value))


@with_tree({"a.txt": "a", "b.txt": "b", "c.py": "c", "d": "d"})
def test_annex_get_annexed_files(path=None):
    repo = AnnexRepo(path)
    repo.add(".")
    repo.commit()
    eq_(set(repo.get_annexed_files()), {"a.txt", "b.txt", "c.py", "d"})

    repo.drop("a.txt", options=["--force"])
    eq_(set(repo.get_annexed_files()), {"a.txt", "b.txt", "c.py", "d"})
    eq_(set(repo.get_annexed_files(with_content_only=True)),
        {"b.txt", "c.py", "d"})

    eq_(set(repo.get_annexed_files(patterns=["*.txt"])),
        {"a.txt", "b.txt"})
    eq_(set(repo.get_annexed_files(with_content_only=True,
                                   patterns=["*.txt"])),
        {"b.txt"})

    eq_(set(repo.get_annexed_files(patterns=["*.txt", "*.py"])),
        {"a.txt", "b.txt", "c.py"})

    eq_(set(repo.get_annexed_files()),
        set(repo.get_annexed_files(patterns=["*"])))

    eq_(set(repo.get_annexed_files(with_content_only=True)),
        set(repo.get_annexed_files(with_content_only=True, patterns=["*"])))


@pytest.mark.parametrize("batch", [True, False])
@with_tree(tree={"test-annex.dat": "content"})
@serve_path_via_http()
@with_tempfile()
@with_tempfile()
def test_is_available(_=None, content_url=None, origpath=None, path=None, *,
                      batch):

    fname = "test-annex.dat"
    content_url += "/" + fname
    origds = Dataset(origpath).create()
    origds.repo.add_url_to_file(fname, content_url)
    origds.save()
    origds.drop(fname)
    annex = clone(origpath, path).repo

    # bkw = {'batch': batch}
    if batch:
        is_available = partial(annex.is_available, batch=batch)
    else:
        is_available = annex.is_available

    key = annex.get_content_annexinfo([fname]).popitem()[1]['key']

    # explicit is to verify data type etc
    assert is_available(key, key=True) is True
    assert is_available(fname) is True

    # known remote but doesn't have it
    assert is_available(fname, remote=DEFAULT_REMOTE) is False

    # If the 'datalad' special remote is present, it will claim fname's URL.
    if DATALAD_SPECIAL_REMOTE in annex.get_remotes():
        remote = DATALAD_SPECIAL_REMOTE
        uuid = DATALAD_SPECIAL_REMOTES_UUIDS[DATALAD_SPECIAL_REMOTE]
    else:
        remote = "web"
        uuid = WEB_SPECIAL_REMOTE_UUID

    # it is on the 'web'
    assert is_available(fname, remote=remote) is True
    # not effective somehow :-/  may be the process already running or smth
    # with swallow_logs(), swallow_outputs():  # it will complain!
    assert is_available(fname, remote='unknown') is False
    assert_false(is_available("boguskey", key=True))

    # remove url
    urls = annex.whereis(fname, output="full").get(uuid, {}).get("urls", [])

    assert(len(urls) == 1)
    eq_(urls,
        annex.whereis(key, key=True, output="full")
        .get(uuid, {}).get("urls"))
    annex.rm_url(fname, urls[0])

    assert is_available(key, key=True) is False
    assert is_available(fname) is False
    assert is_available(fname, remote=remote) is False


@with_tempfile(mkdir=True)
def test_get_urls_none(path=None):
    ar = AnnexRepo(path, create=True)
    with open(opj(ar.path, "afile"), "w") as f:
        f.write("content")
    eq_(ar.get_urls("afile"), [])


@xfail_buggy_annex_info
@with_tempfile(mkdir=True)
def test_annex_add_no_dotfiles(path=None):
    ar = AnnexRepo(path, create=True)
    print(ar.path)
    assert_true(os.path.exists(ar.path))
    assert_false(ar.dirty)
    os.makedirs(opj(ar.path, '.datalad'))
    # we don't care about empty directories
    assert_false(ar.dirty)
    with open(opj(ar.path, '.datalad', 'somefile'), 'w') as f:
        f.write('some content')
    # make sure the repo is considered dirty now
    assert_true(ar.dirty)  # TODO: has been more detailed assertion (untracked file)
    # now add to git, and it should work
    ar.add('.', git=True)
    # all in index
    assert_true(ar.dirty)
    # TODO: has been more specific:
    # assert_false(ar.repo.is_dirty(
    #     index=False, working_tree=True, untracked_files=True, submodules=True))
    ar.commit(msg="some")
    # all committed
    assert_false(ar.dirty)
    # not known to annex
    assert_false(ar.is_under_annex(opj(ar.path, '.datalad', 'somefile')))


@with_tempfile
def test_annex_version_handling_at_min_version(path=None):
    with set_annex_version(AnnexRepo.GIT_ANNEX_MIN_VERSION):
        po = patch.object(AnnexRepo, '_check_git_annex_version',
                          side_effect=AnnexRepo._check_git_annex_version)
        with po as cmpc:
            eq_(AnnexRepo.git_annex_version, None)
            ar1 = AnnexRepo(path, create=True)
            assert(ar1)
            eq_(AnnexRepo.git_annex_version, AnnexRepo.GIT_ANNEX_MIN_VERSION)
            eq_(cmpc.call_count, 1)
            # 2nd time must not be called
            try:
                # Note: Remove to cause creation of a new instance
                rmtree(path)
            except OSError:
                pass
            ar2 = AnnexRepo(path)
            assert(ar2)
            eq_(AnnexRepo.git_annex_version, AnnexRepo.GIT_ANNEX_MIN_VERSION)
            eq_(cmpc.call_count, 1)


@with_tempfile
def test_annex_version_handling_bad_git_annex(path=None):
    with set_annex_version(None):
        eq_(AnnexRepo.git_annex_version, None)
        with assert_raises(MissingExternalDependency) as cme:
            AnnexRepo(path)
        linux_distribution_name = get_linux_distribution()[0]
        if linux_distribution_name == 'debian':
            assert_in("handbook.datalad.org", str(cme.value))
        eq_(AnnexRepo.git_annex_version, None)

    with set_annex_version('6.20160505'):
        eq_(AnnexRepo.git_annex_version, None)
        try:
            # Note: Remove to cause creation of a new instance
            rmtree(path)
        except OSError:
            pass
        assert_raises(OutdatedExternalDependency, AnnexRepo, path)
        # and we don't assign it
        eq_(AnnexRepo.git_annex_version, None)
        # so we could still fail
        try:
            # Note: Remove to cause creation of a new instance
            rmtree(path)
        except OSError:
            pass
        assert_raises(OutdatedExternalDependency, AnnexRepo, path)


@with_tempfile
@with_tempfile
def test_get_description(path1=None, path2=None):
    annex1 = AnnexRepo(path1, create=True)
    # some content for git-annex branch
    create_tree(path1, {'1.dat': 'content'})
    annex1.add('1.dat', git=False)
    annex1.commit("msg")
    annex1_description = annex1.get_description()
    assert_not_equal(annex1_description, path1)

    annex2 = AnnexRepo(path2, create=True, description='custom 2')
    eq_(annex2.get_description(), 'custom 2')
    # not yet known
    eq_(annex2.get_description(uuid=annex1.uuid), None)

    annex2.add_remote('annex1', path1)
    annex2.fetch('annex1')
    # it will match the remote name
    eq_(annex2.get_description(uuid=annex1.uuid),
        annex1_description + ' [annex1]')
    # add a little probe file to make sure it stays untracked
    create_tree(path1, {'probe': 'probe'})
    assert_not_in('probe', annex2.get_indexed_files())
    annex2.localsync('annex1')
    assert_not_in('probe', annex2.get_indexed_files())
    # but let's remove the remote
    annex2.remove_remote('annex1')
    eq_(annex2.get_description(uuid=annex1.uuid), annex1_description)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_AnnexRepo_flyweight(path1=None, path2=None):

    import sys

    repo1 = AnnexRepo(path1, create=True)
    assert_is_instance(repo1, AnnexRepo)

    # Due to issue 4862, we currently still require gc.collect() under unclear
    # circumstances to get rid of an exception traceback when creating in an
    # existing directory. That traceback references the respective function
    # frames which in turn reference the repo instance (they are methods).
    # Doesn't happen on all systems, though. Eventually we need to figure that
    # out.
    # However, still test for the refcount after gc.collect() to ensure we don't
    # introduce new circular references and make the issue worse!
    gc.collect()

    # As long as we don't reintroduce any circular references or produce
    # garbage during instantiation that isn't picked up immediately, `repo1`
    # should be the only counted reference to this instance.
    # Note, that sys.getrefcount reports its own argument and therefore one
    # reference too much.
    assert_equal(1, sys.getrefcount(repo1) - 1)

    # instantiate again:
    repo2 = AnnexRepo(path1, create=False)
    assert_is_instance(repo2, AnnexRepo)
    # the very same object:
    ok_(repo1 is repo2)

    # reference the same in an different way:
    with chpwd(path1):
        repo3 = AnnexRepo(relpath(path1, start=path2), create=False)
        assert_is_instance(repo3, AnnexRepo)
    # it's the same object:
    ok_(repo1 is repo3)

    # but path attribute is absolute, so they are still equal:
    ok_(repo1 == repo3)

    # Now, let's try to get a GitRepo instance from a path, we already have an
    # AnnexRepo of
    repo4 = GitRepo(path1)
    assert_is_instance(repo4, GitRepo)
    assert_not_is_instance(repo4, AnnexRepo)

    orig_id = id(repo1)

    # Be sure we have exactly one object in memory:
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, AnnexRepo) and o.path == path1]))


    # But we have two GitRepos in memory (the AnnexRepo and repo4):
    assert_equal(2, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.path == path1]))

    # deleting one reference doesn't change anything - we still get the same
    # thing:
    del repo1
    gc.collect()  # TODO: see first comment above
    ok_(repo2 is not None)
    ok_(repo2 is repo3)
    ok_(repo2 == repo3)

    repo1 = AnnexRepo(path1)
    eq_(orig_id, id(repo1))

    del repo1
    del repo2

    # for testing that destroying the object calls close() on BatchedAnnex:
    class Dummy:
        def __init__(self, *args, **kwargs):
            self.close_called = False

        def close(self):
            self.close_called = True

    fake_batch = Dummy()

    # Killing last reference will lead to garbage collection which will call
    # AnnexRepo's finalizer:
    with patch.object(repo3._batched, 'close', fake_batch.close):
        with swallow_logs(new_level=1) as cml:
            del repo3
            gc.collect()  # TODO: see first comment above
            cml.assert_logged(msg="Finalizer called on: AnnexRepo(%s)" % path1,
                              level="Level 1",
                              regex=False)
            # finalizer called close() on BatchedAnnex:
            assert_true(fake_batch.close_called)

    # Flyweight is gone:
    assert_not_in(path1, AnnexRepo._unique_instances.keys())

    # gc doesn't know any instance anymore:
    assert_equal([], [o for o in gc.get_objects()
                      if isinstance(o, AnnexRepo) and o.path == path1])
    # GitRepo is unaffected:
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, GitRepo) and o.path == path1]))

    # new object is created on re-request:
    repo1 = AnnexRepo(path1)
    assert_equal(1, len([o for o in gc.get_objects()
                         if isinstance(o, AnnexRepo) and o.path == path1]))


@with_tempfile
@with_tempfile(mkdir=True)
@with_tempfile
def test_AnnexRepo_get_toppath(repo=None, tempdir=None, repo2=None):
    AnnexRepo(repo, create=True)

    reporeal = str(Path(repo).resolve())
    eq_(AnnexRepo.get_toppath(repo, follow_up=False), reporeal)
    eq_(AnnexRepo.get_toppath(repo), repo)
    # Generate some nested directory
    AnnexRepo(repo2, create=True)
    repo2real = str(Path(repo2).resolve())
    nested = opj(repo2, "d1", "d2")
    os.makedirs(nested)
    eq_(AnnexRepo.get_toppath(nested, follow_up=False), repo2real)
    eq_(AnnexRepo.get_toppath(nested), repo2)
    # and if not under git, should return None
    eq_(AnnexRepo.get_toppath(tempdir), None)


def test_AnnexRepo_get_submodules():
    raise SkipTest("TODO")


@with_tempfile(mkdir=True)
def test_AnnexRepo_dirty(path=None):

    repo = AnnexRepo(path, create=True)
    ok_(not repo.dirty)

    # pure git operations:
    # untracked file
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(repo.dirty)
    # staged file
    repo.add('file1.txt', git=True)
    ok_(repo.dirty)
    # clean again
    repo.commit("file1.txt added")
    ok_(not repo.dirty)
    # modify to be the same
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('whatever')
    ok_(not repo.dirty)
    # modified file
    with open(opj(path, 'file1.txt'), 'w') as f:
        f.write('something else')
    ok_(repo.dirty)
    # clean again
    repo.add('file1.txt', git=True)
    repo.commit("file1.txt modified")
    ok_(not repo.dirty)

    # annex operations:
    # untracked file
    with open(opj(path, 'file2.txt'), 'w') as f:
        f.write('different content')
    ok_(repo.dirty)
    # annexed file
    repo.add('file2.txt', git=False)
    ok_(repo.dirty)
    # commit
    repo.commit("file2.txt annexed")

    ok_(not repo.dirty)

    repo.unlock("file2.txt")
    # Unlocking the file is seen as a modification when we're not already in an
    # adjusted branch (for this test, that would be the case if we're on a
    # crippled filesystem).
    ok_(repo.dirty ^ repo.is_managed_branch())
    repo.save()
    ok_(not repo.dirty)

    subm = AnnexRepo(repo.pathobj / "subm", create=True)
    (subm.pathobj / "foo").write_text("foo")
    subm.save()
    ok_(repo.dirty)
    repo.save()
    assert_false(repo.dirty)
    maybe_adjust_repo(subm)
    assert_false(repo.dirty)


@with_tempfile(mkdir=True)
def test_AnnexRepo_set_remote_url(path=None):

    ar = AnnexRepo(path, create=True)
    ar.add_remote('some', 'http://example.com/.git')
    assert_equal(ar.config['remote.some.url'],
                 'http://example.com/.git')
    assert_not_in('remote.some.annexurl', ar.config.keys())
    # change url:
    ar.set_remote_url('some', 'http://believe.it')
    assert_equal(ar.config['remote.some.url'],
                 'http://believe.it')
    assert_not_in('remote.some.annexurl', ar.config.keys())

    # set push url:
    ar.set_remote_url('some', 'ssh://whatever.ru', push=True)
    assert_equal(ar.config['remote.some.pushurl'],
                 'ssh://whatever.ru')
    assert_in('remote.some.annexurl', ar.config.keys())
    assert_equal(ar.config['remote.some.annexurl'],
                 'ssh://whatever.ru')


@with_tempfile(mkdir=True)
def test_wanted(path=None):
    ar = AnnexRepo(path, create=True)
    eq_(ar.get_preferred_content('wanted'), None)
    # test samples with increasing "trickiness"
    for v in ("standard",
              "include=*.nii.gz or include=*.nii",
              "exclude=archive/* and (include=*.dat or smallerthan=2b)"
              ):
        ar.set_preferred_content('wanted', expr=v)
        eq_(ar.get_preferred_content('wanted'), v)
    # give it some file so clone/checkout works without hiccups
    create_tree(ar.path, {'1.dat': 'content'})
    ar.add('1.dat')
    ar.commit(msg="blah")
    # make a clone and see if all cool there
    # intentionally clone as pure Git and do not annex init so to see if we
    # are ignoring crummy log msgs
    ar1_path = ar.path + '_1'
    GitRepo.clone(ar.path, ar1_path)
    ar1 = AnnexRepo(ar1_path, init=False)
    eq_(ar1.get_preferred_content('wanted'), None)
    eq_(ar1.get_preferred_content('wanted', DEFAULT_REMOTE), v)
    ar1.set_preferred_content('wanted', expr='standard')
    eq_(ar1.get_preferred_content('wanted'), 'standard')


@with_tempfile(mkdir=True)
def test_AnnexRepo_metadata(path=None):
    # prelude
    obscure_name = get_most_obscure_supported_name()

    ar = AnnexRepo(path, create=True)
    create_tree(
        path,
        {
            'up.dat': 'content',
            obscure_name: {
                obscure_name + '.dat': 'lowcontent'
            }
        })
    ar.add('.', git=False)
    ar.commit('content')
    assert_repo_status(path)
    # fugue
    # doesn't do anything if there is nothing to do
    ar.set_metadata('up.dat')
    eq_([], list(ar.get_metadata(None)))
    eq_([], list(ar.get_metadata('')))
    eq_([], list(ar.get_metadata([])))
    eq_({'up.dat': {}}, dict(ar.get_metadata('up.dat')))
    # basic invocation
    eq_(1, len(ar.set_metadata(
        'up.dat',
        reset={'mike': 'awesome'},
        add={'tag': 'awesome'},
        remove={'tag': 'awesome'},  # cancels prev, just to use it
        init={'virgin': 'true'},
        purge=['nothere'])))
    # no timestamps by default
    md = dict(ar.get_metadata('up.dat'))
    deq_({'up.dat': {
        'virgin': ['true'],
        'mike': ['awesome']}},
        md)
    # matching timestamp entries for all keys
    md_ts = dict(ar.get_metadata('up.dat', timestamps=True))
    for k in md['up.dat']:
        assert_in('{}-lastchanged'.format(k), md_ts['up.dat'])
    assert_in('lastchanged', md_ts['up.dat'])
    # recursive needs a flag
    assert_raises(CommandError, ar.set_metadata, '.', purge=['virgin'])
    ar.set_metadata('.', purge=['virgin'], recursive=True)
    deq_({'up.dat': {
        'mike': ['awesome']}},
        dict(ar.get_metadata('up.dat')))
    # Use trickier tags (spaces, =)
    ar.set_metadata('.', reset={'tag': 'one and= '}, purge=['mike'], recursive=True)
    playfile = opj(obscure_name, obscure_name + '.dat')
    target = {
        'up.dat': {
            'tag': ['one and= ']},
        playfile: {
            'tag': ['one and= ']}}
    deq_(target, dict(ar.get_metadata('.')))
    for batch in (True, False):
        # no difference in reporting between modes
        deq_(target, dict(ar.get_metadata(['up.dat', playfile], batch=batch)))
    # incremental work like a set
    ar.set_metadata(playfile, add={'tag': 'one and= '})
    deq_(target, dict(ar.get_metadata('.')))
    ar.set_metadata(playfile, add={'tag': ' two'})
    # returned values are sorted
    eq_([' two', 'one and= '], dict(ar.get_metadata(playfile))[playfile]['tag'])
    # init honor prior values
    ar.set_metadata(playfile, init={'tag': 'three'})
    eq_([' two', 'one and= '], dict(ar.get_metadata(playfile))[playfile]['tag'])
    ar.set_metadata(playfile, remove={'tag': ' two'})
    deq_(target, dict(ar.get_metadata('.')))
    # remove non-existing doesn't error and doesn't change anything
    ar.set_metadata(playfile, remove={'ether': 'best'})
    deq_(target, dict(ar.get_metadata('.')))
    # add works without prior existence
    ar.set_metadata(playfile, add={'novel': 'best'})
    eq_(['best'], dict(ar.get_metadata(playfile))[playfile]['novel'])


@with_tree(tree={'file.txt': 'content'})
@serve_path_via_http()
@with_tempfile
def test_AnnexRepo_addurl_batched_and_set_metadata(path=None, url=None, dest=None):
    ar = AnnexRepo(dest, create=True)
    fname = "file.txt"
    ar.add_url_to_file(fname, urljoin(url, fname), batch=True)
    ar.set_metadata(fname, init={"number": "one"})
    eq_(["one"], dict(ar.get_metadata(fname))[fname]["number"])


@with_tempfile(mkdir=True)
def test_change_description(path=None):
    # prelude
    ar = AnnexRepo(path, create=True, description='some')
    eq_(ar.get_description(), 'some')
    # try change it
    ar = AnnexRepo(path, create=False, init=True, description='someother')
    # this doesn't cut the mustard, still old
    eq_(ar.get_description(), 'some')
    # need to resort to "internal" helper
    ar._init(description='someother')
    eq_(ar.get_description(), 'someother')


@with_tempfile
@with_tempfile
def test_AnnexRepo_get_corresponding_branch(src_path=None, path=None):
    src = AnnexRepo(src_path, create=True)
    (src.pathobj / 'test-annex.dat').write_text("content")
    src.save('some')

    ar = AnnexRepo.clone(src_path, path)

    # we should be on the default branch.
    eq_(DEFAULT_BRANCH,
        ar.get_corresponding_branch() or ar.get_active_branch())

    # special case v6 adjusted branch is not provided by a dedicated build:
    ar.adjust()
    # as above, we still want to get the default branch, while being on
    # 'adjusted/<default branch>(unlocked)'
    eq_('adjusted/{}(unlocked)'.format(DEFAULT_BRANCH),
        ar.get_active_branch())
    eq_(DEFAULT_BRANCH, ar.get_corresponding_branch())


@with_tempfile
@with_tempfile
def test_AnnexRepo_get_tracking_branch(src_path=None, path=None):
    src = AnnexRepo(src_path, create=True)
    (src.pathobj / 'test-annex.dat').write_text("content")
    src.save('some')

    ar = AnnexRepo.clone(src_path, path)

    # we want the relation to original branch, e.g. in v6+ adjusted branch
    eq_((DEFAULT_REMOTE, 'refs/heads/' + DEFAULT_BRANCH),
        ar.get_tracking_branch())


@skip_if_adjusted_branch
@with_tempfile
def test_AnnexRepo_is_managed_branch(path=None):
    ar = AnnexRepo(path, create=True)
    (ar.pathobj / 'test-annex.dat').write_text("content")
    ar.save('some')

    ar.adjust()
    ok_(ar.is_managed_branch())


@with_tempfile(mkdir=True)
def test_fake_is_not_special(path=None):
    ar = AnnexRepo(path, create=True)
    # doesn't exist -- we fail by default
    assert_raises(RemoteNotAvailableError, ar.is_special_annex_remote, "fake")
    assert_false(ar.is_special_annex_remote("fake", check_if_known=False))


@with_tree(tree={"remote": {}, "main": {}, "special": {}})
def test_is_special(path=None):
    rem = AnnexRepo(op.join(path, "remote"), create=True)
    dir_arg = "directory={}".format(op.join(path, "special"))
    rem.init_remote("imspecial",
                    ["type=directory", "encryption=none", dir_arg])
    ok_(rem.is_special_annex_remote("imspecial"))

    ar = AnnexRepo.clone(rem.path, op.join(path, "main"))
    assert_false(ar.is_special_annex_remote(DEFAULT_REMOTE))

    assert_false(ar.is_special_annex_remote("imspecial",
                                            check_if_known=False))
    ar.enable_remote("imspecial", options=[dir_arg])
    ok_(ar.is_special_annex_remote("imspecial"))

    # With a mis-configured remote, give warning and return false.
    ar.config.unset(f"remote.{DEFAULT_REMOTE}.url", scope="local")
    with swallow_logs(new_level=logging.WARNING) as cml:
        assert_false(ar.is_special_annex_remote(DEFAULT_REMOTE))
        cml.assert_logged(msg=".*no URL.*", level="WARNING", regex=True)


@with_tempfile(mkdir=True)
def test_fake_dates(path=None):
    ar = AnnexRepo(path, create=True, fake_dates=True)
    timestamp = ar.config.obtain("datalad.fake-dates-start") + 1
    # Commits from the "git annex init" call are one second ahead.
    for commit in ar.get_branch_commits_("git-annex"):
        eq_(timestamp, int(ar.format_commit('%ct', commit)))
    assert_in("timestamp={}s".format(timestamp),
              ar.call_git(["cat-file", "blob", "git-annex:uuid.log"], read_only=True))


# to prevent regression
# http://git-annex.branchable.com/bugs/v6_-_under_subdir__58___git_add___34__whines__34____44___git_commit___34__blows__34__/
# It is disabled because is not per se relevant to DataLad since we do not
# Since we invoke from the top of the repo, we do not hit it,
# but thought to leave it around if we want to enforce/test system-wide git being
# compatible with annex for v6 mode
@with_tempfile(mkdir=True)
def _test_add_under_subdir(path):
    ar = AnnexRepo(path, create=True, version=6)
    gr = GitRepo(path)  # "Git" view over the repository, so we force "git add"
    subdir = opj(path, 'sub')
    subfile = opj('sub', 'empty')
    # os.mkdir(subdir)
    create_tree(subdir, {'empty': ''})
    runner = Runner(cwd=subdir)
    with chpwd(subdir):
        runner.run(['git', 'add', 'empty'])  # should add successfully
        # gr.commit('important') #
        runner.run(['git', 'commit', '-m', 'important'])
        ar.is_under_annex(subfile)


# https://github.com/datalad/datalad/issues/2892
@with_tempfile(mkdir=True)
def test_error_reporting(path=None):
    ar = AnnexRepo(path, create=True)
    res = ar.call_annex_records(['add'], files='gl\\orious BS')
    target = {
        'command': 'add',
        # whole thing, despite space, properly quotes backslash
        'file': 'gl\\orious BS',
        'note': 'not found',
        'success': False
    }
    assert len(res) >= 1
    if 'message-id' in res[0]:
        # new since ~ 10.20230407-99-gbe36e208c2
        target['message-id'] = 'FileNotFound'
        target['input'] = ['gl\\orious BS']
        target['error-messages'] = ['git-annex: gl\\orious BS not found']
    else:
        # our own produced record
        target['error-messages'] = ['File unknown to git']
    eq_(res, [target])


@with_tree(tree={
    'file1': "content1",
    'dir1': {'file2': 'content2'},
})
def test_annexjson_protocol(path=None):
    ar = AnnexRepo(path, create=True)
    ar.save()
    assert_repo_status(path)
    # first an orderly execution
    res = ar._call_annex(
        ['find', '.', '--json'],
        protocol=AnnexJsonProtocol)
    for k in ('stdout', 'stdout_json', 'stderr'):
        assert_in(k, res)
    orig_j = res['stdout_json']
    eq_(len(orig_j), 2)
    # not meant as an exhaustive check for output structure,
    # just some assurance that it is not totally alien
    ok_(all(j['file'] for j in orig_j))
    # no complaints, unless git-annex is triggered to run in debug mode
    if logging.getLogger('datalad.annex').getEffectiveLevel() > 8:
        eq_(res['stderr'], '')

    # Note: git-annex-find <non-existent-path> does not error with all annex
    # versions. Fixed in annex commit
    # ce91f10132805d11448896304821b0aa9c6d9845 (Feb 28, 2022).
    if '10.20220222' < external_versions['cmd:annex'] < '10.20220322':
        raise SkipTest("zero-exit annex-find bug")

    # now the same, but with a forced error
    with assert_raises(CommandError) as e:
        ar._call_annex(['find', '.', 'error', '--json'],
                       protocol=AnnexJsonProtocol)
    # normal operation is not impaired
    eq_(e.value.kwargs['stdout_json'], orig_j)
    # we get a clue what went wrong,
    # but reporting depends on config + version (default changed):
    msg = "pathspec 'error' did not match" if not dl_cfg.getbool(
        section="annex", option="skipunknown",
        # git-annex switched default for this config:
        default=bool(external_versions['cmd:annex'] < '10.20220222')) else \
        "error not found"
    assert_in(msg, e.value.stderr)
    # there should be no errors reported in an individual records
    # hence also no pointless statement in the str()
    assert_not_in('errors from JSON records', str(e.value))


@with_tempfile
def test_annexjson_protocol_long(path=None, *, caplog):
    records = [
        {"k": "v" * 20},
        # Value based off of
        # Lib.asyncio.unix_events._UnixReadPipeTransport.max_size.
        {"k": "v" * 256 * 1024},
        # and tiny ones in between should not be lost
        {"k": "v"},
        # even a much larger one - we should handle as well
        {"k": "v" * 256 * 1024 * 5},
    ]
    with open(path, 'w') as f:
        for record in records:
            print("print(%r);" % json.dumps(record), file=f)
    runner = GitWitlessRunner()
    with caplog.at_level(logging.ERROR), \
        swallow_logs(new_level=logging.ERROR):
        res = runner.run(
            [sys.executable, path],
            protocol=AnnexJsonProtocol
        )
    eq_(res['stdout'], '')
    eq_(res['stderr'], '')
    eq_(res['stdout_json'], records)


@pytest.mark.parametrize("print_opt", ['', ', end=""'])
@with_tempfile
def test_annexjson_protocol_incorrect(path=None, *, print_opt, caplog):
    # Test that we still log some incorrectly formed JSON record
    bad_json = '{"I": "am wrong,}'
    with open(path, 'w') as f:
        print("print(%r%s);" % (bad_json, print_opt), file=f)
    runner = GitWitlessRunner()
    # caplog only to not cause memory error in case of heavy debugging
    # Unfortunately it lacks similar .assert_logged with a regex matching
    # to be just used instead
    with caplog.at_level(logging.ERROR), \
        swallow_logs(new_level=logging.ERROR) as cml:
        res = runner.run(
            [sys.executable, path],
            protocol=AnnexJsonProtocol
        )
        cml.assert_logged(
            msg=".*[rR]eceived undecodable JSON output",
            level="ERROR",
            regex=True)
    # only error logged and nothing returned
    eq_(res['stdout'], '')
    eq_(res['stderr'], '')
    eq_(res['stdout_json'], [])

# see https://github.com/datalad/datalad/pull/5400 for troubleshooting
# for stalling with unlock=False, and then with unlock=True it took >= 300 sec
# https://github.com/datalad/datalad/pull/5433#issuecomment-784470028
@skip_if((on_github or on_travis) and on_nfs)  # TODO. stalled on travis, fails on github
# http://git-annex.branchable.com/bugs/cannot_commit___34__annex_add__34__ed_modified_file_which_switched_its_largefile_status_to_be_committed_to_git_now/#comment-bf70dd0071de1bfdae9fd4f736fd1ec
# https://github.com/datalad/datalad/issues/1651
@known_failure_githubci_win
@pytest.mark.parametrize("unlock", [True, False])
@with_tree(tree={
    '.gitattributes': "** annex.largefiles=(largerthan=4b)",
    'alwaysbig': 'a'*10,
    'willgetshort': 'b'*10,
    'tobechanged-git': 'a',
    'tobechanged-annex': 'a'*10,
})
def test_commit_annex_commit_changed(path=None, *, unlock):
    # Here we test commit working correctly if file was just removed
    # (not unlocked), edited and committed back

    # TODO: an additional possible interaction to check/solidify - if files
    # first get unannexed (after being optionally unlocked first)
    unannex = False

    ar = AnnexRepo(path, create=True)
    ar.save(paths=[".gitattributes"], git=True)
    ar.save("initial commit")
    assert_repo_status(path)
    # Now let's change all but commit only some
    files = [op.basename(p) for p in glob(op.join(path, '*'))]
    if unlock:
        ar.unlock(files)
    if unannex:
        ar.unannex(files)
    create_tree(
        path
        , {
            'alwaysbig': 'a'*11,
            'willgetshort': 'b',
            'tobechanged-git': 'aa',
            'tobechanged-annex': 'a'*11,
            'untracked': 'unique'
        }
        , remove_existing=True
    )
    assert_repo_status(
        path
        , modified=files if not unannex else ['tobechanged-git']
        , untracked=['untracked'] if not unannex else
          # all but the one in git now
          ['alwaysbig', 'tobechanged-annex', 'untracked', 'willgetshort']
    )

    ar.save("message", paths=['alwaysbig', 'willgetshort'])
    assert_repo_status(
        path
        , modified=['tobechanged-git', 'tobechanged-annex']
        , untracked=['untracked']
    )
    ok_file_under_git(path, 'alwaysbig', annexed=True)
    ok_file_under_git(path, 'willgetshort', annexed=False)

    ar.save("message2", untracked='no') # commit all changed
    assert_repo_status(
        path
        , untracked=['untracked']
    )
    ok_file_under_git(path, 'tobechanged-git', annexed=False)
    ok_file_under_git(path, 'tobechanged-annex', annexed=True)


_test_unannex_tree = {
    OBSCURE_FILENAME: 'content1',
    OBSCURE_FILENAME + ".dat": 'content2',
}
if not on_windows and (
        external_versions['cmd:annex'] <= '10.20230407' or external_versions['cmd:annex'] >= '10.20230408'
):
    # Only whenever we are not within the development versions of the 10.20230407
    # where we cannot do version comparison relibalye,
    # the case where we have entire filename within ""
    _test_unannex_tree[f'"{OBSCURE_FILENAME}"'] = 'content3'


@with_tree(tree=_test_unannex_tree)
def test_unannex_etc(path=None):
    # Primarily to test if quote/unquote/not-quote'ing work for tricky
    # filenames. Ref: https://github.com/datalad/datalad/pull/7372
    repo = AnnexRepo(path)
    files = list(_test_unannex_tree)
    # here it is through json so kinda guaranteed to work but let's check too
    assert files == [x['file'] for x in repo.add(files)]
    assert sorted(files) == sorted(repo.get_annexed_files())
    assert files == repo.unannex(files)


@slow  # 15 + 17sec on travis
@pytest.mark.parametrize("cls", [GitRepo, AnnexRepo])
@with_tempfile(mkdir=True)
def test_files_split_exc(topdir=None, *, cls):
    r = cls(topdir)
    # absent files -- should not crash with "too long" but some other more
    # meaningful exception
    files = ["f" * 100 + "%04d" % f for f in range(100000)]
    if isinstance(r, AnnexRepo):
        # Annex'es add first checks for what is being added and does not fail
        # for non existing files either ATM :-/  TODO: make consistent etc
        r.add(files)
    else:
        with assert_raises(Exception) as ecm:
            r.add(files)
        assert_not_in('too long', str(ecm.value))
        assert_not_in('too many', str(ecm.value))


# with 204  (/ + (98+3)*2 + /) chars guaranteed, we hit "filename too long" quickly on windows
# so we are doomed to shorten the filepath for testing on windows. Since the limits are smaller
# on windows (16k vs e.g. 1m on linux in CMD_MAX_ARG), it would already be a "struggle" for it,
# we also reduce number of dirs/files
_ht_len, _ht_n = (48, 20) if on_windows else (98, 100)

_HEAVY_TREE = {
    # might already run into 'filename too long' on windows probably
    "d" * _ht_len + '%03d' % d: {
        # populate with not entirely unique but still not all identical (empty) keys.
        # With content unique to that filename we would still get 100 identical
        # files for each key, thus possibly hitting regressions in annex like
        # https://git-annex.branchable.com/bugs/significant_performance_regression_impacting_datal/
        # but also would not hit filesystem as hard as if we had all the keys unique.
        'f' * _ht_len + '%03d' % f: str(f)
        for f in range(_ht_n)
    }
    for d in range(_ht_n)
}

# @known_failure_windows  # might fail with some older annex `cp` failing to set permissions
@slow  # 313s  well -- if errors out - only 3 sec
@pytest.mark.parametrize("cls", [GitRepo, AnnexRepo])
@with_tree(tree=_HEAVY_TREE)
def test_files_split(topdir=None, *, cls):
    from glob import glob
    r = cls(topdir)
    dirs = glob(op.join(topdir, '*'))
    files = glob(op.join(topdir, '*', '*'))

    r.add(files)
    r.commit(files=files)

    # Let's modify and do dl.add for even a heavier test
    # Now do for real on some heavy directory
    import datalad.api as dl
    for f in files:
        os.unlink(f)
        with open(f, 'w') as f:
            f.write('1')
    dl.save(dataset=r.path, path=dirs, result_renderer="disabled")


@skip_if_on_windows
@skip_if_root
@with_tree({
    'repo': {
        'file1': 'file1',
        'file2': 'file2'
    }
})
def test_ro_operations(path=None):
    # This test would function only if there is a way to run sudo
    # non-interactively, e.g. on Travis or on your local (watchout!) system
    # after you ran sudo command recently.
    run = Runner().run
    sudochown = lambda cmd: run(['sudo', '-n', 'chown'] + cmd)

    repo = AnnexRepo(op.join(path, 'repo'), init=True)
    repo.add('file1')
    repo.commit()

    # make a clone
    repo2 = repo.clone(repo.path, op.join(path, 'clone'))
    repo2.get('file1')

    # progress forward original repo and fetch (but nothing else) it into repo2
    repo.add('file2')
    repo.commit()
    repo2.fetch(DEFAULT_REMOTE)

    # Assure that regardless of umask everyone could read it all
    run(['chmod', '-R', 'a+rX', repo2.path])
    try:
        # To assure that git/git-annex really cannot acquire a lock and do
        # any changes (e.g. merge git-annex branch), we make this repo owned by root
        sudochown(['-R', 'root', repo2.path])
    except Exception as exc:
        # Exception could be CommandError or IOError when there is no sudo
        raise SkipTest("Cannot run sudo chown non-interactively: %s" % exc)

    # recent git would refuse to run  git status  in repository owned by someone else
    # which could lead to odd git-annex errors before 10.20220504-55-gaf0d85446 AKA 10.20220525~13
    # see https://github.com/datalad/datalad/issues/5665 and after an informative error
    # https://github.com/datalad/datalad/issues/6708
    # To overcome - explicitly add the path into allowed
    dl_cfg.add('safe.directory', repo2.path, scope='global')

    try:
        assert not repo2.get('file1')  # should work since file is here already
        repo2.status()  # should be Ok as well
        # and we should get info on the file just fine
        assert repo2.info('file1')
        # The tricky part is the repo_info which might need to update
        # remotes UUID -- by default it should fail!
        # Oh well -- not raised on travis... whatever for now
        #with assert_raises(CommandError):
        #    repo2.repo_info()
        # but should succeed if we disallow merges
        repo2.repo_info(merge_annex_branches=False)
        # and ultimately the ls which uses it
        try:
            from datalad.api import ls
            ls(repo2.path, all_=True, long_=True)
        except ImportError:
            raise SkipTest(
                "No `ls` command available (provided by -deprecated extension)")
    finally:
        sudochown(['-R', str(os.geteuid()), repo2.path])

    # just check that all is good again
    repo2.repo_info()


@skip_if_on_windows
@skip_if_root
@with_tree({
    'file1': 'file1',
})
def test_save_noperms(path=None):
    # check that we do report annex error messages

    # This test would function only if there is a way to run sudo
    # non-interactively, e.g. on Travis or on your local (watchout!) system
    # after you ran sudo command recently.
    repo = AnnexRepo(path, init=True)

    run = Runner().run
    sudochown = lambda cmd: run(['sudo', '-n', 'chown'] + cmd)

    try:
        # To assure that git/git-annex really cannot acquire a lock and do
        # any changes (e.g. merge git-annex branch), we make this repo owned by root
        sudochown(['-R', 'root:root', str(repo.pathobj / 'file1')])
    except Exception as exc:
        # Exception could be CommandError or IOError when there is no sudo
        raise SkipTest("Cannot run sudo chown non-interactively: %s" % exc)

    try:
        repo.save(paths=['file1'])
    except CommandError as exc:
        res = exc.kwargs["stdout_json"]
        assert_result_count(res, 1)
        assert_result_count(res, 1, file='file1',
                            command='add', success=False)
        assert_in('permission denied', res[0]['error-messages'][0])
    finally:
        sudochown(['-R', str(os.geteuid()), repo.path])


def test_get_size_from_key():

    # see https://git-annex.branchable.com/internals/key_format/
    # BACKEND[-sNNNN][-mNNNN][-SNNNN-CNNNN]--NAME

    test_keys = {"ANYBACKEND--NAME": None,
                 "ANYBACKEND-s123-m1234--NAME-WITH-DASHES.ext": 123,
                 "MD5E-s100-S10-C1--somen.ame": 10,
                 "SHA256-s99-S10-C10--name": 9,
                 "SHA256E-sNaN--name": None,  # debatable: None or raise?
                 }

    invalid = ["ANYBACKEND-S10-C30--missing-total",
               "s99-S10-C10--NOBACKEND",
               "MD5-s100-S5--no-chunk-number"]

    for key in invalid:
        assert_raises(ValueError, AnnexRepo.get_size_from_key, key)

    for key, value in test_keys.items():
        eq_(AnnexRepo.get_size_from_key(key), value)


@with_tempfile(mkdir=True)
def test_call_annex(path=None):
    ar = AnnexRepo(path, create=True)
    # we raise on mistakes
    with assert_raises(CommandError):
        ar._call_annex(['not-an-annex-command'])
    # and we get to know why
    try:
        ar._call_annex(['not-an-annex-command'])
    except CommandError as e:
        assert_in('Invalid argument', e.stderr)


@with_tempfile
def test_whereis_zero_copies(path=None):
    repo = AnnexRepo(path, create=True)
    (repo.pathobj / "foo").write_text("foo")
    repo.save()
    repo.drop(["foo"], options=["--force"])

    for output in "full", "uuids", "descriptions":
        res = repo.whereis(files=["foo"], output=output)
        if output == "full":
            assert_equal(res["foo"], {})
        else:
            assert_equal(res, [[]])


@with_tempfile(mkdir=True)
def test_whereis_batch_eqv(path=None):
    path = Path(path)

    repo_a = AnnexRepo(path / "a", create=True)
    (repo_a.pathobj / "foo").write_text("foo")
    (repo_a.pathobj / "bar").write_text("bar")
    (repo_a.pathobj / "baz").write_text("baz")
    repo_a.save()

    repo_b = repo_a.clone(repo_a.path, str(path / "b"))
    repo_b.drop(["bar"])
    repo_b.drop(["baz"])
    repo_b.drop(["baz"], options=["--from=" + DEFAULT_REMOTE, "--force"])

    files = ["foo", "bar", "baz"]
    info = repo_b.get_content_annexinfo(files)
    keys = [info[repo_b.pathobj / f]['key'] for f in files]

    for output in "full", "uuids", "descriptions":
        out_non_batch = repo_b.whereis(files=files, batch=False, output=output)
        assert_equal(out_non_batch,
                     repo_b.whereis(files=files, batch=True, output=output))
        out_non_batch_keys = repo_b.whereis(files=keys, batch=False, key=True, output=output)
        # should be identical
        if output == 'full':
            # we need to map files to keys though
            assert_equal(out_non_batch_keys,
                         {k: out_non_batch[f] for f, k in zip(files, keys)})
        else:
            assert_equal(out_non_batch, out_non_batch_keys)

        if external_versions['cmd:annex'] >= '8.20210903':
            # --batch-keys support was introduced
            assert_equal(out_non_batch_keys,
                         repo_b.whereis(files=keys, batch=True, key=True, output=output))

    if external_versions['cmd:annex'] < '8.20210903':
        # --key= and --batch are incompatible.
        with assert_raises(ValueError):
            repo_b.whereis(files=files, batch=True, key=True)


def test_done_deprecation():
    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        _ = AnnexJsonProtocol("done")
        warn_mock.assert_called_once()

    with unittest.mock.patch("datalad.cmd.warnings.warn") as warn_mock:
        _ = AnnexJsonProtocol()
        warn_mock.assert_not_called()


def test_generator_annex_json_protocol():

    runner = Runner()
    stdin_queue = Queue()

    def json_object(count: int):
        json_template = '{{"id": "some-id", "count": {count}}}'
        return json_template.format(count=count).encode()

    count = 123
    stdin_queue.put(json_object(count=count))
    for result in runner.run(cmd="cat", protocol=GeneratorAnnexJsonProtocol, stdin=stdin_queue):
        assert_equal(
            result,
            {
                "id": "some-id",
                "count": count,
            }
        )
        if count == 133:
            break
        count += 1
        stdin_queue.put(json_object(count=count))


def test_captured_exception():
    class RaiseMock:
        def add_(self, *args, **kwargs):
            raise CommandError("RaiseMock.add_")

    with patch("datalad.support.annexrepo.super") as repl_super:
        repl_super.return_value = RaiseMock()
        gen = AnnexRepo.add_(object(), [])
        assert_raises(CommandError, gen.send, None)


@skip_if_on_windows
def test_stderr_rejecting_protocol_trigger():
    result_generator = GitWitlessRunner().run(
        "echo ssss >&2",
        protocol=GeneratorAnnexJsonNoStderrProtocol)

    try:
        tuple(result_generator)
    except CommandError as e:
        assert_in("ssss", e.stderr)
        return
    assert_true(False)


@skip_if_on_windows
def test_stderr_rejecting_protocol_ignore():

    result_generator = GitWitlessRunner().run(
        ['echo', '{"status": "ok"}'],
        protocol=GeneratorAnnexJsonNoStderrProtocol)
    assert_equal(tuple(result_generator), ({"status": "ok"},))
