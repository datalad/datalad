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

import gc
from os.path import exists, islink
from git.exc import GitCommandError
from six import PY3
from six.moves.urllib.parse import urljoin, urlsplit
from shutil import copyfile

from nose.tools import assert_raises, assert_is_instance, assert_true, \
    assert_equal, assert_false, assert_in, assert_not_in

from ..support.annexrepo import AnnexRepo, kwargs_to_options, GitRepo
from ..support.exceptions import CommandNotAvailableError, \
    FileInGitError, FileNotInAnnexError, CommandError, AnnexBatchCommandError
from ..cmd import Runner
from .utils import *


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
    with swallow_logs() as cm:
        assert_raises(GitCommandError, AnnexRepo, dst, src)
        if git.__version__ != "1.0.2":
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
def test_AnnexRepo_annex_add(src, annex_path):

    ar = AnnexRepo(annex_path, src)

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(annex_path, filename)
    f = open(filename_abs, 'w')
    f.write("What to write?")
    f.close()
    out_json = ar.annex_add(filename)
    if not ar.is_direct_mode():
        assert_true(os.path.islink(filename_abs),
                    "Annexed file is not a link.")
    else:
        assert_false(os.path.islink(filename_abs),
                     "Annexed file is link in direct mode.")
    assert_in('key', out_json)
    key = ar.get_file_key(filename)
    assert_false(key == '')
    assert_equal(key, out_json['key'])
    # could test for the actual key, but if there's something
    # and no exception raised, it's fine anyway.


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_annex_proxy(src, annex_path):
    ar = AnnexRepo(annex_path, src)
    ar.set_direct_mode(True)
    ok_clean_git_annex_proxy(path=annex_path)


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


# 1 is enough to test file_has_content
@with_testrepos('.*annex.*', flavors=['local'], count=1)
@with_tempfile
def test_AnnexRepo_file_has_content(src, annex_path):
    ar = AnnexRepo(annex_path, src)
    testfiles = ["test-annex.dat", "test.dat"]
    assert_equal(ar.file_has_content(testfiles), [False, False])

    ok_annex_get(ar, "test-annex.dat")
    assert_equal(ar.file_has_content(testfiles), [True, False])
    assert_equal(ar.file_has_content(testfiles[:1]), [True])

    assert_equal(ar.file_has_content(testfiles + ["bogus.txt"]),
                 [True, False, False])

    assert_false(ar.file_has_content("bogus.txt"))
    assert_true(ar.file_has_content("test-annex.dat"))


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


def test_AnnexRepo_options_decorator():

    @kwargs_to_options
    def decorated(self, whatever, options=[]):
        return options

    # Order is not guaranteed so use sets
    assert_equal(set(decorated(1, 2, someoption='first', someotheroption='second')),
                 {' --someoption=first', ' --someotheroption=second'})


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_annex_add_to_git(src, dst):

    ar = AnnexRepo(dst, src)

    filename = get_most_obscure_supported_name()
    filename_abs = os.path.join(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")

    assert_raises(IOError, ar.get_file_key, filename)
    ar.annex_add_to_git(filename)
    assert_in(filename, ar.get_indexed_files())


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
        ar.annex_addurls([testurl])
    l = ar.annex_whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # output='full'
    lfull = ar.annex_whereis(testfile, output='full')
    assert_equal(set(lfull), set(l))  # the same entries
    non_web_remote = l[1-l.index(ar.WEB_UUID)]
    assert_in('urls', lfull[non_web_remote])
    assert_equal(lfull[non_web_remote]['urls'], [])
    assert_not_in('uuid', lfull[ar.WEB_UUID])  # no uuid in the records
    assert_equal(lfull[ar.WEB_UUID]['urls'], [testurl])

    # output='descriptions'
    ldesc = ar.annex_whereis(testfile, output='descriptions')
    assert_equal(set(ldesc), set([v['description'] for v in lfull.values()]))

    # info
    info = ar.annex_info(testfile)
    assert_equal(info['size'], 14)
    assert(info['key'])  # that it is there
    info_batched = ar.annex_info(testfile, batch=True)
    assert_equal(info, info_batched)
    # while at it ;)
    assert_equal(ar.annex_info('nonexistent', batch=False), None)
    assert_equal(ar.annex_info('nonexistent', batch=True), None)

    # annex repo info
    repo_info = ar.annex_repo_info()
    assert_equal(repo_info['local annex size'], 14)
    assert_equal(repo_info['backend usage'], {'SHA256E': 1})
    #import pprint; pprint.pprint(repo_info)

    # remove the remote
    ar.annex_rmurl(testfile, testurl)
    l = ar.annex_whereis(testfile)
    assert_not_in(ar.WEB_UUID, l)
    assert_equal(len(l), 1)

    # now only 1 copy; drop should fail
    try:
        with swallow_logs() as cml:
            ar.annex_drop(testfile)
            assert_in('ERROR', cml.out)
            assert_in('drop: 1 failed', cml.out)
    except CommandError as e:
        assert_equal(e.code, 1)
        assert_in('Could only verify the '
                  'existence of 0 out of 1 necessary copies', e.stdout)
        failed = True

    assert_true(failed)

    # read the url using different method
    ar.annex_addurl_to_file(testfile, testurl)
    l = ar.annex_whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    assert_equal(len(l), 2)
    assert_true(ar.file_has_content(testfile))

    # 2 known copies now; drop should succeed
    ar.annex_drop(testfile)
    l = ar.annex_whereis(testfile)
    assert_in(ar.WEB_UUID, l)
    assert_equal(len(l), 1)
    assert_false(ar.file_has_content(testfile))
    lfull = ar.annex_whereis(testfile, output='full')
    assert_not_in(non_web_remote, lfull) # not present -- so not even listed

    # multiple files/urls
    # get the file from remote
    with swallow_outputs() as cmo:
        ar.annex_addurls([testurl2])

    # TODO: if we ask for whereis on all files, we should get for all files
    lall = ar.annex_whereis('.')
    assert_equal(len(lall), 2)
    for e in lall:
        assert(isinstance(e, list))
    # but we don't know which one for which file. need a 'full' one for that
    lall_full = ar.annex_whereis('.', output='full')
    assert_true(ar.file_has_content(testfile2))
    assert_true(lall_full[testfile2][non_web_remote]['here'])
    assert_equal(set(lall_full), {testfile, testfile2})

    # add a bogus 2nd url to testfile

    someurl = "http://example.com/someurl"
    ar.annex_addurl_to_file(testfile, someurl, options=['--relaxed'])
    lfull = ar.annex_whereis(testfile, output='full')
    assert_equal(set(lfull[ar.WEB_UUID]['urls']), {testurl, someurl})

    # and now test with a file in subdirectory
    subdir = opj(dst, 'd')
    os.mkdir(subdir)
    with swallow_outputs() as cmo:
        ar.annex_addurl_to_file(testfile3, url=testurl3)
    ok_file_has_content(opj(dst, testfile3), 'more stuff')
    assert_equal(set(ar.annex_whereis(testfile3)), {ar.WEB_UUID, non_web_remote})
    assert_equal(set(ar.annex_whereis(testfile3, output='full').keys()), {ar.WEB_UUID, non_web_remote})

    # and if we ask for both files
    info2 = ar.annex_info([testfile, testfile3])
    assert_equal(set(info2), {testfile, testfile3})
    assert_equal(info2[testfile3]['size'], 10)

    # which would work even if we cd to that subdir, but then we should use explicit curdir
    with chpwd(subdir):
        cur_subfile = opj(curdir, 'sub.txt')
        assert_equal(set(ar.annex_whereis(cur_subfile)), {ar.WEB_UUID, non_web_remote})
        assert_equal(set(ar.annex_whereis(cur_subfile, output='full').keys()), {ar.WEB_UUID, non_web_remote})
        testfiles = [cur_subfile, opj(pardir, testfile)]
        info2_ = ar.annex_info(testfiles)
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

    ar.annex_add(filename, backend='MD5')
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
    annex.add_to_annex(files)
    print({f: annex.get_file_key(f) for f in files})


@with_batch_direct
@with_tree(**tree1args)
def test_dropkey(batch, direct, path):
    kw = {'batch': batch}
    annex = AnnexRepo(path, init=True, backend='MD5E', direct=direct)
    files = list(tree1_md5e_keys)
    annex.add_to_annex(files)
    # drop one key
    annex.annex_dropkey(tree1_md5e_keys[files[0]], **kw)
    # drop multiple
    annex.annex_dropkey([tree1_md5e_keys[f] for f in files[1:3]], **kw)
    # drop already dropped -- should work as well atm
    # https://git-annex.branchable.com/bugs/dropkey_--batch_--json_--force_is_always_succesfull
    annex.annex_dropkey(tree1_md5e_keys[files[0]], **kw)
    # and a mix with already dropped or not
    annex.annex_dropkey(list(tree1_md5e_keys.values()), **kw)


@with_tree(**tree1args)
@serve_path_via_http()
def test_AnnexRepo_backend_option(path, url):
    ar = AnnexRepo(path, backend='MD5')

    ar.annex_add('firstfile', backend='SHA1')
    ar.annex_add('secondfile')
    assert_equal(ar.get_file_backend('firstfile'), 'SHA1')
    assert_equal(ar.get_file_backend('secondfile'), 'MD5')

    with swallow_outputs() as cmo:
        # must be added under different name since annex 20160114
        ar.annex_addurl_to_file('remotefile2', url + 'remotefile', backend='SHA1')
    assert_equal(ar.get_file_backend('remotefile2'), 'SHA1')

    with swallow_outputs() as cmo:
        ar.annex_addurls([url + 'faraway'], backend='SHA1')
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
    repo.annex_add(file1)

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
    repo.annex_add(file2)

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
        annex.annex_get('test-annex.dat')
        assert_true(annex.file_has_content('test-annex.dat'))


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_commit(src, path):

    ds = AnnexRepo(path, src)
    filename = opj(path, get_most_obscure_supported_name())
    with open(filename, 'w') as f:
        f.write("File to add to git")
    ds.annex_add(filename)

    if ds.is_direct_mode():
        assert_raises(AssertionError, ok_clean_git_annex_proxy, path)
    else:
        assert_raises(AssertionError, ok_clean_git, path, annex=True)

    ds.commit("test _commit")
    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(path)
    else:
        ok_clean_git(path, annex=True)


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_add_to_git(src, dst):

    ds = AnnexRepo(dst, src)

    filename = get_most_obscure_supported_name()
    filename_abs = opj(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_git(filename_abs)

    if ds.is_direct_mode():
        ok_clean_git_annex_proxy(dst)
    else:
        ok_clean_git(dst, annex=True)
    ok_file_under_git(dst, filename)
    assert_raises(FileInGitError, ds.get_file_key, filename)


@assert_cwd_unchanged
@with_testrepos('.*annex.*', flavors=local_testrepo_flavors)
@with_tempfile
def test_AnnexRepo_add_to_annex(src, dst):

    ds = AnnexRepo(dst, src)
    filename = get_most_obscure_supported_name()
    filename_abs = opj(dst, filename)
    with open(filename_abs, 'w') as f:
        f.write("What to write?")
    ds.add_to_annex(filename)

    if not ds.is_direct_mode():
        assert_true(islink(filename_abs),
                    "Annexed file is not a link.")
        ok_clean_git(dst, annex=True)
    else:
        assert_false(islink(filename_abs),
                     "Annexed file is link in direct mode.")
        ok_clean_git_annex_proxy(dst)

    key = ds.get_file_key(filename)
    assert_false(key == '')
    # could test for the actual key, but if there's something and no
    # exception raised, it's fine anyway.


@ignore_nose_capturing_stdout
@with_testrepos('.*annex.*', flavors=['local', 'network'])
@with_tempfile
def test_AnnexRepo_get(src, dst):

    ds = AnnexRepo(dst, src)
    assert_is_instance(ds, AnnexRepo, "AnnexRepo was not created.")
    testfile = 'test-annex.dat'
    testfile_abs = opj(dst, testfile)
    assert_false(ds.file_has_content("test-annex.dat"))
    with swallow_outputs() as cmo:
        ds.get(testfile)
    assert_true(ds.file_has_content("test-annex.dat"))
    f = open(testfile_abs, 'r')
    assert_equal(f.readlines(), ['123\n'],
                 "test-annex.dat's content doesn't match.")


# TODO:
#def annex_initremote(self, name, options):
#def annex_enableremote(self, name):

@with_testrepos('basic_annex$', flavors=['clone'])
def _test_AnnexRepo_get_contentlocation(batch, path):
    annex = AnnexRepo(path, create=False, init=False)
    fname = 'test-annex.dat'
    key = annex.get_file_key(fname)
    # TODO: see if we can avoid this or specify custom exception
    assert_equal(annex.get_contentlocation(key, batch=batch), '')

    with swallow_outputs() as cmo:
        annex.annex_get(fname)
    key_location = annex.get_contentlocation(key, batch=batch)
    assert(key_location)
    # they both should point to the same location eventually
    eq_(os.path.realpath(opj(annex.path, fname)),
        os.path.realpath(opj(annex.path, key_location)))

    # TODO: test how it would look if done under a subdir
    with chpwd('subdir', mkdir=True):
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
        ar.annex_addurl_to_file(testfile, testurl, batch=True)

    # Remove it and re-add
    os.unlink(opj(dst, testfile))
    ar.annex_addurl_to_file(testfile, testurl, batch=True)

    info = ar.annex_info(testfile)
    assert_equal(info['size'], 14)
    assert(info['key'])
    # not even added to index yet since we this repo is with default batch_size
    assert_not_in(ar.WEB_UUID, ar.annex_whereis(testfile))

    # TODO: none of the below should re-initiate the batch process

    # add to an existing and staged annex file
    copyfile(opj(sitepath, 'about2.txt'), opj(dst, testfile2))
    ar.annex_add(testfile2)
    ar.annex_addurl_to_file(testfile2, testurl2, batch=True)
    assert(ar.annex_info(testfile2))
    # not committed yet
    # assert_in(ar.WEB_UUID, ar.annex_whereis(testfile2))

    # add to an existing and committed annex file
    copyfile(opj(sitepath, 'about2_.txt'), opj(dst, testfile2_))
    ar.annex_add(testfile2_)
    assert_not_in(ar.WEB_UUID, ar.annex_whereis(testfile))
    ar.commit("added about2_.txt and there was about2.txt lingering around")
    # commit causes closing all batched annexes, so testfile gets committed
    assert_in(ar.WEB_UUID, ar.annex_whereis(testfile))
    assert(not ar.dirty)
    ar.annex_addurl_to_file(testfile2_, testurl2_, batch=True)
    assert(ar.annex_info(testfile2_))
    assert_in(ar.WEB_UUID, ar.annex_whereis(testfile2_))

    # add into a new file
    #filename = 'newfile.dat'
    filename = get_most_obscure_supported_name()
    ar2 = AnnexRepo(dst, batch_size=1)
    with swallow_outputs():
        assert_equal(len(ar2._batched), 0)
        ar2.annex_addurl_to_file(filename, testurl, batch=True)
        assert_equal(len(ar2._batched), 1)  # we added one more with batch_size=1
    ar2.commit("added new file")  # would do nothing ATM, but also doesn't fail
    assert_in(filename, ar2.git_get_files())
    assert_in(ar.WEB_UUID, ar2.annex_whereis(filename))

    ar.commit("actually committing new files")
    assert_in(filename, ar.git_get_files())
    assert_in(ar.WEB_UUID, ar.annex_whereis(filename))
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
