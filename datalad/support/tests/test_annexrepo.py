# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test implementation of class AnnexRepo

"""

import logging
from functools import partial
import os
from os import mkdir
from os.path import join as opj
from os.path import basename
from os.path import realpath
from os.path import relpath
from os.path import curdir
from os.path import pardir
from os.path import exists
from shutil import copyfile
from nose.tools import assert_not_is_instance

from six.moves.urllib.parse import urljoin
from six.moves.urllib.parse import urlsplit

import git
from git import GitCommandError
from mock import patch
import gc

from datalad.cmd import Runner

from datalad.support.external_versions import external_versions

from datalad.support.sshconnector import get_connection_hash

from datalad.utils import on_windows
from datalad.utils import chpwd
from datalad.utils import rmtree
from datalad.utils import linux_distribution_name

from datalad.tests.utils import ignore_nose_capturing_stdout
from datalad.tests.utils import assert_cwd_unchanged
from datalad.tests.utils import with_testrepos
from datalad.tests.utils import with_tempfile
from datalad.tests.utils import with_tree
from datalad.tests.utils import create_tree
from datalad.tests.utils import with_batch_direct
from datalad.tests.utils import assert_dict_equal as deq_
from datalad.tests.utils import assert_is_instance
from datalad.tests.utils import assert_false
from datalad.tests.utils import assert_in
from datalad.tests.utils import assert_is
from datalad.tests.utils import assert_not_in
from datalad.tests.utils import assert_re_in
from datalad.tests.utils import assert_raises
from datalad.tests.utils import assert_not_equal
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_true
from datalad.tests.utils import eq_
from datalad.tests.utils import ok_
from datalad.tests.utils import ok_git_config_not_empty
from datalad.tests.utils import ok_annex_get
from datalad.tests.utils import ok_clean_git
from datalad.tests.utils import ok_file_has_content
from datalad.tests.utils import swallow_logs
from datalad.tests.utils import swallow_outputs
from datalad.tests.utils import local_testrepo_flavors
from datalad.tests.utils import serve_path_via_http
from datalad.tests.utils import get_most_obscure_supported_name
from datalad.tests.utils import SkipTest
from datalad.tests.utils import skip_ssh
from datalad.tests.utils import find_files

from datalad.support.exceptions import CommandError
from datalad.support.exceptions import CommandNotAvailableError
from datalad.support.exceptions import FileNotInRepositoryError
from datalad.support.exceptions import FileNotInAnnexError
from datalad.support.exceptions import FileInGitError
from datalad.support.exceptions import OutOfSpaceError
from datalad.support.exceptions import RemoteNotAvailableError
from datalad.support.exceptions import OutdatedExternalDependency
from datalad.support.exceptions import MissingExternalDependency
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.exceptions import AnnexBatchCommandError
from datalad.support.exceptions import IncompleteResultsError

from datalad.support.gitrepo import GitRepo

# imports from same module:
from datalad.support.annexrepo import AnnexRepo
from datalad.support.annexrepo import ProcessAnnexProgressIndicators
from .utils import check_repo_deals_with_inode_change

@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_instance_from_clone(src, dst):

    ar = AnnexRepo.clone(src, dst)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise GitCommandError since git will notice
    # there's already a git-repo at that path and therefore can't clone to `dst`
    with swallow_logs(new_level=logging.WARN) as cm:
        assert_raises(GitCommandError, AnnexRepo.clone, src, dst)
        if git.__version__ != "1.0.2" and git.__version__ != "2.0.5":
            assert("already exists" in cm.out)


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    GitRepo(path)
    assert_raises(RuntimeError, AnnexRepo, path, create=False)

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    ok_(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_crippled_filesystem(src, dst):

    ar = AnnexRepo.clone(src, dst)

    # fake git-annex entries in .git/config:
    writer = ar.repo.config_writer()
    writer.set_value("annex", "crippledfilesystem", True)
    writer.release()
    ok_(ar.is_crippled_fs())
    writer.set_value("annex", "crippledfilesystem", False)
    writer.release()
    assert_false(ar.is_crippled_fs())
    # since we can't remove the entry, just rename it to fake its absence:
    writer.rename_section("annex", "removed")
    writer.set_value("annex", "something", "value")
    writer.release()
    assert_false(ar.is_crippled_fs())


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
def test_AnnexRepo_is_direct_mode(path):

    ar = AnnexRepo(path)
    eq_(ar.config.getbool("annex", "direct", False),
        ar.is_direct_mode())


@with_tempfile()
def test_AnnexRepo_is_direct_mode_gitrepo(path):
    repo = GitRepo(path, create=True)
    # artificially make .git/annex so no annex section gets initialized
    # in .git/config.  We did manage somehow to make this happen (via publish)
    # but didn't reproduce yet, so just creating manually
    mkdir(opj(repo.path, '.git', 'annex'))
    ar = AnnexRepo(path, init=False, create=False)
    # It is unlikely though that annex would be in direct mode (requires explicit)
    # annex magic, without having annex section under .git/config
    dm = ar.is_direct_mode()

    if ar.is_crippled_fs() or on_windows:
        ok_(dm)
    else:
        assert_false(dm)


@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_set_direct_mode(src, dst):

    ar = AnnexRepo.clone(src, dst)

    if ar.config.getint("annex", "version") >= 6:
        # there's no direct mode available:
        assert_raises(CommandError, ar.set_direct_mode, True)
        raise SkipTest("Test not applicable in repository version >= 6")

    ar.set_direct_mode(True)
    ok_(ar.is_direct_mode(), "Switching to direct mode failed.")
    if ar.is_crippled_fs():
        assert_raises(CommandNotAvailableError, ar.set_direct_mode, False)
        ok_(
            ar.is_direct_mode(),
            "Indirect mode on crippled fs detected. Shouldn't be possible.")
    else:
        ar.set_direct_mode(False)
        assert_false(ar.is_direct_mode(), "Switching to indirect mode failed.")


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):
    ar = AnnexRepo.clone(src, annex_path)
    if ar.config.getint("annex", "version") >= 6:
        # there's no direct mode available and therefore no 'annex proxy':
        assert_raises(CommandError, ar.proxy, ['git', 'status'])
        raise SkipTest("Test not applicable in repository version >= 6")
    ar.set_direct_mode(True)

    # annex proxy raises in indirect mode:
    try:
        ar.set_direct_mode(False)
        assert_raises(CommandNotAvailableError, ar.proxy, ['git', 'status'])
    except CommandNotAvailableError:
        # we can't switch to indirect
        pass


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_get_file_key(src, annex_path):

    ar = AnnexRepo.clone(src, annex_path)

    # test-annex.dat should return the correct key:
    eq_(
        ar.get_file_key("test-annex.dat"),
        'SHA256E-s4--181210f8f9c779c26da1d9b2075bde0127302ee0e3fca38c9a83f5b1dd8e5d3b.dat')

    # and should take a list with an empty string as result, if a file wasn't
    # in annex:
    eq_(
        ar.get_file_key(["filenotpresent.wtf", "test-annex.dat"]),
        ['', 'SHA256E-s4--181210f8f9c779c26da1d9b2075bde0127302ee0e3fca38c9a83f5b1dd8e5d3b.dat']
    )

    # test.dat is actually in git
    # should raise Exception; also test for polymorphism
    assert_raises(IOError, ar.get_file_key, "test.dat")
    assert_raises(FileNotInAnnexError, ar.get_file_key, "test.dat")
    assert_raises(FileInGitError, ar.get_file_key, "test.dat")

    # filenotpresent.wtf doesn't even exist
    assert_raises(IOError, ar.get_file_key, "filenotpresent.wtf")


@with_tempfile(mkdir=True)
def test_AnnexRepo_get_outofspace(annex_path):
    ar = AnnexRepo(annex_path, create=True)

    def raise_cmderror(*args, **kwargs):
        raise CommandError(
            cmd="whatever",
            stderr="junk around not enough free space, need 905.6 MB more and after"
        )

    with patch.object(AnnexRepo, '_run_annex_command', raise_cmderror) as cma, \
            assert_raises(OutOfSpaceError) as cme:
        ar.get("file")
    exc = cme.exception
    eq_(exc.sizemore_msg, '905.6 MB')
    assert_re_in(".*annex (find|get). needs 905.6 MB more", str(exc))


@with_testrepos('basic_annex', flavors=['local'])
def test_AnnexRepo_get_remote_na(path):
    ar = AnnexRepo(path)

    with assert_raises(RemoteNotAvailableError) as cme:
        ar.get('test-annex.dat', options=["--from=NotExistingRemote"])
    eq_(cme.exception.remote, "NotExistingRemote")


# 1 is enough to test file_has_content
@with_batch_direct
@with_testrepos('.*annex.*', flavors=['local'], count=1)
@with_tempfile
def test_AnnexRepo_file_has_content(batch, direct, src, annex_path):
    ar = AnnexRepo.clone(src, annex_path, direct=direct)
    testfiles = ["test-annex.dat", "test.dat"]

    eq_(ar.file_has_content(testfiles), [False, False])

    ok_annex_get(ar, "test-annex.dat")
    eq_(ar.file_has_content(testfiles, batch=batch), [True, False])
    eq_(ar.file_has_content(testfiles[:1], batch=batch), [True])

    eq_(ar.file_has_content(testfiles + ["bogus.txt"], batch=batch),
        [True, False, False])

    assert_false(ar.file_has_content("bogus.txt", batch=batch))
    ok_(ar.file_has_content("test-annex.dat", batch=batch))


# 1 is enough to test
@with_batch_direct
@with_testrepos('.*annex.*', flavors=['local'], count=1)
@with_tempfile
def test_AnnexRepo_is_under_annex(batch, direct, src, annex_path):
    ar = AnnexRepo.clone(src, annex_path, direct=direct)

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


@with_tree(tree=(('about.txt', 'Lots of abouts'),
                 ('about2.txt', 'more abouts'),
                 ('d', {'sub.txt': 'more stuff'})))
@serve_path_via_http()
@with_tempfile
def test_AnnexRepo_web_remote(sitepath, siteurl, dst):

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
        ar.add_urls([testurl])
    l = ar.whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    eq_(len(l), 2)
    ok_(ar.file_has_content(testfile))

    # output='full'
    lfull = ar.whereis(testfile, output='full')
    eq_(set(lfull), set(l))  # the same entries
    non_web_remote = l[1 - l.index(ar.WEB_UUID)]
    assert_in('urls', lfull[non_web_remote])
    eq_(lfull[non_web_remote]['urls'], [])
    assert_not_in('uuid', lfull[ar.WEB_UUID])  # no uuid in the records
    eq_(lfull[ar.WEB_UUID]['urls'], [testurl])

    # --all and --key are incompatible
    assert_raises(CommandError, ar.whereis, [], options='--all', output='full', key=True)

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
    assert_not_in(ar.WEB_UUID, l)
    eq_(len(l), 1)

    # now only 1 copy; drop should fail
    res = ar.drop(testfile)
    eq_(res['command'], 'drop')
    eq_(res['success'], False)
    assert_in('adjust numcopies', res['note'])

    # read the url using different method
    ar.add_url_to_file(testfile, testurl)
    l = ar.whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    eq_(len(l), 2)
    ok_(ar.file_has_content(testfile))

    # 2 known copies now; drop should succeed
    ar.drop(testfile)
    l = ar.whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    eq_(len(l), 1)
    assert_false(ar.file_has_content(testfile))
    lfull = ar.whereis(testfile, output='full')
    assert_not_in(non_web_remote, lfull) # not present -- so not even listed

    # multiple files/urls
    # get the file from remote
    with swallow_outputs() as cmo:
        ar.add_urls([testurl2])

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
    eq_(set(lfull[ar.WEB_UUID]['urls']), {testurl, someurl})

    # and now test with a file in subdirectory
    subdir = opj(dst, 'd')
    os.mkdir(subdir)
    with swallow_outputs() as cmo:
        ar.add_url_to_file(testfile3, url=testurl3)
    ok_file_has_content(opj(dst, testfile3), 'more stuff')
    eq_(set(ar.whereis(testfile3)), {ar.WEB_UUID, non_web_remote})
    eq_(set(ar.whereis(testfile3, output='full').keys()), {ar.WEB_UUID, non_web_remote})

    # and if we ask for both files
    info2 = ar.info([testfile, testfile3])
    eq_(set(info2), {testfile, testfile3})
    eq_(info2[testfile3]['size'], 10)

    full = ar.whereis([], options='--all', output='full')
    eq_(len(full.keys()), 3)  # we asked for all files -- got 3 keys
    assert_in(ar.WEB_UUID, full['SHA256E-s10--a978713ea759207f7a6f9ebc9eaebd1b40a69ae408410ddf544463f6d33a30e1.txt'])

    # which would work even if we cd to that subdir, but then we should use explicit curdir
    with chpwd(subdir):
        cur_subfile = opj(curdir, 'sub.txt')
        eq_(set(ar.whereis(cur_subfile)), {ar.WEB_UUID, non_web_remote})
        eq_(set(ar.whereis(cur_subfile, output='full').keys()), {ar.WEB_UUID, non_web_remote})
        testfiles = [cur_subfile, opj(pardir, testfile)]
        info2_ = ar.info(testfiles)
        # Should maintain original relative file names
        eq_(set(info2_), set(testfiles))
        eq_(info2_[cur_subfile]['size'], 10)


@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_AnnexRepo_migrating_backends(src, dst):
    ar = AnnexRepo.clone(src, dst, backend='MD5')
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

    if ar.is_direct_mode():
        # No migration in direct mode
        assert_raises(CommandNotAvailableError, ar.migrate_backend,
                      'test-annex.dat')
    else:
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


@with_tree(**tree1args)
def __test_get_md5s(path):
    # was used just to generate above dict
    annex = AnnexRepo(path, init=True, backend='MD5E')
    files = [basename(f) for f in find_files('.*', path)]
    annex.add(files, commit=True)
    print({f: annex.get_file_key(f) for f in files})


@with_batch_direct
@with_tree(**tree1args)
def test_dropkey(batch, direct, path):
    kw = {'batch': batch}
    annex = AnnexRepo(path, init=True, backend='MD5E', direct=direct)
    files = list(tree1_md5e_keys)
    annex.add(files, commit=True)
    # drop one key
    annex.drop_key(tree1_md5e_keys[files[0]], **kw)
    # drop multiple
    annex.drop_key([tree1_md5e_keys[f] for f in files[1:3]], **kw)
    # drop already dropped -- should work as well atm
    # https://git-annex.branchable.com/bugs/dropkey_--batch_--json_--force_is_always_succesfull
    annex.drop_key(tree1_md5e_keys[files[0]], **kw)
    # and a mix with already dropped or not
    annex.drop_key(list(tree1_md5e_keys.values()), **kw)


@with_tree(**tree1args)
@serve_path_via_http()
def test_AnnexRepo_backend_option(path, url):
    ar = AnnexRepo(path, backend='MD5')

    ar.add('firstfile', backend='SHA1')
    ar.add('secondfile')
    eq_(ar.get_file_backend('firstfile'), 'SHA1')
    eq_(ar.get_file_backend('secondfile'), 'MD5')

    with swallow_outputs() as cmo:
        # must be added under different name since annex 20160114
        ar.add_url_to_file('remotefile2', url + 'remotefile', backend='SHA1')
    eq_(ar.get_file_backend('remotefile2'), 'SHA1')

    with swallow_outputs() as cmo:
        ar.add_urls([url + 'faraway'], backend='SHA1')
    # TODO: what's the annex-generated name of this?
    # For now, workaround:
    ok_(ar.get_file_backend(f) == 'SHA1'
        for f in ar.get_indexed_files() if 'faraway' in f)


@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_get_file_backend(src, dst):
    #init local test-annex before cloning:
    AnnexRepo(src)

    ar = AnnexRepo.clone(src, dst)

    eq_(ar.get_file_backend('test-annex.dat'), 'SHA256E')
    if not ar.is_direct_mode():
        # no migration in direct mode
        ok_annex_get(ar, 'test-annex.dat', network=False)
        ar.migrate_backend('test-annex.dat', backend='SHA1')
        eq_(ar.get_file_backend('test-annex.dat'), 'SHA1')
    else:
        assert_raises(CommandNotAvailableError, ar.migrate_backend,
                      'test-annex.dat', backend='SHA1')


@with_tempfile
def test_AnnexRepo_always_commit(path):

    repo = AnnexRepo(path)
    runner = Runner(cwd=path)
    file1 = get_most_obscure_supported_name() + "_1"
    file2 = get_most_obscure_supported_name() + "_2"
    with open(opj(path, file1), 'w') as f:
        f.write("First file.")
    with open(opj(path, file2), 'w') as f:
        f.write("Second file.")

    # always_commit == True is expected to be default
    repo.add(file1)

    # Now git-annex log should show the addition:
    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    eq_(len(out_list), 1)
    assert_in(file1, out_list[0])
    # check git log of git-annex branch:
    # expected: initial creation, update (by annex add) and another
    # update (by annex log)
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    eq_(num_commits, 3)

    repo.always_commit = False
    repo.add(file2)

    # No additional git commit:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    eq_(num_commits, 3)

    repo.always_commit = True

    # Still one commit only in git-annex log,
    # but 'git annex log' was called when always_commit was true again,
    # so it should commit the addition at the end. Calling it again should then
    # show two commits.
    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    eq_(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in("recording state in git", out_list[1])

    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    eq_(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in(file2, out_list[1])

    # Now git knows as well:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    eq_(num_commits, 4)


@with_testrepos('basic_annex', flavors=['clone'])
def test_AnnexRepo_on_uninited_annex(path):
    assert_false(exists(opj(path, '.git', 'annex'))) # must not be there for this test to be valid
    annex = AnnexRepo(path, create=False, init=False)  # so we can initialize without
    # and still can get our things
    assert_false(annex.file_has_content('test-annex.dat'))
    with swallow_outputs():
        annex.get('test-annex.dat')
        ok_(annex.file_has_content('test-annex.dat'))


@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_commit(path):

    ds = AnnexRepo(path, create=True)
    filename = opj(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.add(filename, git=True)

    assert_raises(AssertionError, ok_clean_git, path, annex=True)

    ds.commit("test _commit")
    ok_clean_git(path, annex=True)

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


@with_testrepos('.*annex.*', flavors=['clone'])
def test_AnnexRepo_add_to_annex(path):

    # Note: Some test repos appears to not be initialized.
    #       Therefore: 'init=True'
    # TODO: Fix these repos finally!
    # clone as provided by with_testrepos:
    repo = AnnexRepo(path, create=False, init=True)

    ok_clean_git(repo, annex=True, ignore_submodules=True)
    filename = get_most_obscure_supported_name()
    filename_abs = opj(repo.path, filename)
    with open(filename_abs, "w") as f:
        f.write("some")

    out_json = repo.add(filename)
    # file is known to annex:
    if not repo.is_direct_mode():
        assert_true(os.path.islink(filename_abs),
                    "Annexed file is not a link.")
    else:
        assert_false(os.path.islink(filename_abs),
                     "Annexed file is link in direct mode.")
    assert_in('key', out_json)
    key = repo.get_file_key(filename)
    assert_false(key == '')
    assert_equal(key, out_json['key'])
    ok_(repo.file_has_content(filename))

    # uncommitted:
    # but not in direct mode branch
    if repo.is_direct_mode():
        ok_(not repo.is_dirty(submodules=False))
    else:
        ok_(repo.is_dirty(submodules=False))

    repo.commit("Added file to annex.")
    ok_clean_git(repo, annex=True, ignore_submodules=True)

    # now using commit/msg options:
    filename = "another.txt"
    with open(opj(repo.path, filename), "w") as f:
        f.write("something else")

    repo.add(filename, commit=True, msg="Added another file to annex.")
    # known to annex:
    ok_(repo.get_file_key(filename))
    ok_(repo.file_has_content(filename))

    # and committed:
    ok_clean_git(repo, annex=True, ignore_submodules=True)


@with_testrepos('.*annex.*', flavors=['clone'])
def test_AnnexRepo_add_to_git(path):

    # Note: Some test repos appears to not be initialized.
    #       Therefore: 'init=True'
    # TODO: Fix these repos finally!

    # clone as provided by with_testrepos:
    repo = AnnexRepo(path, create=False, init=True)

    ok_clean_git(repo, annex=True, ignore_submodules=True)
    filename = get_most_obscure_supported_name()
    with open(opj(repo.path, filename), "w") as f:
        f.write("some")
    repo.add(filename, git=True)

    # not in annex, but in git:
    assert_raises(FileInGitError, repo.get_file_key, filename)
    # uncommitted:
    ok_(repo.is_dirty(submodules=False))
    repo.commit("Added file to annex.")
    ok_clean_git(repo, annex=True, ignore_submodules=True)

    # now using commit/msg options:
    filename = "another.txt"
    with open(opj(repo.path, filename), "w") as f:
        f.write("something else")

    repo.add(filename, git=True, commit=True,
             msg="Added another file to annex.")
    # not in annex, but in git:
    assert_raises(FileInGitError, repo.get_file_key, filename)

    # and committed:
    ok_clean_git(repo, annex=True, ignore_submodules=True)


@ignore_nose_capturing_stdout
@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_AnnexRepo_get(src, dst):

    annex = AnnexRepo.clone(src, dst)
    assert_is_instance(annex, AnnexRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = opj(dst, testfile)
    assert_false(annex.file_has_content("test-annex.dat"))
    with swallow_outputs():
        annex.get(testfile)
    ok_(annex.file_has_content("test-annex.dat"))
    ok_file_has_content(testfile_abs, '123', strip=True)

    called = []
    # for some reason yoh failed mock to properly just call original func
    orig_run = annex._run_annex_command

    def check_run(cmd, annex_options, **kwargs):
        called.append(cmd)
        if cmd == 'find':
            assert_not_in('-J5', annex_options)
        elif cmd == 'get':
            assert_in('-J5', annex_options)
        else:
            raise AssertionError(
                "no other commands so far should be ran. Got %s, %s" %
                (cmd, annex_options)
            )
        return orig_run(cmd, annex_options=annex_options, **kwargs)

    annex.drop(testfile)
    with patch.object(AnnexRepo, '_run_annex_command',
                      side_effect=check_run, auto_spec=True), \
            swallow_outputs():
        annex.get(testfile, jobs=5)
    eq_(called, ['find', 'get'])
    ok_file_has_content(testfile_abs, '123', strip=True)


# TODO:
#def init_remote(self, name, options):
#def enable_remote(self, name):

@with_testrepos('basic_annex$', flavors=['clone'])
@with_tempfile
def _test_AnnexRepo_get_contentlocation(batch, path, work_dir_outside):
    annex = AnnexRepo(path, create=False, init=False)
    fname = 'test-annex.dat'
    key = annex.get_file_key(fname)
    # TODO: see if we can avoid this or specify custom exception
    eq_(annex.get_contentlocation(key, batch=batch), '')

    with swallow_outputs() as cmo:
        annex.get(fname)
    key_location = annex.get_contentlocation(key, batch=batch)
    assert(key_location)
    # they both should point to the same location eventually
    eq_(os.path.realpath(opj(annex.path, fname)),
        os.path.realpath(opj(annex.path, key_location)))

    # test how it would look if done under a subdir of the annex:
    with chpwd(opj(annex.path, 'subdir'), mkdir=True):
        key_location = annex.get_contentlocation(key, batch=batch)
        # they both should point to the same location eventually
        eq_(os.path.realpath(opj(annex.path, fname)),
            os.path.realpath(opj(annex.path, key_location)))

    # test how it would look if done under a dir outside of the annex:
    with chpwd(work_dir_outside, mkdir=True):
        key_location = annex.get_contentlocation(key, batch=batch)
        # they both should point to the same location eventually
        eq_(os.path.realpath(opj(annex.path, fname)),
            os.path.realpath(opj(annex.path, key_location)))


def test_AnnexRepo_get_contentlocation():
    for batch in (False, True):
        yield _test_AnnexRepo_get_contentlocation, batch


@with_tree(tree=(('about.txt', 'Lots of abouts'),
                 ('about2.txt', 'more abouts'),
                 ('about2_.txt', 'more abouts_'),
                 ('d', {'sub.txt': 'more stuff'})))
@serve_path_via_http()
@with_tempfile
def test_AnnexRepo_addurl_to_file_batched(sitepath, siteurl, dst):

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
    os.unlink(opj(dst, testfile))
    ar.add_url_to_file(testfile, testurl, batch=True)

    info = ar.info(testfile)
    eq_(info['size'], 14)
    assert(info['key'])
    # not even added to index yet since we this repo is with default batch_size
    # but: in direct mode it is added!
    if ar.is_direct_mode():
        assert_in(ar.WEB_UUID, ar.whereis(testfile))
    else:
        assert_not_in(ar.WEB_UUID, ar.whereis(testfile))

    # TODO: none of the below should re-initiate the batch process

    # add to an existing and staged annex file
    copyfile(opj(sitepath, 'about2.txt'), opj(dst, testfile2))
    ar.add(testfile2)
    ar.add_url_to_file(testfile2, testurl2, batch=True)
    assert(ar.info(testfile2))
    # not committed yet
    # assert_in(ar.WEB_UUID, ar.whereis(testfile2))

    # add to an existing and committed annex file
    copyfile(opj(sitepath, 'about2_.txt'), opj(dst, testfile2_))
    ar.add(testfile2_)
    if ar.is_direct_mode():
        assert_in(ar.WEB_UUID, ar.whereis(testfile))
    else:
        assert_not_in(ar.WEB_UUID, ar.whereis(testfile))
    ar.commit("added about2_.txt and there was about2.txt lingering around")
    # commit causes closing all batched annexes, so testfile gets committed
    assert_in(ar.WEB_UUID, ar.whereis(testfile))
    assert(not ar.dirty)
    ar.add_url_to_file(testfile2_, testurl2_, batch=True)
    assert(ar.info(testfile2_))
    assert_in(ar.WEB_UUID, ar.whereis(testfile2_))

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
    ar2.commit("added new file")  # would do nothing ATM, but also doesn't fail
    assert_in(filename, ar2.get_files())
    assert_in(ar.WEB_UUID, ar2.whereis(filename))

    if not ar.is_direct_mode():
        # in direct mode there's nothing to commit
        ar.commit("actually committing new files")
    assert_in(filename, ar.get_files())
    assert_in(ar.WEB_UUID, ar.whereis(filename))
    # this poor bugger still wasn't added since we used default batch_size=0 on him

    # and closing the pipes now shoudn't anyhow affect things
    eq_(len(ar._batched), 1)
    ar._batched.close()
    eq_(len(ar._batched), 1)  # doesn't remove them, just closes
    assert(not ar.dirty)

    ar._batched.clear()
    eq_(len(ar._batched), 0)  # .clear also removes

    raise SkipTest("TODO: more, e.g. add with a custom backend")
    # TODO: also with different modes (relaxed, fast)
    # TODO: verify that file is added with that backend and that we got a new batched process


@with_tempfile(mkdir=True)
def test_annex_backends(path):
    repo = AnnexRepo(path)
    eq_(repo.default_backends, None)

    rmtree(path)

    repo = AnnexRepo(path, backend='MD5E')
    eq_(repo.default_backends, ['MD5E'])

    # persists
    repo = AnnexRepo(path)
    eq_(repo.default_backends, ['MD5E'])


@skip_ssh
@with_tempfile
@with_testrepos('basic_annex', flavors=['local'])
@with_testrepos('basic_annex', flavors=['local'])
def test_annex_ssh(repo_path, remote_1_path, remote_2_path):
    from datalad import ssh_manager
    # create remotes:
    rm1 = AnnexRepo(remote_1_path, create=False)
    rm2 = AnnexRepo(remote_2_path, create=False)

    # check whether we are the first to use these sockets:
    socket_1 = opj(ssh_manager.socket_dir, get_connection_hash('datalad-test'))
    socket_2 = opj(ssh_manager.socket_dir, get_connection_hash('localhost'))
    datalad_test_was_open = exists(socket_1)
    localhost_was_open = exists(socket_2)

    # repo to test:AnnexRepo(repo_path)
    # At first, directly use git to add the remote, which should be recognized
    # by AnnexRepo's constructor
    gr = GitRepo(repo_path, create=True)
    AnnexRepo(repo_path)
    gr.add_remote("ssh-remote-1", "ssh://datalad-test" + remote_1_path)

    # Now, make it an annex:
    ar = AnnexRepo(repo_path, create=False)

    # connection to 'datalad-test' should be known to ssh manager:
    assert_in(socket_1, ssh_manager._connections)
    # but socket was not touched:
    if datalad_test_was_open:
        ok_(exists(socket_1))
    else:
        ok_(not exists(socket_1))

    from datalad import lgr
    lgr.debug("HERE")
    # remote interaction causes socket to be created:
    try:
        # Note: For some reason, it hangs if log_stdout/err True
        # TODO: Figure out what's going on
        #  yoh: I think it is because of what is "TODOed" within cmd.py --
        #       trying to log/obtain both through PIPE could lead to lock
        #       downs.
        # here we use our swallow_logs to overcome a problem of running under
        # nosetests without -s, when nose then tries to swallow stdout by
        # mocking it with StringIO, which is not fully compatible with Popen
        # which needs its .fileno()
        with swallow_outputs():
            ar._run_annex_command('sync',
                                  expect_stderr=True,
                                  log_stdout=False,
                                  log_stderr=False,
                                  expect_fail=True)
    # sync should return exit code 1, since it can not merge
    # doesn't matter for the purpose of this test
    except CommandError as e:
        if e.code == 1:
            pass

    ok_(exists(socket_1))

    # add another remote:
    ar.add_remote('ssh-remote-2', "ssh://localhost" + remote_2_path)

    # now, this connection to localhost was requested:
    assert_in(socket_2, ssh_manager._connections)
    # but socket was not touched:
    if localhost_was_open:
        ok_(exists(socket_2))
    else:
        ok_(not exists(socket_2))

    # sync with the new remote:
    try:
        with swallow_outputs():
            ar._run_annex_command('sync', annex_options=['ssh-remote-2'],
                                  expect_stderr=True,
                                  log_stdout=False,
                                  log_stderr=False,
                                  expect_fail=True)
    # sync should return exit code 1, since it can not merge
    # doesn't matter for the purpose of this test
    except CommandError as e:
        if e.code == 1:
            pass

    ok_(exists(socket_2))


@with_testrepos('basic_annex', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_annex_remove(path1, path2):
    ar1 = AnnexRepo(path1, create=False)
    ar2 = AnnexRepo.clone(path1, path2, create=True, direct=True)

    for repo in (ar1, ar2):
        file_list = repo.get_annexed_files()
        assert len(file_list) >= 1
        # remove a single file
        out = repo.remove(file_list[0])
        assert_not_in(file_list[0], repo.get_annexed_files())
        eq_(out[0], file_list[0])

        with open(opj(repo.path, "rm-test.dat"), "w") as f:
            f.write("whatever")

        # add it
        repo.add("rm-test.dat")

        # remove without '--force' should fail, due to staged changes:
        if repo.is_direct_mode():
            assert_raises(CommandError, repo.remove, "rm-test.dat")
        else:
            assert_raises(GitCommandError, repo.remove, "rm-test.dat")
        assert_in("rm-test.dat", repo.get_annexed_files())

        # now force:
        out = repo.remove("rm-test.dat", force=True)
        assert_not_in("rm-test.dat", repo.get_annexed_files())
        eq_(out[0], "rm-test.dat")


@with_tempfile
@with_tempfile
@with_tempfile
def test_repo_version(path1, path2, path3):
    annex = AnnexRepo(path1, create=True, version=6)
    ok_clean_git(path1, annex=True)
    version = annex.repo.config_reader().get_value('annex', 'version')
    eq_(version, 6)

    # default from config item (via env var):
    with patch.dict('os.environ', {'DATALAD_REPO_VERSION': '6'}):
        annex = AnnexRepo(path2, create=True)
        version = annex.repo.config_reader().get_value('annex', 'version')
        eq_(version, 6)

        # parameter `version` still has priority over default config:
        annex = AnnexRepo(path3, create=True, version=5)
        version = annex.repo.config_reader().get_value('annex', 'version')
        eq_(version, 5)


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_annex_copy_to(origin, clone):
    repo = AnnexRepo(origin, create=False)
    remote = AnnexRepo.clone(origin, clone, create=True)
    repo.add_remote("target", clone)

    assert_raises(IOError, repo.copy_to, "doesnt_exist.dat", "target")
    assert_raises(FileInGitError, repo.copy_to, "INFO.txt", "target")
    assert_raises(ValueError, repo.copy_to, "test-annex.dat", "invalid_target")

    # test-annex.dat has no content to copy yet:
    eq_(repo.copy_to("test-annex.dat", "target"), [])

    repo.get("test-annex.dat")
    # now it has:
    eq_(repo.copy_to("test-annex.dat", "target"), ["test-annex.dat"])
    # and will not be copied again since it was already copied
    eq_(repo.copy_to(["INFO.txt", "test-annex.dat"], "target"), [])

    # Test that if we pass a list of items and annex processes them nicely,
    # we would obtain a list back. To not stress our tests even more -- let's mock
    def ok_copy(command, **kwargs):
        return """
{"command":"copy","note":"to target ...", "success":true, "key":"akey1", "file":"copied1"}
{"command":"copy","note":"to target ...", "success":true, "key":"akey2", "file":"copied2"}
{"command":"copy","note":"checking target ...", "success":true, "key":"akey3", "file":"existed"}
""", ""
    with patch.object(repo, '_run_annex_command', ok_copy):
        eq_(repo.copy_to(["copied2", "copied1", "existed"], "target"),
            ["copied1", "copied2"])

    # now let's test that we are correctly raising the exception in case if
    # git-annex execution fails
    orig_run = repo._run_annex_command
    def fail_to_copy(command, **kwargs):
        if command == 'copy':
            # That is not how annex behaves
            # http://git-annex.branchable.com/bugs/copy_does_not_reflect_some_failed_copies_in_--json_output/
            # for non-existing files output goes into stderr
            raise CommandError(
                "Failed to run ...",
                stdout=
                    '{"command":"copy","note":"to target ...", "success":true, "key":"akey1", "file":"copied"}\n'
                    '{"command":"copy","note":"checking target ...", "success":true, "key":"akey2", "file":"existed"}\n',
                stderr=
                    'git-annex: nonex1 not found\n'
                    'git-annex: nonex2 not found\n'
            )
        else:
            return orig_run(command, **kwargs)

    with patch.object(repo, '_run_annex_command', fail_to_copy):
        with assert_raises(IncompleteResultsError) as cme:
            repo.copy_to(["copied", "existed", "nonex1", "nonex2"], "target")
    eq_(cme.exception.results, ["copied"])
    eq_(cme.exception.failed, ['nonex1', 'nonex2'])


@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_annex_drop(src, dst):
    ar = AnnexRepo.clone(src, dst)
    testfile = 'test-annex.dat'
    assert_false(ar.file_has_content(testfile))
    ar.get(testfile)
    ok_(ar.file_has_content(testfile))

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
    testkey = ar.get_file_key(testfile)
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


@with_testrepos('basic_annex', flavors=['clone'])
def test_annex_remove(path):
    repo = AnnexRepo(path, create=False)

    file_list = repo.get_annexed_files()
    assert len(file_list) >= 1
    # remove a single file
    out = repo.remove(file_list[0])
    assert_not_in(file_list[0], repo.get_annexed_files())
    eq_(out[0], file_list[0])

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


@with_batch_direct
@with_testrepos('basic_annex', flavors=['clone'], count=1)
def test_is_available(batch, direct, p):
    annex = AnnexRepo(p)

    # bkw = {'batch': batch}
    if batch:
        is_available = partial(annex.is_available, batch=batch)
    else:
        is_available = annex.is_available

    fname = 'test-annex.dat'
    key = annex.get_file_key(fname)

    # explicit is to verify data type etc
    assert is_available(key, key=True) is True
    assert is_available(fname) is True

    # known remote but doesn't have it
    assert is_available(fname, remote='origin') is False
    # it is on the 'web'
    assert is_available(fname, remote='web') is True
    # not effective somehow :-/  may be the process already running or smth
    # with swallow_logs(), swallow_outputs():  # it will complain!
    assert is_available(fname, remote='unknown') is False
    assert_false(is_available("boguskey", key=True))

    # remove url
    urls = annex.get_urls(fname) #, **bkw)
    assert(len(urls) == 1)
    annex.rm_url(fname, urls[0])

    assert is_available(key, key=True) is False
    assert is_available(fname) is False
    assert is_available(fname, remote='web') is False


@with_tempfile(mkdir=True)
def test_annex_add_no_dotfiles(path):
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
    # no file is being added, as dotfiles/directories are ignored by default
    ar.add('.', git=False)
    # double check, still dirty
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
def test_annex_version_handling(path):
    with patch.object(AnnexRepo, 'git_annex_version', None) as cmpov, \
         patch.object(AnnexRepo, '_check_git_annex_version',
                      auto_spec=True,
                      side_effect=AnnexRepo._check_git_annex_version) \
            as cmpc, \
         patch.object(external_versions, '_versions',
                      {'cmd:annex': AnnexRepo.GIT_ANNEX_MIN_VERSION}):
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
    with patch.object(AnnexRepo, 'git_annex_version', None) as cmpov, \
            patch.object(AnnexRepo, '_check_git_annex_version',
                         auto_spec=True,
                         side_effect=AnnexRepo._check_git_annex_version):
        # no git-annex at all
        with patch.object(
                external_versions, '_versions', {'cmd:annex': None}):
            eq_(AnnexRepo.git_annex_version, None)
            with assert_raises(MissingExternalDependency) as cme:
                try:
                    # Note: Remove to cause creation of a new instance
                    rmtree(path)
                except OSError:
                    pass
                AnnexRepo(path)
            if linux_distribution_name == 'debian':
                assert_in("http://neuro.debian.net", str(cme.exception))
            eq_(AnnexRepo.git_annex_version, None)

        # outdated git-annex at all
        with patch.object(
                external_versions, '_versions', {'cmd:annex': '6.20160505'}):
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


def test_ProcessAnnexProgressIndicators():
    irrelevant_lines = (
        'abra',
        '{"some_json": "sure thing"}'
    )
    # regular lines, without completion for known downloads
    success_lines = (
        '{"command":"get","note":"","success":true,"key":"key1","file":"file1"}',
        '{"command":"comm","note":"","success":true,"key":"backend-s10--key2"}',
    )
    progress_lines = (
        '{"byte-progress":10,"action":{"command":"get","note":"from web...",'
            '"key":"key1","file":"file1"},"percent-progress":"10%"}',
    )

    # without providing expected entries
    proc = ProcessAnnexProgressIndicators()
    # when without any target downloads, there is no total_pbar
    assert_is(proc.total_pbar, None)
    # for regular lines -- should just return them without side-effects
    for l in irrelevant_lines + success_lines:
        with swallow_outputs() as cmo:
            eq_(proc(l), l)
            eq_(proc.pbars, {})
            eq_(cmo.out, '')
            eq_(cmo.err, '')
    # should process progress lines
    eq_(proc(progress_lines[0]), None)
    eq_(len(proc.pbars), 1)
    # but when we finish download -- should get cleared
    eq_(proc(success_lines[0]), success_lines[0])
    eq_(proc.pbars, {})
    # and no side-effect of any kind in finish
    eq_(proc.finish(), None)

    proc = ProcessAnnexProgressIndicators(expected={'key1': 100, 'key2': None})
    # when without any target downloads, there is no total_pbar
    assert(proc.total_pbar is not None)
    eq_(proc.total_pbar.total, 100)  # as much as it knows at this point
    eq_(proc.total_pbar.current, 0)
    # for regular lines -- should still just return them without side-effects
    for l in irrelevant_lines:
        with swallow_outputs() as cmo:
            eq_(proc(l), l)
            eq_(proc.pbars, {})
            eq_(cmo.out, '')
            eq_(cmo.err, '')
    # should process progress lines
    # it doesn't swallow everything -- so there will be side-effects in output
    with swallow_outputs() as cmo:
        eq_(proc(progress_lines[0]), None)
        eq_(len(proc.pbars), 1)
        # but when we finish download -- should get cleared
        eq_(proc(success_lines[0]), success_lines[0])
        eq_(proc.pbars, {})
        out = cmo.out

    from datalad.ui import ui
    from datalad.ui.dialog import SilentConsoleLog

    assert out \
        if not isinstance(ui.ui, SilentConsoleLog) else not out
    assert proc.total_pbar is not None
    # and no side-effect of any kind in finish
    with swallow_outputs() as cmo:
        eq_(proc.finish(), None)
        eq_(proc.total_pbar, None)


@with_tempfile
@with_tempfile
def test_get_description(path1, path2):
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
    annex2.merge_annex('annex1')
    assert_not_in('probe', annex2.get_indexed_files())
    # but let's remove the remote
    annex2.remove_remote('annex1')
    eq_(annex2.get_description(uuid=annex1.uuid), annex1_description)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_AnnexRepo_flyweight(path1, path2):

    repo1 = AnnexRepo(path1, create=True)
    assert_is_instance(repo1, AnnexRepo)
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


@with_testrepos(flavors=local_testrepo_flavors)
@with_tempfile(mkdir=True)
@with_tempfile
def test_AnnexRepo_get_toppath(repo, tempdir, repo2):

    reporeal = realpath(repo)
    eq_(AnnexRepo.get_toppath(repo, follow_up=False), reporeal)
    eq_(AnnexRepo.get_toppath(repo), repo)
    # Generate some nested directory
    AnnexRepo(repo2, create=True)
    repo2real = realpath(repo2)
    nested = opj(repo2, "d1", "d2")
    os.makedirs(nested)
    eq_(AnnexRepo.get_toppath(nested, follow_up=False), repo2real)
    eq_(AnnexRepo.get_toppath(nested), repo2)
    # and if not under git, should return None
    eq_(AnnexRepo.get_toppath(tempdir), None)


@with_testrepos(".*basic.*", flavors=['local'])
@with_tempfile(mkdir=True)
def test_AnnexRepo_add_submodule(source, path):

    top_repo = AnnexRepo(path, create=True)

    top_repo.add_submodule('sub', name='sub', url=source)
    top_repo.commit('submodule added')
    eq_([s.name for s in top_repo.get_submodules()], ['sub'])

    ok_clean_git(top_repo, annex=True)
    ok_clean_git(opj(path, 'sub'), annex=False)


def test_AnnexRepo_update_submodule():
    raise SkipTest("TODO")


def test_AnnexRepo_get_submodules():
    raise SkipTest("TODO")


@with_tempfile(mkdir=True)
def test_AnnexRepo_dirty(path):

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
    if not repo.config.getint("annex", "version") == 6:
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
    if not repo.is_direct_mode():
        # in direct mode 'annex add' results in a clean repo
        ok_(repo.dirty)
        # commit
        repo.commit("file2.txt annexed")
    ok_(not repo.dirty)

    # TODO: unlock/modify

    # TODO: submodules


def _test_status(ar):
    # TODO: plain git submodule and even deeper hierarchy?
    #       => complete recursion to work if started from within plain git;
    #       But this is then relevant for Dataset.status() - not herein

    def sync_wrapper(push=False, pull=False, commit=False):
        # wraps common annex-sync call, since it currently fails under
        # mysterious circumstances in V6 adjusted branch setups
        try:
            ar.sync(push=push, pull=pull, commit=commit)
        except CommandError as e:
            if "fatal: entry 'submod' object type (blob) doesn't match mode type " \
               "(commit)" in e.stderr:
                # some bug in adjusted branch(?) + submodule
                # TODO: figure out and probably report
                # stdout:
                # commit
                # [adjusted/master(unlocked) ae3e9a7] git-annex in ben@tree:/tmp/datalad_temp_test_AnnexRepo_status7qKhRQ
                #  4 files changed, 4 insertions(+), 2 deletions(-)
                #  create mode 100644 fifth
                #  create mode 100644 sub/third
                # ok
                #
                # failed
                # stderr:
                # fatal: entry 'submod' object type (blob) doesn't match mode type (commit)
                # git-annex: user error (git ["--git-dir=.git","--work-tree=.","--literal-pathspecs","mktree","--batch","-z"] exited 128)
                # git-annex: sync: 1 failed

                # But it almost works - so apperently nothing to do
                import logging
                lgr = logging.getLogger("datalad.support.tests.test-status")
                lgr.warning("DEBUG: v6 sync failure")

    stat = {'untracked': [],
            'deleted': [],
            'modified': [],
            'added': [],
            'type_changed': []}
    eq_(stat, ar.get_status())

    # untracked files:
    with open(opj(ar.path, 'first'), 'w') as f:
        f.write("it's huge!")
    with open(opj(ar.path, 'second'), 'w') as f:
        f.write("looser")

    stat['untracked'].append('first')
    stat['untracked'].append('second')
    eq_(stat, ar.get_status())

    # add a file to git
    ar.add('first', git=True)
    sync_wrapper()
    stat['untracked'].remove('first')
    stat['added'].append('first')
    eq_(stat, ar.get_status())

    # add a file to annex
    ar.add('second')
    sync_wrapper()
    stat['untracked'].remove('second')
    if not ar.is_direct_mode():
        # in direct mode annex-status doesn't report an added file 'added'
        stat['added'].append('second')
    eq_(stat, ar.get_status())

    # commit to be clean again:
    ar.commit("added first and second")
    stat = {'untracked': [],
            'deleted': [],
            'modified': [],
            'added': [],
            'type_changed': []}
    eq_(stat, ar.get_status())
    # create a file to be unannexed:
    with open(opj(ar.path, 'fifth'), 'w') as f:
        f.write("total disaster")

    ar.add('fifth')
    sync_wrapper()
    # TODO:
    # Note: For some reason this seems to be the only place, where we actually
    # need to call commit via annex-proxy. If called via '-c core.bare=False'
    # and/or '--work-tree=.' the file ends up in git instead of annex.
    # Note 2: This is only if we explicitly pass a path. Otherwise it works
    # without annex-proxy.
    ar.commit(msg="fifth to be unannexed", files='fifth',
              proxy=ar.is_direct_mode())
    eq_(stat, ar.get_status())

    ar.unannex('fifth')

    sync_wrapper(pull=False, push=False, commit=True)
    stat['untracked'].append('fifth')
    eq_(stat, ar.get_status())

    # modify a file in git:
    with open(opj(ar.path, 'first'), 'w') as f:
        f.write("increased tremendousness")
    stat['modified'].append('first')
    eq_(stat, ar.get_status())

    # modify an annexed file:
    if not ar.is_direct_mode():
        # actually: if 'second' isn't locked, which is the case in direct mode
        ar.unlock('second')
        if not ar.get_active_branch().endswith('(unlocked)'):
            stat['type_changed'].append('second')
        eq_(stat, ar.get_status())
    with open(opj(ar.path, 'second'), 'w') as f:
        f.write("Needed to unlock first. Sad!")
    if not ar.is_direct_mode():
        ar.add('second')  # => modified
        if not ar.get_active_branch().endswith('(unlocked)'):
            stat['type_changed'].remove('second')
    stat['modified'].append('second')
    sync_wrapper()
    eq_(stat, ar.get_status())

    # create something in a subdir
    os.mkdir(opj(ar.path, 'sub'))
    with open(opj(ar.path, 'sub', 'third'), 'w') as f:
        f.write("tired of winning")

    # Note, that this is different from 'git status',
    # which would just say 'sub/':
    stat['untracked'].append(opj('sub', 'third'))
    eq_(stat, ar.get_status())

    # test parameters for status to restrict results:
    # limit requested states:
    limited_status = ar.get_status(untracked=True, deleted=False, modified=True,
                                   added=True, type_changed=False)
    eq_(len(limited_status), 3)
    ok_(all([k in ('untracked', 'modified', 'added') for k in limited_status]))
    eq_(stat['untracked'], limited_status['untracked'])
    eq_(stat['modified'], limited_status['modified'])
    eq_(stat['added'], limited_status['added'])
    # limit requested files:
    limited_status = ar.get_status(path=opj('sub', 'third'))
    eq_(limited_status['untracked'], [opj('sub', 'third')])
    ok_(all([len(limited_status[l]) == 0 for l in ('modified', 'added',
                                                   'deleted', 'type_changed')]))
    # again, with a list:
    limited_status = ar.get_status(path=[opj('sub', 'third'), 'second'])
    eq_(limited_status['untracked'], [opj('sub', 'third')])
    eq_(limited_status['modified'], ['second'])
    ok_(all([len(limited_status[l]) == 0 for l in ('added', 'deleted',
                                                   'type_changed')]))

    # create a subrepo:
    sub = AnnexRepo(opj(ar.path, 'submod'), create=True)
    # nothing changed, it's empty besides .git, which is ignored
    eq_(stat, ar.get_status())

    # file in subrepo
    with open(opj(ar.path, 'submod', 'fourth'), 'w') as f:
        f.write("this is a birth certificate")
    stat['untracked'].append(opj('submod', 'fourth'))
    eq_(stat, ar.get_status())

    # add to subrepo
    sub.add('fourth', commit=True, msg="birther mod init'ed")
    stat['untracked'].remove(opj('submod', 'fourth'))

    if ar.get_active_branch().endswith('(unlocked)') and \
       'adjusted' in ar.get_active_branch():
        # we are running on adjusted branch => do it in submodule, too
        sub.adjust()

    # Note, that now the non-empty repo is untracked
    stat['untracked'].append('submod/')
    eq_(stat, ar.get_status())

    # add the submodule
    ar.add_submodule('submod', url=opj(curdir, 'submod'))

    stat['untracked'].remove('submod/')
    stat['added'].append('.gitmodules')

    # 'submod/' might either be reported as 'added' or 'modified'.
    # Therefore more complex assertions at this point:
    reported_stat = ar.get_status()
    eq_(stat['untracked'], reported_stat['untracked'])
    eq_(stat['deleted'], reported_stat['deleted'])
    eq_(stat['type_changed'], reported_stat['type_changed'])
    ok_(stat['added'] == reported_stat['added'] or
        stat['added'] + ['submod/'] == reported_stat['added'])
    ok_(stat['modified'] == reported_stat['modified'] or
        stat['modified'] + ['submod/'] == reported_stat['modified'])

    # simpler assertion if we ignore submodules:
    eq_(stat, ar.get_status(submodules=False))

    # commit the submodule
    # in direct mode, commit of a removed submodule fails with:
    #  error: unable to index file submod
    #  fatal: updating files failed
    #
    # - this happens, when commit is called with -c core.bare=False
    # - it works when called via annex proxy
    # - if we add a submodule instead of removing one, it's vice versa with
    #   the very same error message

    ar.commit(msg="submodule added", files=['.gitmodules', 'submod'])

    stat['added'].remove('.gitmodules')
    eq_(stat, ar.get_status())

    # add another file to submodule
    with open(opj(ar.path, 'submod', 'not_tracked'), 'w') as f:
        f.write("#LastNightInSweden")
    stat['modified'].append('submod/')
    eq_(stat, ar.get_status())

    # add the untracked file:
    sub.add('not_tracked')
    if sub.is_direct_mode():
        # 'sub' is now considered to be clean; therefore it's not reported as
        # modified upwards
        # This is consistent in a way, but surprising in another ...
        pass
    else:
        eq_(stat, ar.get_status())
    sub.commit(msg="added file not_tracked")
    # 'submod/' still modified when looked at from above:
    eq_(stat, ar.get_status())

    ar.add('submod', git=True)
    ar.commit(msg="submodule modified", files='submod')
    stat['modified'].remove('submod/')
    eq_(stat, ar.get_status())

    # clean again:
    stat = {'untracked': [],
            'deleted': [],
            'modified': [],
            'added': [],
            'type_changed': []}

    ar.add('first', git=True)
    ar.add(opj('sub', 'third'))
    ar.add('fifth')
    sync_wrapper()

    if ar.config.getint("annex", "version") == 6:
        # mixed annexed/not-annexed files ATm can't be committed with explicitly
        # given paths in v6
        # See:
        # http://git-annex.branchable.com/bugs/committing_files_into_git_doesn__39__t_work_with_explicitly_given_paths_in_V6
        ar.commit()
    else:
        super(AnnexRepo, ar).commit(files=['first', 'fifth', opj('sub', 'third'), 'second'])
    eq_(stat, ar.get_status())

    # remove a file in annex:
    ar.remove('fifth')
    stat['deleted'].append('fifth')
    eq_(stat, ar.get_status())

    # remove a file in git:
    ar.remove('first')
    stat['deleted'].append('first')
    eq_(stat, ar.get_status())

    # remove a submodule:
    # rm; git rm; git commit
    from datalad.utils import rmtree
    rmtree(opj(ar.path, 'submod'))
    stat['deleted'].append('submod')
    eq_(stat, ar.get_status())
    # recreate an empty mountpoint, since we currently do it in uninstall:
    os.makedirs(opj(ar.path, 'submod'))
    stat['deleted'].remove('submod')
    eq_(stat, ar.get_status())

    ar.remove('submod')
    # TODO: Why the difference?
    stat['deleted'].append('submod')
    stat['modified'].append('.gitmodules')
    eq_(stat, ar.get_status())

    # Note: Here again we need to use annex-proxy; This contradicts the addition
    # of the very same submodule, which we needed to commit via
    # -c core.bare=False instead. Otherwise the very same failure happens.
    # Just vice versa. See above where 'submod' is added.
    ar.commit("submod removed", files=['submod', '.gitmodules'])
    stat['modified'].remove('.gitmodules')
    stat['deleted'].remove('submod')
    eq_(stat, ar.get_status())


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_AnnexRepo_status(path, path2):

    ar = AnnexRepo(path, create=True)
    _test_status(ar)
    if ar.config.getint("annex", "version") == 6:
        # in case of v6 have a second run with adjusted branch feature:
        ar2 = AnnexRepo(path2, create=True)
        ar2.commit(msg="empty commit to create branch 'master'",
                   options=['--allow-empty'])
        ar2._run_annex_command('adjust', annex_options=['--unlock'])
        _test_status(ar2)



# TODO: test dirty
# TODO: GitRep.dirty
# TODO: test/utils ok_clean_git


@with_tempfile(mkdir=True)
def test_AnnexRepo_set_remote_url(path):

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
def test_wanted(path):
    ar = AnnexRepo(path, create=True)
    eq_(ar.get_wanted(), None)
    # test samples with increasing "trickiness"
    for v in ("standard",
              "include=*.nii.gz or include=*.nii",
              "exclude=archive/* and (include=*.dat or smallerthan=2b)"
              ):
        ar.set_wanted(expr=v)
        eq_(ar.get_wanted(), v)
    # give it some file so clone/checkout works without hiccups
    create_tree(ar.path, {'1.dat': 'content'}); ar.add('1.dat'); ar.commit(msg="blah")
    # make a clone and see if all cool there
    # intentionally clone as pure Git and do not annex init so to see if we
    # are ignoring crummy log msgs
    ar1_path = ar.path + '_1'
    GitRepo.clone(ar.path, ar1_path)
    ar1 = AnnexRepo(ar1_path, init=False)
    eq_(ar1.get_wanted(), None)
    eq_(ar1.get_wanted('origin'), v)
    ar1.set_wanted(expr='standard')
    eq_(ar1.get_wanted(), 'standard')


@with_tempfile(mkdir=True)
def test_AnnexRepo_metadata(path):
    # prelude
    ar = AnnexRepo(path, create=True)
    create_tree(
        path,
        {
            'up.dat': 'content',
            'd o"w n': {
                'd o w n.dat': 'lowcontent'
            }
        })
    ar.add('.', git=False)
    ar.commit('content')
    ok_clean_git(path)
    # fugue
    # doesn't do anything if there is nothing to do
    ar.set_metadata('up.dat')
    eq_({}, ar.get_metadata(None))
    eq_({}, ar.get_metadata(''))
    eq_({}, ar.get_metadata([]))
    eq_({'up.dat': {}}, ar.get_metadata('up.dat'))
    # basic invocation
    eq_(None, ar.set_metadata(
        'up.dat',
        reset={'mike': 'awesome'},
        add={'tag': 'awesome'},
        remove={'tag': 'awesome'},  # cancels prev, just to use it
        init={'virgin': 'true'},
        purge=['nothere']))
    # no timestamps by default
    md = ar.get_metadata('up.dat')
    deq_({'up.dat': {
        'virgin': ['true'],
        'mike': ['awesome']}},
        md)
    # matching timestamp entries for all keys
    md_ts = ar.get_metadata('up.dat', timestamps=True)
    for k in md['up.dat']:
        assert_in('{}-lastchanged'.format(k), md_ts['up.dat'])
    assert_in('lastchanged', md_ts['up.dat'])
    # recursive needs a flag
    assert_raises(CommandError, ar.set_metadata, '.', purge=['virgin'])
    ar.set_metadata('.', purge=['virgin'], recursive=True)
    deq_({'up.dat': {
        'mike': ['awesome']}},
        ar.get_metadata('up.dat'))
    # Use trickier tags (spaces, =)
    ar.set_metadata('.', reset={'tag': 'one and= '}, purge=['mike'], recursive=True)
    playfile = opj('d o"w n', 'd o w n.dat')
    target = {
        'up.dat': {
            'tag': ['one and= ']},
        playfile: {
            'tag': ['one and= ']}}
    deq_(target, ar.get_metadata('.'))
    # incremental work like a set
    ar.set_metadata(playfile, add={'tag': 'one and= '})
    deq_(target, ar.get_metadata('.'))
    ar.set_metadata(playfile, add={'tag': ' two'})
    # returned values are sorted
    eq_([' two', 'one and= '], ar.get_metadata(playfile)[playfile]['tag'])
    # init honor prior values
    ar.set_metadata(playfile, init={'tag': 'three'})
    eq_([' two', 'one and= '], ar.get_metadata(playfile)[playfile]['tag'])
    ar.set_metadata(playfile, remove={'tag': ' two'})
    deq_(target, ar.get_metadata('.'))
    # remove non-existing doesn't error and doesn't change anything
    ar.set_metadata(playfile, remove={'ether': 'best'})
    deq_(target, ar.get_metadata('.'))
    # add works without prior existence
    ar.set_metadata(playfile, add={'novel': 'best'})
    eq_(['best'], ar.get_metadata(playfile)[playfile]['novel'])


@with_tempfile(mkdir=True)
def test_change_description(path):
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


@with_testrepos('basic_annex', flavors=['clone'])
def test_AnnexRepo_get_corresponding_branch(path):

    ar = AnnexRepo(path)

    # we should be on master or a corresponding branch like annex/direct/master
    # respectively if ran in direct mode build.
    # We want to get 'master' in any case
    eq_('master', ar.get_corresponding_branch())

    # special case v6 adjusted branch is not provided by a dedicated build:
    if ar.config.getint("annex", "version") == 6:
        ar.adjust()
        # as above, we still want to get 'master', while being on
        # 'adjusted/master(unlocked)'
        eq_('adjusted/master(unlocked)', ar.get_active_branch())
        eq_('master', ar.get_corresponding_branch())


@with_testrepos('basic_annex', flavors=['clone'])
def test_AnnexRepo_get_tracking_branch(path):

    ar = AnnexRepo(path)

    # we want the relation to original branch, especially in direct mode
    # or even in v6 adjusted branch
    eq_(('origin', 'refs/heads/master'), ar.get_tracking_branch())


@with_testrepos('basic_annex', flavors=['clone'])
def test_AnnexRepo_is_managed_branch(path):

    ar = AnnexRepo(path)

    if ar.is_direct_mode():
        ok_(ar.is_managed_branch())
    else:
        # ATM only direct mode and v6 adjusted branches should return True.
        # Adjusted branch requires a call of git-annex-adjust and shouldn't
        # be the state of a fresh clone
        ok_(not ar.is_managed_branch())
    if ar.config.getint("annex", "version") == 6:
        ar.adjust()
        ok_(ar.is_managed_branch())


@with_tempfile(mkdir=True)
@with_tempfile()
def test_AnnexRepo_flyweight_monitoring_inode(path, store):
    # testing for issue #1512
    check_repo_deals_with_inode_change(AnnexRepo, path, store)
