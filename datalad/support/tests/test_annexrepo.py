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

import mock
from functools import partial
from os import mkdir

from six.moves.urllib.parse import urljoin
from six.moves.urllib.parse import urlsplit
from shutil import copyfile
from nose.tools import assert_is_instance

from datalad.utils import linux_distribution_name
from datalad.tests.utils import *
from datalad.support.exceptions import MissingExternalDependency
from datalad.support.exceptions import OutdatedExternalDependency

# imports from same module:
from ..annexrepo import *


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_instance_from_clone(src, dst):

    ar = AnnexRepo(dst, src)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(dst, '.git', 'annex')))

    # do it again should raise GitCommandError since git will notice
    # there's already a git-repo at that path and therefore can't clone to `dst`
    with swallow_logs(new_level=logging.WARN) as cm:
        assert_raises(GitCommandError, AnnexRepo, dst, src)
        if git.__version__ != "1.0.2" and git.__version__ != "2.0.5":
            assert("already exists" in cm.out)


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
def test_AnnexRepo_instance_from_existing(path):

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@ignore_nose_capturing_stdout
@assert_cwd_unchanged
@with_tempfile
def test_AnnexRepo_instance_brand_new(path):

    GitRepo(path)
    assert_raises(RuntimeError, AnnexRepo, path, create=False)

    ar = AnnexRepo(path)
    assert_is_instance(ar, AnnexRepo, "AnnexRepo was not created.")
    assert_true(os.path.exists(os.path.join(path, '.git')))


@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_crippled_filesystem(src, dst):

    ar = AnnexRepo(dst, src)

    # fake git-annex entries in .git/config:
    writer = ar.repo.config_writer()
    writer.set_value("annex", "crippledfilesystem", True)
    writer.release()
    assert_true(ar.is_crippled_fs())
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
    dm = ar.is_direct_mode()

    # by default annex should be in direct mode on crippled filesystem and
    # on windows:
    if ar.is_crippled_fs() or on_windows:
        assert_true(dm)
    else:
        assert_false(dm)


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
        assert_true(dm)
    else:
        assert_false(dm)


@assert_cwd_unchanged
@with_testrepos('.*annex.*')
@with_tempfile
def test_AnnexRepo_set_direct_mode(src, dst):

    ar = AnnexRepo(dst, src)
    ar.set_direct_mode(True)
    assert_true(ar.is_direct_mode(), "Switching to direct mode failed.")
    if ar.is_crippled_fs():
        assert_raises(CommandNotAvailableError, ar.set_direct_mode, False)
        assert_true(ar.is_direct_mode(),
            "Indirect mode on crippled fs detected. Shouldn't be possible.")
    else:
        ar.set_direct_mode(False)
        assert_false(ar.is_direct_mode(), "Switching to indirect mode failed.")


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):
    ar = AnnexRepo(annex_path, src)
    ar.set_direct_mode(True)
    ok_clean_git_annex_proxy(path=annex_path)

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

    ar = AnnexRepo(annex_path, src)

    # test-annex.dat should return the correct key:
    assert_equal(
        ar.get_file_key("test-annex.dat"),
        'SHA256E-s4--181210f8f9c779c26da1d9b2075bde0127302ee0e3fca38c9a83f5b1dd8e5d3b.dat')

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
    assert_equal(exc.sizemore_msg, '905.6 MB')
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
    ar = AnnexRepo(annex_path, src, direct=direct)
    testfiles = ["test-annex.dat", "test.dat"]

    assert_equal(ar.file_has_content(testfiles), [False, False])

    ok_annex_get(ar, "test-annex.dat")
    assert_equal(ar.file_has_content(testfiles, batch=batch), [True, False])
    assert_equal(ar.file_has_content(testfiles[:1], batch=batch), [True])

    assert_equal(ar.file_has_content(testfiles + ["bogus.txt"], batch=batch),
                 [True, False, False])

    assert_false(ar.file_has_content("bogus.txt", batch=batch))
    assert_true(ar.file_has_content("test-annex.dat", batch=batch))


# 1 is enough to test
@with_batch_direct
@with_testrepos('.*annex.*', flavors=['local'], count=1)
@with_tempfile
def test_AnnexRepo_is_under_annex(batch, direct, src, annex_path):
    ar = AnnexRepo(annex_path, src, direct=direct)

    with open(opj(annex_path, 'not-committed.txt'), 'w') as f:
        f.write("aaa")

    testfiles = ["test-annex.dat", "not-committed.txt", "INFO.txt"]
    # wouldn't change
    target_value = [True, False, False]
    assert_equal(ar.is_under_annex(testfiles, batch=batch), target_value)

    ok_annex_get(ar, "test-annex.dat")
    assert_equal(ar.is_under_annex(testfiles, batch=batch), target_value)
    assert_equal(ar.is_under_annex(testfiles[:1], batch=batch), target_value[:1])
    assert_equal(ar.is_under_annex(testfiles[1:], batch=batch), target_value[1:])

    assert_equal(ar.is_under_annex(testfiles + ["bogus.txt"], batch=batch),
                 target_value + [False])

    assert_false(ar.is_under_annex("bogus.txt", batch=batch))
    assert_true(ar.is_under_annex("test-annex.dat", batch=batch))


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
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # output='full'
    lfull = ar.whereis(testfile, output='full')
    assert_equal(set(lfull), set(l))  # the same entries
    non_web_remote = l[1-l.index(ar.WEB_UUID)]
    assert_in('urls', lfull[non_web_remote])
    assert_equal(lfull[non_web_remote]['urls'], [])
    assert_not_in('uuid', lfull[ar.WEB_UUID])  # no uuid in the records
    assert_equal(lfull[ar.WEB_UUID]['urls'], [testurl])

    # output='descriptions'
    ldesc = ar.whereis(testfile, output='descriptions')
    assert_equal(set(ldesc), set([v['description'] for v in lfull.values()]))

    # info w/ and w/o fast mode
    for fast in [True, False]:
        info = ar.info(testfile, fast=fast)
        assert_equal(info['size'], 14)
        assert(info['key'])  # that it is there
        info_batched = ar.info(testfile, batch=True, fast=fast)
        assert_equal(info, info_batched)
        # while at it ;)
        assert_equal(ar.info('nonexistent', batch=False), None)
        assert_equal(ar.info('nonexistent', batch=True), None)

    # annex repo info
    repo_info = ar.repo_info(fast=False)
    assert_equal(repo_info['local annex size'], 14)
    assert_equal(repo_info['backend usage'], {'SHA256E': 1})
    # annex repo info in fast mode
    repo_info_fast = ar.repo_info(fast=True)
    # doesn't give much testable info, so just comparing a subset for match with repo_info info
    assert_equal(repo_info_fast['semitrusted repositories'], repo_info['semitrusted repositories'])
    #import pprint; pprint.pprint(repo_info)

    # remove the remote
    ar.rm_url(testfile, testurl)
    l = ar.whereis(testfile)
    assert_not_in(ar.WEB_UUID, l)
    assert_equal(len(l), 1)

    # now only 1 copy; drop should fail
    try:
        with swallow_logs() as cml:
            ar.drop(testfile)
            assert_in('ERROR', cml.out)
            assert_in('drop: 1 failed', cml.out)
    except CommandError as e:
        assert_equal(e.code, 1)
        assert_in('Could only verify the '
                  'existence of 0 out of 1 necessary copies', e.stdout)
        failed = True

    assert_true(failed)

    # read the url using different method
    ar.add_url_to_file(testfile, testurl)
    l = ar.whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # 2 known copies now; drop should succeed
    ar.drop(testfile)
    l = ar.whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    assert_equal(len(l), 1)
    assert_false(ar.file_has_content(testfile))
    lfull = ar.whereis(testfile, output='full')
    assert_not_in(non_web_remote, lfull) # not present -- so not even listed

    # multiple files/urls
    # get the file from remote
    with swallow_outputs() as cmo:
        ar.add_urls([testurl2])

    # TODO: if we ask for whereis on all files, we should get for all files
    lall = ar.whereis('.')
    assert_equal(len(lall), 2)
    for e in lall:
        assert(isinstance(e, list))
    # but we don't know which one for which file. need a 'full' one for that
    lall_full = ar.whereis('.', output='full')
    assert_true(ar.file_has_content(testfile2))
    assert_true(lall_full[testfile2][non_web_remote]['here'])
    assert_equal(set(lall_full), {testfile, testfile2})

    # add a bogus 2nd url to testfile

    someurl = "http://example.com/someurl"
    ar.add_url_to_file(testfile, someurl, options=['--relaxed'])
    lfull = ar.whereis(testfile, output='full')
    assert_equal(set(lfull[ar.WEB_UUID]['urls']), {testurl, someurl})

    # and now test with a file in subdirectory
    subdir = opj(dst, 'd')
    os.mkdir(subdir)
    with swallow_outputs() as cmo:
        ar.add_url_to_file(testfile3, url=testurl3)
    ok_file_has_content(opj(dst, testfile3), 'more stuff')
    assert_equal(set(ar.whereis(testfile3)), {ar.WEB_UUID, non_web_remote})
    assert_equal(set(ar.whereis(testfile3, output='full').keys()), {ar.WEB_UUID, non_web_remote})

    # and if we ask for both files
    info2 = ar.info([testfile, testfile3])
    assert_equal(set(info2), {testfile, testfile3})
    assert_equal(info2[testfile3]['size'], 10)

    # which would work even if we cd to that subdir, but then we should use explicit curdir
    with chpwd(subdir):
        cur_subfile = opj(curdir, 'sub.txt')
        assert_equal(set(ar.whereis(cur_subfile)), {ar.WEB_UUID, non_web_remote})
        assert_equal(set(ar.whereis(cur_subfile, output='full').keys()), {ar.WEB_UUID, non_web_remote})
        testfiles = [cur_subfile, opj(pardir, testfile)]
        info2_ = ar.info(testfiles)
        # Should maintain original relative file names
        assert_equal(set(info2_), set(testfiles))
        assert_equal(info2_[cur_subfile]['size'], 10)


@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_AnnexRepo_migrating_backends(src, dst):
    ar = AnnexRepo(dst, src, backend='MD5')
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
    assert_equal(ar.get_file_backend(filename), 'MD5')
    assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')

    # migrating will only do, if file is present
    ok_annex_get(ar, 'test-annex.dat')

    if ar.is_direct_mode():
        # No migration in direct mode
        assert_raises(CommandNotAvailableError, ar.migrate_backend,
                      'test-annex.dat')
    else:
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')
        ar.migrate_backend('test-annex.dat')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'MD5')

        ar.migrate_backend('', backend='SHA1')
        assert_equal(ar.get_file_backend(filename), 'SHA1')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA1')


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
    assert_equal(ar.get_file_backend('firstfile'), 'SHA1')
    assert_equal(ar.get_file_backend('secondfile'), 'MD5')

    with swallow_outputs() as cmo:
        # must be added under different name since annex 20160114
        ar.add_url_to_file('remotefile2', url + 'remotefile', backend='SHA1')
    assert_equal(ar.get_file_backend('remotefile2'), 'SHA1')

    with swallow_outputs() as cmo:
        ar.add_urls([url + 'faraway'], backend='SHA1')
    # TODO: what's the annex-generated name of this?
    # For now, workaround:
    assert_true(ar.get_file_backend(f) == 'SHA1'
                for f in ar.get_indexed_files() if 'faraway' in f)


@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_get_file_backend(src, dst):
    #init local test-annex before cloning:
    AnnexRepo(src)

    ar = AnnexRepo(dst, src)

    assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA256E')
    if not ar.is_direct_mode():
        # no migration in direct mode
        ok_annex_get(ar, 'test-annex.dat', network=False)
        ar.migrate_backend('test-annex.dat', backend='SHA1')
        assert_equal(ar.get_file_backend('test-annex.dat'), 'SHA1')
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
    assert_equal(len(out_list), 1)
    assert_in(file1, out_list[0])
    # check git log of git-annex branch:
    # expected: initial creation, update (by annex add) and another
    # update (by annex log)
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 3)

    repo.always_commit = False
    repo.add(file2)

    # No additional git commit:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 3)

    repo.always_commit = True

    # Still one commit only in git-annex log,
    # but 'git annex log' was called when always_commit was true again,
    # so it should commit the addition at the end. Calling it again should then
    # show two commits.
    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    assert_equal(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in("recording state in git", out_list[1])

    out, err = repo._run_annex_command('log')
    out_list = out.rstrip(os.linesep).splitlines()
    assert_equal(len(out_list), 2, "Output:\n%s" % out_list)
    assert_in(file1, out_list[0])
    assert_in(file2, out_list[1])

    # Now git knows as well:
    out, err = runner.run(['git', 'log', 'git-annex'])
    num_commits = len([commit
                       for commit in out.rstrip(os.linesep).split('\n')
                       if commit.startswith('commit')])
    assert_equal(num_commits, 4)


@with_testrepos('basic_annex', flavors=['clone'])
def test_AnnexRepo_on_uninited_annex(path):
    assert_false(exists(opj(path, '.git', 'annex'))) # must not be there for this test to be valid
    annex = AnnexRepo(path, create=False, init=False)  # so we can initialize without
    # and still can get our things
    assert_false(annex.file_has_content('test-annex.dat'))
    with swallow_outputs():
        annex.get('test-annex.dat')
        assert_true(annex.file_has_content('test-annex.dat'))


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_commit(src, path):

    ds = AnnexRepo(path, src)
    filename = opj(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.add(filename, git=True)

    if ds.is_direct_mode():
        assert_raises(AssertionError, ok_clean_git_annex_proxy, path)
    else:
        assert_raises(AssertionError, ok_clean_git, path, annex=True)

    ds.commit("test _commit")
    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(path)
    else:
        ok_clean_git(path, annex=True)


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_AnnexRepo_add_to_annex(path_1, path_2):

    # Note: Some test repos appears to not be initialized.
    #       Therefore: 'init=True'
    # TODO: Fix these repos finally!

    # Note: For now running twice to test direct mode.
    #       Eventually this should implicitly be tested by a proper testrepo
    #       setup and by running the tests on different filesystem, where direct
    #       mode is implied.

    # first clone as provided by with_testrepos:
    r1 = AnnexRepo(path_1, create=False, init=True)
    # additional second clone for direct mode:
    r2 = AnnexRepo(path_2, path_1, create=True)
    r2.set_direct_mode()

    for repo in [r1, r2]:
        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)
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
        ok_(repo.repo.is_dirty())

        repo.commit("Added file to annex.")
        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)

        # now using commit/msg options:
        filename = "another.txt"
        with open(opj(repo.path, filename), "w") as f:
            f.write("something else")

        repo.add(filename, commit=True, msg="Added another file to annex.")
        # known to annex:
        ok_(repo.get_file_key(filename))
        ok_(repo.file_has_content(filename))

        # and committed:
        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_AnnexRepo_add_to_git(path_1, path_2):

    # Note: Some test repos appears to not be initialized.
    #       Therefore: 'init=True'
    # TODO: Fix these repos finally!

        # Note: For now running twice to test direct mode.
    #       Eventually this should implicitly be tested by a proper testrepo
    #       setup and by running the tests on different filesystem, where direct
    #       mode is implied.

    # first clone as provided by with_testrepos:
    r1 = AnnexRepo(path_1, create=False, init=True)
    # additional second clone for direct mode:
    r2 = AnnexRepo(path_2, path_1, create=True)
    r2.set_direct_mode()

    for repo in [r1, r2]:

        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)
        filename = get_most_obscure_supported_name()
        with open(opj(repo.path, filename), "w") as f:
            f.write("some")
        repo.add(filename, git=True)

        # not in annex, but in git:
        assert_raises(FileInGitError, repo.get_file_key, filename)
        # uncommitted:
        ok_(repo.repo.is_dirty())
        repo.commit("Added file to annex.")
        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)

        # now using commit/msg options:
        filename = "another.txt"
        with open(opj(repo.path, filename), "w") as f:
            f.write("something else")

        repo.add(filename, git=True, commit=True,
                 msg="Added another file to annex.")
        # not in annex, but in git:
        assert_raises(FileInGitError, repo.get_file_key, filename)

        # and committed:
        if repo.is_direct_mode():
            ok_clean_git_annex_proxy(repo.path)
        else:
            ok_clean_git(repo.path, annex=True)


@ignore_nose_capturing_stdout
@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_AnnexRepo_get(src, dst):

    annex = AnnexRepo(dst, src)
    assert_is_instance(annex, AnnexRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = opj(dst, testfile)
    assert_false(annex.file_has_content("test-annex.dat"))
    with swallow_outputs():
        annex.get(testfile)
    assert_true(annex.file_has_content("test-annex.dat"))
    ok_file_has_content(testfile_abs, '123', strip=True)

    called = []
    # for some reason yoh failed mock to properly just call original func
    orig_run = annex._run_annex_command_json

    def check_run(cmd, args, **kwargs):
        called.append(cmd)
        if cmd == 'find':
            assert_not_in('-J5', args)
        elif cmd == 'get':
            assert_in('-J5', args)
        else:
            raise AssertionError(
                "no other commands so far should be ran. Got %s, %s" %
                (cmd, args)
            )
        return orig_run(cmd, args, **kwargs)

    annex.drop(testfile)
    with patch.object(AnnexRepo, '_run_annex_command_json',
                      side_effect=check_run, auto_spec=True), \
            swallow_outputs():
        annex.get(testfile, jobs=5)
    assert_equal(called, ['find', 'get'])
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
    assert_equal(annex.get_contentlocation(key, batch=batch), '')

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
    assert_equal(info['size'], 14)
    assert(info['key'])
    # not even added to index yet since we this repo is with default batch_size
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
    assert_not_in(ar.WEB_UUID, ar.whereis(testfile))
    ar.commit("added about2_.txt and there was about2.txt lingering around")
    # commit causes closing all batched annexes, so testfile gets committed
    assert_in(ar.WEB_UUID, ar.whereis(testfile))
    assert(not ar.dirty)
    ar.add_url_to_file(testfile2_, testurl2_, batch=True)
    assert(ar.info(testfile2_))
    assert_in(ar.WEB_UUID, ar.whereis(testfile2_))

    # add into a new file
    #filename = 'newfile.dat'
    filename = get_most_obscure_supported_name()
    ar2 = AnnexRepo(dst, batch_size=1)
    with swallow_outputs():
        assert_equal(len(ar2._batched), 0)
        ar2.add_url_to_file(filename, testurl, batch=True)
        assert_equal(len(ar2._batched), 1)  # we added one more with batch_size=1
    ar2.commit("added new file")  # would do nothing ATM, but also doesn't fail
    assert_in(filename, ar2.get_files())
    assert_in(ar.WEB_UUID, ar2.whereis(filename))

    ar.commit("actually committing new files")
    assert_in(filename, ar.get_files())
    assert_in(ar.WEB_UUID, ar.whereis(filename))
    # this poor bugger still wasn't added since we used default batch_size=0 on him

    # and closing the pipes now shoudn't anyhow affect things
    assert_equal(len(ar._batched), 1)
    ar._batched.close()
    assert_equal(len(ar._batched), 1)  # doesn't remove them, just closes
    assert(not ar.dirty)

    ar._batched.clear()
    assert_equal(len(ar._batched), 0)  # .clear also removes

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
    socket_1 = opj(ssh_manager.socket_dir, 'datalad-test')
    socket_2 = opj(ssh_manager.socket_dir, 'localhost')
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

    # remote interaction causes socket to be created:
    try:
        # Note: For some reason, it hangs if log_stdout/err True
        # TODO: Figure out what's going on
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
        # Note: For some reason, it hangs if log_stdout/err True
        # TODO: Figure out what's going on
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
    ar2 = AnnexRepo(path2, path1, create=True, direct=True)

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
def test_repo_version(path):
    annex = AnnexRepo(path, create=True, version=6)
    ok_clean_git(path, annex=True)
    version = annex.repo.config_reader().get_value('annex', 'version')
    eq_(version, 6)


@with_testrepos('.*annex.*', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_annex_copy_to(origin, clone):
    repo = AnnexRepo(origin, create=False)
    remote = AnnexRepo(clone, origin, create=True)
    repo.add_remote("target", clone)

    assert_raises(IOError, repo.copy_to, "doesnt_exist.dat", "target")
    assert_raises(FileInGitError, repo.copy_to, "INFO.txt", "target")
    assert_raises(ValueError, repo.copy_to, "test-annex.dat", "invalid_target")

    # test-annex.dat has no content to copy yet:
    eq_(repo.copy_to("test-annex.dat", "target"), [])

    repo.get("test-annex.dat")
    # now it has:
    eq_(repo.copy_to("test-annex.dat", "target"), ["test-annex.dat"])
    eq_(repo.copy_to(["INFO.txt", "test-annex.dat"], "target"), ["test-annex.dat"])


@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_annex_drop(src, dst):
    ar = AnnexRepo(dst, src)
    testfile = 'test-annex.dat'
    assert_false(ar.file_has_content(testfile))
    ar.get(testfile)
    ok_(ar.file_has_content(testfile))

    # drop file by name:
    result = ar.drop([testfile])
    assert_false(ar.file_has_content(testfile))
    ok_(isinstance(result, list))
    eq_(result[0], testfile)
    eq_(len(result), 1)

    ar.get(testfile)

    # drop file by key:
    testkey = ar.get_file_key(testfile)
    result = ar.drop([testkey], key=True)
    assert_false(ar.file_has_content(testfile))
    ok_(isinstance(result, list))
    eq_(result[0], testkey)
    eq_(len(result), 1)

    # insufficient arguments:
    assert_raises(TypeError, ar.drop)
    assert_raises(InsufficientArgumentsError, ar.drop, [], options=["--jobs=5"])
    assert_raises(InsufficientArgumentsError, ar.drop, [])

    # too much arguments:
    assert_raises(CommandError, ar.drop, ['.'], options=['--all'])


@with_testrepos('basic_annex', flavors=['clone'])
@with_tempfile(mkdir=True)
def test_annex_remove(path1, path2):
    ar1 = AnnexRepo(path1, create=False)
    ar2 = AnnexRepo(path2, path1, create=True, direct=True)

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
    #with swallow_logs(), swallow_outputs():  # it will complain!
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
    assert_false(ar.repo.is_dirty(
        index=True, working_tree=True, untracked_files=True, submodules=True))
    os.makedirs(opj(ar.path, '.datalad'))
    # we don't care about empty directories
    assert_false(ar.repo.is_dirty(
        index=True, working_tree=True, untracked_files=True, submodules=True))
    with open(opj(ar.path, '.datalad', 'somefile'), 'w') as f:
        f.write('some content')
    # make sure the repo is considered dirty now
    assert_true(ar.repo.is_dirty(
        index=False, working_tree=False, untracked_files=True, submodules=False))
    # no file is being added, as dotfiles/directories are ignored by default
    ar.add('.', git=False)
    # double check, still dirty
    assert_true(ar.repo.is_dirty(
        index=False, working_tree=False, untracked_files=True, submodules=False))
    # now add to git, and it should work
    ar.add('.', git=True)
    # all in index
    assert_false(ar.repo.is_dirty(
        index=False, working_tree=True, untracked_files=True, submodules=True))
    ar.commit(msg="some")
    # all committed
    assert_false(ar.repo.is_dirty(
        index=True, working_tree=True, untracked_files=True, submodules=True))
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
                AnnexRepo(path)
            if linux_distribution_name == 'debian':
                assert_in("http://neuro.debian.net", str(cme.exception))
            eq_(AnnexRepo.git_annex_version, None)

        # outdated git-annex at all
        with patch.object(
                external_versions, '_versions', {'cmd:annex': '6.20160505'}):
            eq_(AnnexRepo.git_annex_version, None)
            assert_raises(OutdatedExternalDependency, AnnexRepo, path)
            # and we don't assign it
            eq_(AnnexRepo.git_annex_version, None)
            # so we could still fail
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
            assert_equal(proc(l), l)
            assert_equal(proc.pbars, {})
            assert_equal(cmo.out, '')
            assert_equal(cmo.err, '')
    # should process progress lines
    assert_equal(proc(progress_lines[0]), None)
    assert_equal(len(proc.pbars), 1)
    # but when we finish download -- should get cleared
    assert_equal(proc(success_lines[0]), success_lines[0])
    assert_equal(proc.pbars, {})
    # and no side-effect of any kind in finish
    assert_equal(proc.finish(), None)

    proc = ProcessAnnexProgressIndicators(expected={'key1': 100, 'key2': None})
    # when without any target downloads, there is no total_pbar
    assert(proc.total_pbar is not None)
    assert_equal(proc.total_pbar._pbar.total, 100)  # as much as it knows at this point
    # for regular lines -- should still just return them without side-effects
    for l in irrelevant_lines:
        with swallow_outputs() as cmo:
            assert_equal(proc(l), l)
            assert_equal(proc.pbars, {})
            assert_equal(cmo.out, '')
            assert_equal(cmo.err, '')
    # should process progress lines
    # it doesn't swallow everything -- so there will be side-effects in output
    with swallow_outputs() as cmo:
        assert_equal(proc(progress_lines[0]), None)
        assert_equal(len(proc.pbars), 1)
        # but when we finish download -- should get cleared
        assert_equal(proc(success_lines[0]), success_lines[0])
        assert_equal(proc.pbars, {})
        out = cmo.out
    assert out  # just assert that something was output
    assert proc.total_pbar is not None
    # and no side-effect of any kind in finish
    with swallow_outputs() as cmo:
        assert_equal(proc.finish(), None)
        assert_equal(proc.total_pbar, None)


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
    assert_equal(annex2.get_description(), 'custom 2')
    # not yet known
    assert_equal(annex2.get_description(uuid=annex1.uuid), None)

    annex2.add_remote('annex1', path1)
    annex2.fetch('annex1')
    # it will match the remote name
    assert_equal(annex2.get_description(uuid=annex1.uuid),
                 annex1_description + ' [annex1]')
    # but let's remove the remote
    annex1.merge_annex('annex1')
    annex2.remove_remote('annex1')
    assert_equal(annex2.get_description(uuid=annex1.uuid), annex1_description)
