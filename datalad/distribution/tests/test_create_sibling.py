# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test create publication target ssh web server action

"""

import logging
import os
import stat
import sys
from os import chmod
from os.path import (
    basename,
    exists,
)
from os.path import join as opj

import pytest

from datalad.api import (
    create_sibling,
    install,
    push,
)
from datalad.cmd import StdOutErrCapture
from datalad.cmd import WitlessRunner as Runner
from datalad.distribution.create_sibling import _RunnerAdapter
from datalad.support.annexrepo import AnnexRepo
from datalad.support.exceptions import (
    CommandError,
    InsufficientArgumentsError,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.network import urlquote
from datalad.tests.utils_pytest import (
    DEFAULT_BRANCH,
    DEFAULT_REMOTE,
    SkipTest,
    assert_dict_equal,
    assert_false,
    assert_in,
    assert_in_results,
    assert_no_errors_logged,
    assert_not_equal,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    create_tree,
    eq_,
    get_mtimes_and_digests,
    get_ssh_port,
    known_failure_windows,
    ok_,
    ok_endswith,
    ok_file_has_content,
    ok_file_under_git,
    skip_if_on_windows,
    skip_if_root,
    skip_ssh,
    slow,
    swallow_logs,
    with_tempfile,
    with_testsui,
)
from datalad.tests.utils_testdatasets import _mk_submodule_annex
from datalad.utils import (
    Path,
    _path_,
    chpwd,
    on_windows,
)

from ..dataset import Dataset

lgr = logging.getLogger('datalad.tests')


_have_webui = None


def have_webui():
    """Helper for a delayed import test to break circular imports from
    deprecated extension, which gets its tests from the module too
    """
    global _have_webui
    if _have_webui is not None:
        return _have_webui

    try:
        import datalad_deprecated.sibling_webui
        from datalad_deprecated.tests.test_create_sibling_webui import (
            assert_publish_with_ui,
        )
        _have_webui = True
    except (ModuleNotFoundError, ImportError):
        _have_webui = False
    return _have_webui


if lgr.getEffectiveLevel() > logging.DEBUG:
    assert_create_sshwebserver = assert_no_errors_logged(create_sibling)
else:
    assert_create_sshwebserver = create_sibling


def assert_postupdate_hooks(path, installed=True, flat=False):
    """
    Verify that post-update hook was installed (or not, if installed=False)
    """
    from glob import glob
    if flat:
        # there is no top level dataset
        datasets = glob(opj(path, '*'))
    else:
        ds = Dataset(path)
        datasets = [ds.path] + ds.subdatasets(result_xfm='paths', recursive=True, state='present')
    for ds_ in datasets:
        ds_ = Dataset(ds_)
        hook_path = opj(ds_.path, '.git', 'hooks', 'post-update')
        if installed:
            ok_(os.path.exists(hook_path),
                msg="Missing %s" % hook_path)
        else:
            ok_(not os.path.exists(hook_path),
                msg="%s exists when it shouldn't" % hook_path)


@with_tempfile(mkdir=True)
def test_invalid_call(path=None):
    with chpwd(path):
        # ^ Change directory so that we don't fail with an
        # InvalidGitRepositoryError if the test is executed from a git
        # worktree.

        # needs a SSH URL
        assert_raises(InsufficientArgumentsError, create_sibling, '')
        assert_raises(ValueError, create_sibling, 'http://ignore.me')
        # needs an actual dataset
        assert_raises(
            ValueError,
            create_sibling, 'datalad-test:/tmp/somewhere', dataset='/nothere')
    # pre-configure a bogus remote
    ds = Dataset(path).create()
    ds.repo.add_remote('bogus', 'http://bogus.url.com')
    # fails to reconfigure by default with generated
    # and also when given an existing name
    for res in (ds.create_sibling('bogus:/tmp/somewhere', on_failure='ignore'),
                ds.create_sibling('datalad-test:/tmp/somewhere', name='bogus', on_failure='ignore')):
        assert_result_count(
            res, 1,
            status='error',
            message=(
                "sibling '%s' already configured (specify alternative name, or force reconfiguration via --existing",
                'bogus'))

    if not have_webui():
        # need an extension package
        assert_raises(RuntimeError, ds.create_sibling, '', ui=True)


@slow  # 26sec on travis
@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_target_ssh_simple(origin=None, src_path=None, target_rootpath=None):
    ca = dict(result_renderer='disabled')
    test_fname = 'test-annex.dat'
    orig = Dataset(origin).create(**ca)
    (orig.pathobj / test_fname).write_text('some')
    orig.save(**ca)

    port = get_ssh_port("datalad-test")
    # prepare src
    source = install(
        src_path, source=origin,
        result_xfm='datasets', return_type='item-or-list')

    target_path = opj(target_rootpath, "basic")
    with swallow_logs(new_level=logging.ERROR) as cml:
        create_sibling(
            dataset=source,
            name="local_target",
            sshurl="ssh://datalad-test:{}".format(port),
            target_dir=target_path,
            ui=have_webui())
        assert_not_in('enableremote local_target failed', cml.out)

    target_gitrepo = GitRepo(target_path, create=False)  # raises if not a git repo
    assert_in("local_target", source.repo.get_remotes())
    # Both must be annex or git repositories
    src_is_annex = AnnexRepo.is_valid_repo(src_path)
    eq_(src_is_annex, AnnexRepo.is_valid_repo(target_path))
    # And target one should be known to have a known UUID within the source if annex
    if src_is_annex:
        lclcfg = AnnexRepo(src_path).config
        target_aversion = target_gitrepo.config['annex.version']
        # basic config in place
        eq_(lclcfg.get('remote.local_target.annex-ignore'), 'false')
        ok_(lclcfg.get('remote.local_target.annex-uuid'))

    # do it again without force, but use a different name to avoid initial checks
    # for existing remotes:
    with assert_raises(RuntimeError) as cm:
        assert_create_sshwebserver(
            dataset=source,
            name="local_target_alt",
            sshurl="ssh://datalad-test",
            target_dir=target_path)
    ok_(str(cm.value).startswith(
        "Target path %s already exists." % target_path))
    if src_is_annex:
        # Before we "talk" to it with git-annex directly -- we must prevent auto-upgrades
        # since the git-annex on "remote server" (e.g. docker container) could be outdated
        # and not support new git-annex repo version
        target_gitrepo.config.set('annex.autoupgraderepository', "false", scope='local')
        try:
            target_description = AnnexRepo(target_path, create=False).get_description()
        except CommandError as e:
            if 'is at unsupported version' not in str(e.stderr):
                raise
            # we just would skip this part of the test and avoid future similar query
            target_description = None
        else:
            assert target_gitrepo.config['annex.version'] == target_aversion
            assert_not_equal(target_description, None)
            assert_not_equal(target_description, target_path)
            # on yoh's laptop TMPDIR is under HOME, so things start to become
            # tricky since then target_path is shortened and we would need to know
            # remote $HOME.  To not over-complicate and still test, test only for
            # the basename of the target_path
            ok_endswith(target_description, basename(target_path))
    # now, with force and correct url, which is also used to determine
    # target_dir
    # Note: on windows absolute path is not url conform. But this way it's easy
    # to test, that ssh path is correctly used.
    if not on_windows:
        # add random file under target_path, to explicitly test existing=replace
        open(opj(target_path, 'random'), 'w').write('123')

        @with_testsui(responses=["yes"])
        def interactive_assert_create_sshwebserver():
            assert_create_sshwebserver(
                dataset=source,
                name="local_target",
                sshurl="ssh://datalad-test" + target_path,
                publish_by_default=DEFAULT_BRANCH,
                existing='replace',
                ui=have_webui(),
            )
        interactive_assert_create_sshwebserver()

        eq_("ssh://datalad-test" + urlquote(target_path),
            source.repo.get_remote_url("local_target"))
        ok_(source.repo.get_remote_url("local_target", push=True) is None)

        # ensure target tree actually replaced by source
        assert_false(exists(opj(target_path, 'random')))

        if src_is_annex:
            lclcfg = AnnexRepo(src_path).config
            eq_(lclcfg.get('remote.local_target.annex-ignore'), 'false')
            # valid uuid
            eq_(lclcfg.get('remote.local_target.annex-uuid').count('-'), 4)
            # should be added too, even if URL matches prior state
            eq_(lclcfg.get('remote.local_target.push'), DEFAULT_BRANCH)

        # again, by explicitly passing urls. Since we are on datalad-test, the
        # could use local path, but then it would not use "remote" git-annex
        # and thus potentially lead to incongruent result. So make URLs a bit
        # different by adding trailing /. to regular target_url
        target_url = "ssh://datalad-test" + target_path + "/."
        cpkwargs = dict(
            dataset=source,
            name="local_target",
            sshurl="ssh://datalad-test",
            target_dir=target_path,
            target_url=target_url,
            target_pushurl="ssh://datalad-test" + target_path,
            ui=have_webui(),
        )

        @with_testsui(responses=['yes'])
        def interactive_assert_create_sshwebserver():
            assert_create_sshwebserver(existing='replace', **cpkwargs)
        interactive_assert_create_sshwebserver()

        if src_is_annex and target_description:
            target_description = AnnexRepo(target_path,
                                           create=False).get_description()
            eq_(target_description, target_url)

        eq_(target_url,
            source.repo.get_remote_url("local_target"))
        eq_("ssh://datalad-test" + target_path,
            source.repo.get_remote_url("local_target", push=True))

        if have_webui():
            from datalad_deprecated.tests.test_create_sibling_webui import (
                assert_publish_with_ui,
            )
            assert_publish_with_ui(target_path)

        # now, push should work:
        push(dataset=source, to="local_target")

        # and we should be able to 'reconfigure'
        def process_digests_mtimes(digests, mtimes):
            # it should have triggered a hook, which would have created log and metadata files
            check_metadata = False
            for part in 'logs', 'metadata':
                metafiles = [k for k in digests if k.startswith(_path_('.git/datalad/%s/' % part))]
                # This is in effect ONLY if we have "compatible" datalad installed on remote
                # end. ATM we don't have easy way to guarantee that AFAIK (yoh),
                # so let's not check/enforce (TODO)
                # assert(len(metafiles) >= 1)  # we might have 2 logs if timestamps do not collide ;)
                # Let's actually do it to some degree
                if part == 'logs':
                    # always should have those:
                    assert (len(metafiles) >= 1)
                    with open(opj(target_path, metafiles[0])) as f:
                        if 'no datalad found' not in f.read():
                            check_metadata = True
                if part == 'metadata':
                    eq_(len(metafiles), bool(check_metadata))
                for f in metafiles:
                    digests.pop(f)
                    mtimes.pop(f)
            # and just pop some leftovers from annex
            # and ignore .git/logs content (gh-5298)
            for f in list(digests):
                if f.startswith('.git/annex/mergedrefs') \
                        or f.startswith('.git/logs/'):
                    digests.pop(f)
                    mtimes.pop(f)

        if not have_webui():
            # the rest of the test assumed that we have uploaded a UI
            return
        orig_digests, orig_mtimes = get_mtimes_and_digests(target_path)
        process_digests_mtimes(orig_digests, orig_mtimes)

        import time
        time.sleep(0.1)  # just so that mtimes change
        assert_create_sshwebserver(existing='reconfigure', **cpkwargs)
        digests, mtimes = get_mtimes_and_digests(target_path)
        process_digests_mtimes(digests, mtimes)

        assert_dict_equal(orig_digests, digests)  # nothing should change in terms of content

        # but some files should have been modified
        modified_files = {k for k in mtimes if orig_mtimes.get(k, 0) != mtimes.get(k, 0)}
        # collect which files were expected to be modified without incurring any changes
        ok_modified_files = {
            _path_('.git/hooks/post-update'), 'index.html',
        }
        ok_modified_files.add(_path_('.git/config'))
        ok_modified_files.update({f for f in digests if f.startswith(_path_('.git/datalad/web'))})
        # it seems that with some recent git behavior has changed a bit
        # and index might get touched
        if _path_('.git/index') in modified_files:
            ok_modified_files.add(_path_('.git/index'))
        ok_(modified_files.issuperset(ok_modified_files))


@slow  # 53.8496s
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def check_target_ssh_recursive(use_ssh, origin, src_path, target_path):
    _mk_submodule_annex(origin, 'test-annex.dat', 'whatever')

    # prepare src
    source = install(src_path, source=origin, recursive=True)

    sub1 = Dataset(opj(src_path, "subm 1"))
    sub2 = Dataset(opj(src_path, "2"))

    for flat in False, True:
        target_path_ = target_dir_tpl = target_path + "-" + str(flat)

        if flat:
            target_dir_tpl += "/prefix%RELNAME"
            sep = '-'
        else:
            sep = os.path.sep

        if use_ssh:
            sshurl = "ssh://datalad-test" + target_path_
        else:
            sshurl = target_path_

        remote_name = 'remote-' + str(flat)
        with chpwd(source.path):
            assert_create_sshwebserver(
                name=remote_name,
                sshurl=sshurl,
                target_dir=target_dir_tpl,
                recursive=True,
                ui=have_webui())

        # raise if git repos were not created
        for suffix in [sep + 'subm 1', sep + '2', '']:
            target_dir = opj(target_path_, 'prefix' if flat else "").rstrip(os.path.sep) + suffix
            # raise if git repos were not created
            GitRepo(target_dir, create=False)

            if have_webui():
                from datalad_deprecated.tests.test_create_sibling_webui import (
                    assert_publish_with_ui,
                )
                assert_publish_with_ui(target_dir, rootds=not suffix, flat=flat)

        for repo in [source.repo, sub1.repo, sub2.repo]:
            assert_not_in("local_target", repo.get_remotes())

        # now, push should work:
        push(dataset=source, to=remote_name)

        # verify that we can create-sibling which was created later and possibly
        # first published in super-dataset as an empty directory
        sub3_name = 'subm 3-%s' % flat
        sub3 = source.create(sub3_name)
        # since is an empty value to force it to consider all changes since we published
        # already
        with chpwd(source.path):
            # as we discussed in gh-1495 we use the last-published state of the base
            # dataset as the indicator for modification detection with since='^'
            # hence we must not publish the base dataset on its own without recursion,
            # if we want to have this mechanism do its job
            #push(to=remote_name)  # no recursion
            out1 = assert_create_sshwebserver(
                name=remote_name,
                sshurl=sshurl,
                target_dir=target_dir_tpl,
                recursive=True,
                existing='skip',
                ui=have_webui(),
                since='^'
            )
            assert_postupdate_hooks(target_path_, installed=have_webui(), flat=flat)
            assert_result_count(out1, 1, status='ok', sibling_name=remote_name)

            # ensure that nothing is created since since is used.
            # Also cover deprecation for since='' support.  Takes just 60ms or so.
            # TODO: change or remove when removing since='' deprecation support
            out2 = assert_create_sshwebserver(
                name=remote_name,
                sshurl=sshurl,
                target_dir=target_dir_tpl,
                recursive=True,
                existing='skip',
                ui=have_webui(),
                since=''
            )
            assert_result_count(out2, 1, status='notneeded', sibling_name=remote_name)

        # so it was created on remote correctly and wasn't just skipped
        assert(Dataset(_path_(target_path_, ('prefix-' if flat else '') + sub3_name)).is_installed())
        push(dataset=source, to=remote_name, recursive=True, since='^') # just a smoke test


# we are explicitly testing deprecated since='' inside
@pytest.mark.filterwarnings("ignore: 'since' should point to commitish")
@slow  # 28 + 19sec on travis
def test_target_ssh_recursive():
    skip_if_on_windows()
    check_target_ssh_recursive(False)
    skip_ssh(check_target_ssh_recursive)(True)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile
def check_target_ssh_since(use_ssh, origin, src_path, target_path):
    _mk_submodule_annex(origin, 'test-annex.dat', 'whatever')

    if use_ssh:
        sshurl = "ssh://datalad-test" + target_path
    else:
        sshurl = target_path
    # prepare src
    source = install(src_path, source=origin, recursive=True)
    eq_(len(source.subdatasets()), 2)
    # get a new subdataset and make sure it is committed in the super
    source.create('brandnew')
    eq_(len(source.subdatasets()), 3)
    assert_repo_status(source.path)

    # and now we create a sibling for the new subdataset only
    assert_create_sshwebserver(
        name='dominique_carrera',
        dataset=source,
        sshurl=sshurl,
        recursive=True,
        since='HEAD~1')
    # there is one thing in the target directory only, and that is the
    # remote repo of the newly added subdataset

    target = Dataset(target_path)
    ok_(not target.is_installed())  # since we didn't create it due to since
    eq_(['brandnew'], os.listdir(target_path))

    # now test functionality if we add a subdataset with a subdataset
    brandnew2 = source.create('brandnew2')
    brandnewsub = brandnew2.create('sub')
    brandnewsubsub = brandnewsub.create('sub')
    # and now we create a sibling for the new subdataset only
    assert_create_sshwebserver(
        name='dominique_carrera',
        dataset=source,
        sshurl=sshurl,
        recursive=True,
        existing='skip')
    # verify that it created the immediate subdataset
    ok_(Dataset(_path_(target_path, 'brandnew2')).is_installed())
    # but not the subs since they were not saved, thus even push would not operate
    # on them yet, so no reason for us to create them until subdatasets are saved
    ok_(not Dataset(_path_(target_path, 'brandnew2/sub')).is_installed())

    source.save(recursive=True)

    # and if repeated now -- will create those sub/sub
    assert_create_sshwebserver(
        name='dominique_carrera',
        dataset=source,
        sshurl=sshurl,
        recursive=True,
        existing='skip')
    # verify that it created the immediate subdataset
    ok_(Dataset(_path_(target_path, 'brandnew2/sub')).is_installed())
    ok_(Dataset(_path_(target_path, 'brandnew2/sub/sub')).is_installed())

    # now we will try with --since while creating even deeper nested one, and ensuring
    # it is created -- see https://github.com/datalad/datalad/issues/6596
    brandnewsubsub.create('sub')
    source.save(recursive=True)
    # and now we create a sibling for the new subdataset only
    assert_create_sshwebserver(
        name='dominique_carrera',
        dataset=source,
        sshurl=sshurl,
        recursive=True,
        existing='skip',
        since=f'{DEFAULT_REMOTE}/{DEFAULT_BRANCH}')
    # verify that it created the sub and sub/sub
    ok_(Dataset(_path_(target_path, 'brandnew2/sub/sub/sub')).is_installed())

    # we installed without web ui - no hooks should be created/enabled
    assert_postupdate_hooks(_path_(target_path, 'brandnew'), installed=False)


@slow  # 10sec + ? on travis
def test_target_ssh_since():
    skip_if_on_windows()
    skip_ssh(check_target_ssh_since)(True)
    check_target_ssh_since(False)


@skip_if_on_windows
@skip_if_root
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def check_failon_no_permissions(use_ssh, src_path, target_path):
    if use_ssh:
        sshurl = "ssh://datalad-test" + opj(target_path, 'ds')
    else:
        sshurl = opj(target_path, 'ds')
    ds = Dataset(src_path).create()
    # remove user write permissions from target path
    chmod(target_path, stat.S_IREAD | stat.S_IEXEC)
    assert_raises(
        CommandError,
        ds.create_sibling,
        name='noperm',
        sshurl=sshurl)
    # restore permissions
    chmod(target_path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    assert_create_sshwebserver(
        name='goodperm',
        dataset=ds,
        sshurl=sshurl)


def test_failon_no_permissions():
    skip_ssh(check_failon_no_permissions)(True)
    check_failon_no_permissions(False)


@with_tempfile(mkdir=True)
@with_tempfile
def check_replace_and_relative_sshpath(use_ssh, src_path, dst_path):
    # We need to come up with the path relative to our current home directory
    # https://github.com/datalad/datalad/issues/1653
    # but because we override HOME the HOME on the remote end would be
    # different even though a datalad-test. So we need to query it
    if use_ssh:
        from datalad import ssh_manager
        ssh = ssh_manager.get_connection('datalad-test')
        remote_home, err = ssh('pwd')
        remote_home = remote_home.rstrip('\n')
        dst_relpath = os.path.relpath(dst_path, remote_home)
        url = 'datalad-test:%s' % dst_relpath
        sibname = 'datalad-test'
    else:
        url = dst_path
        sibname = 'local'

    ds = Dataset(src_path).create()
    create_tree(ds.path, {'sub.dat': 'lots of data'})
    ds.save('sub.dat')
    res = ds.create_sibling(url, ui=have_webui())
    assert_in_results(res, action="create_sibling", sibling_name=sibname)
    published = ds.push(to=sibname, data='anything')
    assert_result_count(published, 1, path=opj(ds.path, 'sub.dat'))
    if have_webui():
        # verify that hook runs and there is nothing in stderr
        # since it exits with 0 exit even if there was a problem
        out = Runner(cwd=opj(dst_path, '.git')).run([_path_('hooks/post-update')],
                                                    protocol=StdOutErrCapture)
        assert_false(out['stdout'])
        assert_false(out['stderr'])

    # Verify that we could replace and publish no problem
    # https://github.com/datalad/datalad/issues/1656
    # Strangely it spits outs IncompleteResultsError exception atm... so just
    # checking that it fails somehow
    res = ds.create_sibling(url, on_failure='ignore')
    assert_status('error', res)
    assert_in('already configured', res[0]['message'][0])
    # "Settings" such as UI do not persist, so we specify it again
    # for the test below depending on it
    with assert_raises(RuntimeError):
        # but we cannot replace in non-interactive mode
        ds.create_sibling(url, existing='replace', ui=have_webui())

    # We don't have context manager like @with_testsui, so
    @with_testsui(responses=["yes"])
    def interactive_create_sibling():
        ds.create_sibling(url, existing='replace', ui=have_webui())
    interactive_create_sibling()

    published2 = ds.push(to=sibname, data='anything')
    assert_result_count(published2, 1, path=opj(ds.path, 'sub.dat'))

    # and one more test since in above test it would not puke ATM but just
    # not even try to copy since it assumes that file is already there
    create_tree(ds.path, {'sub2.dat': 'more data'})
    ds.save('sub2.dat')
    published3 = ds.push(to=sibname, data='nothing')  # we publish just git
    assert_result_count(published3, 0, path=opj(ds.path, 'sub2.dat'))

    if not have_webui():
        return

    # now publish "with" data, which should also trigger the hook!
    # https://github.com/datalad/datalad/issues/1658
    from glob import glob

    from datalad.consts import WEB_META_LOG
    logs_prior = glob(_path_(dst_path, WEB_META_LOG, '*'))
    published4 = ds.push(to=sibname, data='anything')
    assert_result_count(published4, 1, path=opj(ds.path, 'sub2.dat'))
    logs_post = glob(_path_(dst_path, WEB_META_LOG, '*'))
    eq_(len(logs_post), len(logs_prior) + 1)

    assert_postupdate_hooks(dst_path)


@slow  # 14 + 10sec on travis
def test_replace_and_relative_sshpath():
    skip_if_on_windows()
    skip_ssh(check_replace_and_relative_sshpath)(True)
    check_replace_and_relative_sshpath(False)


@with_tempfile(mkdir=True)
@with_tempfile(suffix="target")
def _test_target_ssh_inherit(standardgroup, ui, use_ssh, src_path, target_path):
    ds = Dataset(src_path).create()
    if use_ssh:
        target_url = 'datalad-test:%s' % target_path
    else:
        target_url = target_path
    remote = "magical"
    # for the test of setting a group, will just smoke test while using current
    # user's group
    ds.create_sibling(target_url, name=remote, shared='group', group=os.getgid(), ui=ui)  # not doing recursively
    if standardgroup:
        ds.repo.set_preferred_content('wanted', 'standard', remote)
        ds.repo.set_preferred_content('group', standardgroup, remote)
    ds.publish(to=remote)

    # now a month later we created a new subdataset... a few of the nested ones
    # A known hiccup happened when there
    # is also subsub ds added - we might incorrectly traverse and not prepare
    # sub first for subsub to inherit etc
    parent_ds = ds
    subdss = []
    nlevels = 2  # gets slow: 1 - 43 sec, 2 - 49 sec , 3 - 69 sec
    for levels in range(nlevels):
        subds = parent_ds.create('sub')
        create_tree(subds.path, {'sub.dat': 'lots of data'})
        parent_ds.save('sub', recursive=True)
        ok_file_under_git(subds.path, 'sub.dat', annexed=True)
        parent_ds = subds
        subdss.append(subds)

    target_subdss = [
        Dataset(opj(*([target_path] + ['sub'] * (i+1))))
        for i in range(nlevels)
    ]
    # since we do not have yet/thus have not used an option to record to publish
    # to that sibling by default (e.g. --set-upstream), if we run just ds.publish
    # -- should fail
    assert_result_count(
        ds.publish(on_failure='ignore'),
        1,
        status='impossible',
        message='No target sibling configured for default publication, please specify via --to')
    ds.publish(to=remote)  # should be ok, non recursive; BUT it (git or us?) would
                  # create an empty sub/ directory
    assert_postupdate_hooks(target_path, installed=ui)
    for target_sub in target_subdss:
        ok_(not target_sub.is_installed())  # still not there
    res = ds.publish(to=remote, recursive=True, on_failure='ignore')
    assert_result_count(res, 1 + len(subdss))
    assert_status(('error', 'notneeded'), res)
    assert_result_count(
        res, len(subdss),
        status='error',
        message=("Unknown target sibling '%s' for publication", 'magical'))

    # Finally publishing with inheritance
    ds.publish(to=remote, recursive=True, missing='inherit')
    assert_postupdate_hooks(target_path, installed=ui)

    def check_dss():
        # we added the remote and set all the
        for subds in subdss:
            eq_(subds.repo.get_preferred_content('wanted', remote), 'standard' if standardgroup else '')
            eq_(subds.repo.get_preferred_content('group', remote), standardgroup or '')

        for target_sub in target_subdss:
            ok_(target_sub.is_installed())  # it is there now
            eq_(target_sub.repo.config.get('core.sharedrepository'), '1')
            # and we have transferred the content
            if standardgroup and standardgroup == 'backup':
                # only then content should be copied
                ok_file_has_content(opj(target_sub.path, 'sub.dat'), 'lots of data')
            else:
                # otherwise nothing is copied by default
                assert_false(target_sub.repo.file_has_content('sub.dat'))

    check_dss()
    # and it should be ok to reconfigure the full hierarchy of datasets
    # while "inheriting". No URL must be specified, and we must not blow
    # but just issue a warning for the top level dataset which has no super,
    # so cannot inherit anything - use case is to fixup/establish the full
    # hierarchy on the remote site
    ds.save(recursive=True)  # so we have committed hierarchy for create_sibling
    with swallow_logs(logging.WARNING) as cml:
        out = ds.create_sibling(
            None, name=remote, existing="reconfigure", inherit=True,
            ui=ui, recursive=True)
        eq_(len(out), 1 + len(subdss))
        assert_in("Cannot determine super dataset", cml.out)

    check_dss()


@slow  # 49 sec
def test_target_ssh_inherit():
    skip_if_on_windows()  # create_sibling incompatible with win servers
    try:
        from datalad_deprecated.publish import Publish
    except ImportError:
        raise SkipTest('Test requires `publish()` from datalad-deprecated')
    # TODO: was waiting for resolution on
    #   https://github.com/datalad/datalad/issues/1274
    # which is now closed but this one is failing ATM, thus leaving as TODO
    # _test_target_ssh_inherit(None)      # no wanted etc
    # Takes too long so one will do with UI and another one without
    skip_ssh(_test_target_ssh_inherit)('manual', have_webui(), True)  # manual -- no load should be annex copied
    _test_target_ssh_inherit('backup', False, False)  # backup -- all data files


@with_testsui(responses=["no", "yes"])
@with_tempfile(mkdir=True)
def check_exists_interactive(use_ssh, path):
    origin = Dataset(opj(path, "origin")).create()
    sibling_path = opj(path, "sibling")

    # Initiate sibling directory with "stuff"
    create_tree(sibling_path, {'stuff': ''})

    if use_ssh:
        sshurl = 'datalad-test:' + sibling_path
    else:
        sshurl = sibling_path

    # Should fail
    with assert_raises(RuntimeError):
        origin.create_sibling(sshurl)

    # Since first response is "no" - we should fail here again:
    with assert_raises(RuntimeError):
        origin.create_sibling(sshurl, existing='replace')
    # and there should be no initiated repository
    assert not Dataset(sibling_path).is_installed()
    # But we would succeed on the 2nd try, since answer will be yes
    origin.create_sibling(sshurl, existing='replace')
    assert Dataset(sibling_path).is_installed()
    # And with_testsui should not fail with "Unused responses left"


def test_check_exists_interactive():
    skip_if_on_windows()
    skip_ssh(check_exists_interactive)(True)
    check_exists_interactive(False)


@skip_if_on_windows
@with_tempfile(mkdir=True)
def test_local_relpath(path=None):
    path = Path(path)
    ds_main = Dataset(path / "main").create()
    ds_main.create("subds")

    ds_main.create_sibling(
        name="relpath-bound", recursive=True,
        sshurl=os.path.relpath(str(path / "a"), ds_main.path))
    ok_((path / "a" / "subds").exists())

    with chpwd(path):
        create_sibling(
            dataset=ds_main.path,
            name="relpath-unbound", recursive=True,
            sshurl="b")
    ok_((path / "b" / "subds").exists())

    with chpwd(ds_main.path):
        create_sibling(
            name="relpath-unbound-dsnone", recursive=True,
            sshurl=os.path.relpath(str(path / "c"), ds_main.path))
    ok_((path / "c" / "subds").exists())


@skip_if_on_windows
@with_tempfile(mkdir=True)
def test_local_path_target_dir(path=None):
    path = Path(path)
    ds_main = Dataset(path / "main").create()

    ds_main.create_sibling(
        name="abspath-targetdir",
        sshurl=str(path / "a"), target_dir="tdir")
    ok_((path / "a" / "tdir").exists())

    ds_main.create_sibling(
        name="relpath-bound-targetdir",
        sshurl=os.path.relpath(str(path / "b"), ds_main.path),
        target_dir="tdir")
    ok_((path / "b" / "tdir").exists())

    with chpwd(path):
        create_sibling(
            dataset=ds_main.path,
            name="relpath-unbound-targetdir",
            sshurl="c", target_dir="tdir")
    ok_((path / "c" / "tdir").exists())

    ds_main.create("subds")

    ds_main.create_sibling(
        name="rec-plain-targetdir", recursive=True,
        sshurl=str(path / "d"), target_dir="tdir")
    ok_((path / "d" / "tdir" / "subds").exists())

    ds_main.create_sibling(
        name="rec-template-targetdir", recursive=True,
        sshurl=str(path / "e"), target_dir="d%RELNAME")
    ok_((path / "e" / "d").exists())
    ok_((path / "e" / "d-subds").exists())


@slow  # 12sec on Yarik's laptop
@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_non_master_branch(src_path=None, target_path=None):
    src_path = Path(src_path)
    target_path = Path(target_path)

    ds_a = Dataset(src_path).create()
    # Rename rather than checking out another branch so that the default branch
    # doesn't exist in any state.
    ds_a.repo.call_git(["branch", "-m", DEFAULT_BRANCH, "other"])
    (ds_a.pathobj / "afile").write_text("content")
    sa = ds_a.create("sub-a")
    sa.repo.checkout("other-sub", ["-b"])
    ds_a.create("sub-b")

    ds_a.save()
    ds_a.create_sibling(
        name="sib", recursive=True,
        sshurl="ssh://datalad-test" + str(target_path / "b"))
    ds_a.push(to="sib", data="anything")

    ds_b = Dataset(target_path / "b")

    def get_branch(repo):
        return repo.get_corresponding_branch() or repo.get_active_branch()

    # The HEAD for the create-sibling matches what the branch was in
    # the original repo.
    eq_(get_branch(ds_b.repo), "other")
    ok_((ds_b.pathobj / "afile").exists())

    eq_(get_branch(Dataset(target_path / "b" / "sub-a").repo),
        "other-sub")
    eq_(get_branch(Dataset(target_path / "b" / "sub-b").repo),
        DEFAULT_BRANCH)


@known_failure_windows  # https://github.com/datalad/datalad/issues/5287
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_preserve_attrs(src=None, dest=None):
    create_tree(src, {"src": {"foo": {"bar": "This is test text."}}})
    os.utime(opj(src, "src", "foo", "bar"), (1234567890, 1234567890))
    _RunnerAdapter().put(opj(src, "src"), dest, recursive=True, preserve_attrs=True)
    s = os.stat(opj(dest, "src", "foo", "bar"))
    assert s.st_atime == 1234567890
    assert s.st_mtime == 1234567890
    with open(opj(dest, "src", "foo", "bar")) as fp:
        assert fp.read() == "This is test text."


@known_failure_windows # backstory: https://github.com/datalad/datalad/pull/7265
@with_tempfile(mkdir=True)
def test_only_one_level_without_recursion(path=None):
    # this tests for https://github.com/datalad/datalad/issues/5614: accidental
    # recursion of one level by default
    path = Path(path)
    ds_main = Dataset(path / "main").create()
    ds_main.create('sub1')

    ds_main.create_sibling(
        name="dummy",
        sshurl=str(path / "toplevelsibling"))
    # this should exist
    ok_((path / 'toplevelsibling').exists())
    # this shouldn't
    assert_false(Path(path / 'toplevelsibling' / 'sub1').exists())
