# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test clone action

"""

import logging
import os.path as op
import stat

from unittest.mock import patch

from datalad.config import ConfigManager
from datalad import consts
from datalad.api import (
    clone,
    create,
    remove,
)
from datalad.utils import (
    chpwd,
    Path,
    on_windows,
)
from datalad.support.exceptions import IncompleteResultsError
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import Runner
from datalad.tests.utils import (
    assert_false,
    assert_in,
    assert_message,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_result_values_equal,
    assert_status,
    create_tree,
    DEFAULT_BRANCH,
    eq_,
    get_datasets_topdir,
    integration,
    known_failure,
    known_failure_appveyor,
    neq_,
    nok_,
    ok_,
    ok_file_has_content,
    has_symlink_capability,
    ok_startswith,
    patch_config,
    set_date,
    serve_path_via_http,
    skip_if_no_network,
    skip_if_on_windows,
    skip_ssh,
    slow,
    swallow_logs,
    use_cassette,
    with_sameas_remote,
    with_tempfile,
    with_testrepos,
    with_tree,
    SkipTest,
)
from datalad.core.distributed.clone import (
    _get_installationpath_from_url,
    decode_source_spec,
)
from datalad.distribution.dataset import Dataset

# this is the dataset ID of our test dataset in the main datalad RIA store
datalad_store_testds_id = '76b6ca66-36b1-11ea-a2e6-f0d5bf7b5561'


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_invalid_args(path, otherpath, alienpath):
    # source == path
    assert_raises(ValueError, clone, 'Zoidberg', path='Zoidberg')
    assert_raises(ValueError, clone, 'ssh://mars/Zoidberg', path='ssh://mars/Zoidberg')

    # "invalid URL" is a valid filepath... and since no clone to remote
    # is possible - we can just assume that it is the (legit) file path
    # which is provided, not a URL.  So both below should fail as any
    # other clone from a non-existing source and not for the reason of
    # "invalid something".  Behavior is similar to how Git performs - can
    # clone into a URL-like path.

    # install to an "invalid URL" path
    res = clone('Zoidberg', path='ssh://mars:Zoidberg', on_failure='ignore')
    assert_status('error', res)

    # install to a "remote location" path
    res = clone('Zoidberg', path='ssh://mars/Zoidberg', on_failure='ignore')
    assert_status('error', res)

    # make fake dataset
    ds = create(path)
    assert_raises(IncompleteResultsError, ds.clone, '/higherup.', 'Zoidberg')
    # make real dataset, try to install outside
    ds_target = create(Path(otherpath) / 'target')
    assert_raises(ValueError, ds_target.clone, ds.path, path=ds.path)
    assert_status('error', ds_target.clone(ds.path, path=alienpath, on_failure='ignore'))


@integration
@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_crcns(tdir, ds_path):
    with chpwd(tdir):
        res = clone('///', path="all-nonrecursive", on_failure='ignore',
                    result_xfm=None, return_type='list')
        assert_status('ok', res)

    # again, but into existing dataset:
    ds = create(ds_path)
    crcns = ds.clone("///crcns", result_xfm='datasets', return_type='item-or-list')
    ok_(crcns.is_installed())
    eq_(crcns.pathobj, ds.pathobj / "crcns")
    assert_in(crcns.path, ds.subdatasets(result_xfm='paths'))


@integration
@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tree(tree={'sub': {}})
def test_clone_datasets_root(tdir):
    tdir = Path(tdir)
    with chpwd(tdir):
        ds = clone("///")
        ok_(ds.is_installed())
        eq_(ds.pathobj, tdir / get_datasets_topdir())

        # do it a second time:
        res = clone("///", on_failure='ignore', result_xfm=None, return_type='list')
        assert_message(
            "dataset %s was already cloned from '%s'",
            res)
        assert_status('notneeded', res)

        # and a third time into an existing something, that is not a dataset:
        (tdir / 'sub' / 'a_file.txt').write_text("something")

        res = clone('///', path="sub", on_failure='ignore')
        assert_message(
            'target path already exists and not empty, refuse to clone into target path',
            res)
        assert_status('error', res)


@with_testrepos('.*basic.*', flavors=['local-url', 'network', 'local'])
@with_tempfile(mkdir=True)
def test_clone_simple_local(src, path):
    origin = Dataset(path)

    # now install it somewhere else
    ds = clone(src, path, description='mydummy',
               result_xfm='datasets', return_type='item-or-list')
    eq_(ds.path, path)
    ok_(ds.is_installed())
    if not isinstance(origin.repo, AnnexRepo):
        # this means it is a GitRepo
        ok_(isinstance(origin.repo, GitRepo))
        # stays plain Git repo
        ok_(isinstance(ds.repo, GitRepo))
        ok_(not isinstance(ds.repo, AnnexRepo))
        ok_(GitRepo.is_valid_repo(ds.path))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt'})
        assert_repo_status(path, annex=False)
    else:
        # must be an annex
        ok_(isinstance(ds.repo, AnnexRepo))
        ok_(AnnexRepo.is_valid_repo(ds.path, allow_noninitialized=False))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt', 'test-annex.dat'})
        assert_repo_status(path, annex=True)
        # no content was installed:
        ok_(not ds.repo.file_has_content('test-annex.dat'))
        uuid_before = ds.repo.uuid
        eq_(ds.repo.get_description(), 'mydummy')

    # installing it again, shouldn't matter:
    res = clone(src, path, result_xfm=None, return_type='list')
    assert_result_values_equal(res, 'source_url', [src])
    assert_status('notneeded', res)
    assert_message("dataset %s was already cloned from '%s'", res)
    ok_(ds.is_installed())
    if isinstance(origin.repo, AnnexRepo):
        eq_(uuid_before, ds.repo.uuid)


@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_clone_dataset_from_just_source(url, path):
    with chpwd(path, mkdir=True):
        ds = clone(url, result_xfm='datasets', return_type='item-or-list')

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    assert_repo_status(ds.path, annex=None)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


# test fails randomly, likely a bug in one of the employed test helpers
# https://github.com/datalad/datalad/pull/3966#issuecomment-571267932
@known_failure
@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_clone_dataladri(src, topurl, path):
    # make plain git repo
    ds_path = Path(src) / 'ds'
    gr = GitRepo(ds_path, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    Runner(cwd=gr.path)(['git', 'update-server-info'])
    # now install it somewhere else
    with patch('datalad.consts.DATASETS_TOPURL', topurl):
        ds = clone('///ds', path, result_xfm='datasets', return_type='item-or-list')
    eq_(ds.path, path)
    assert_repo_status(path, annex=False)
    ok_file_has_content(ds.pathobj / 'test.txt', 'some')


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_clone_isnot_recursive(src, path_nr, path_r):
    ds = clone(src, path_nr, result_xfm='datasets', return_type='item-or-list')
    ok_(ds.is_installed())
    # check nothin is unintentionally installed
    subdss = ds.subdatasets(recursive=True)
    assert_result_count(subdss, len(subdss), state='absent')
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.subdatasets(recursive=True, fulfilled=False, result_xfm='relpaths')),
        {'subm 1', '2'})


@slow  # 23.1478s
@with_testrepos(flavors=['local'])
# 'local-url', 'network'
# TODO: Somehow annex gets confused while initializing installed ds, whose
# .git/config show a submodule url "file:///aaa/bbb%20b/..."
# this is delivered by with_testrepos as the url to clone
@with_tempfile
def test_clone_into_dataset(source, top_path):

    ds = create(top_path)
    assert_repo_status(ds.path)

    subds = ds.clone(source, "sub",
                     result_xfm='datasets', return_type='item-or-list')
    ok_((subds.pathobj / '.git').is_dir())
    ok_(subds.is_installed())
    assert_in('sub', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))
    # sub is clean:
    assert_repo_status(subds.path, annex=None)
    # top is clean:
    assert_repo_status(ds.path, annex=None)

    # but we could also save while installing and there should be no side-effect
    # of saving any other changes if we state to not auto-save changes
    # Create a dummy change
    create_tree(ds.path, {'dummy.txt': 'buga'})
    assert_repo_status(ds.path, untracked=['dummy.txt'])
    subds_ = ds.clone(source, "sub2",
                      result_xfm='datasets', return_type='item-or-list')
    eq_(subds_.pathobj, ds.pathobj / "sub2")  # for paranoid yoh ;)
    assert_repo_status(ds.path, untracked=['dummy.txt'])


@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_notclone_known_subdataset(src, path):
    # get the superdataset:
    ds = clone(src, path,
               result_xfm='datasets', return_type='item-or-list')

    # subdataset not installed:
    subds = Dataset(ds.pathobj / 'subm 1')
    assert_false(subds.is_installed())
    assert_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_not_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))
    # clone is not meaningful
    res = ds.clone('subm 1', on_failure='ignore')
    assert_status('error', res)
    assert_message('Failed to clone from all attempted sources: %s',
                   res)
    # get does the job
    res = ds.get(path='subm 1', get_data=False)
    assert_status('ok', res)
    ok_(subds.is_installed())
    ok_(AnnexRepo.is_valid_repo(subds.path, allow_noninitialized=False))
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    eq_(set(subds.repo.get_indexed_files()),
        {'test.dat', 'INFO.txt', 'test-annex.dat'})
    assert_not_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))


@with_tempfile(mkdir=True)
def test_failed_clone(dspath):
    ds = create(dspath)
    res = ds.clone("http://nonexistingreallyanything.datalad.org/bla", "sub",
                   on_failure='ignore')
    assert_status('error', res)
    assert_message('Failed to clone from all attempted sources: %s',
                   res)


@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def check_reckless(annex, src_path, top_path, sharedpath):
    # super with or without annex
    src = Dataset(src_path).create(annex=annex)
    # sub always with annex
    srcsub = src.create('sub')

    # and for the actual test
    ds = clone(src.path, top_path, reckless=True,
               result_xfm='datasets', return_type='item-or-list')

    is_crippled = srcsub.repo.is_managed_branch()

    if annex and not is_crippled:
        eq_(ds.config.get('annex.hardlink', None), 'true')

    # actual value is 'auto', because True is a legacy value and we map it
    eq_(ds.config.get('datalad.clone.reckless', None), 'auto')
    if annex:
        eq_(ds.repo.repo_info()['untrusted repositories'][0]['here'], True)
    # now, if we clone another repo into this one, it will inherit the setting
    # without having to provide it explicitly
    newsub = ds.clone(srcsub, 'newsub', result_xfm='datasets', return_type='item-or-list')
    # and `get` the original subdataset
    origsub = ds.get('sub', result_xfm='datasets', return_type='item-or-list')
    for sds in (newsub, origsub):
        eq_(sds.config.get('datalad.clone.reckless', None), 'auto')
        if not is_crippled:
            eq_(sds.config.get('annex.hardlink', None), 'true')

    if is_crippled:
        raise SkipTest("Remainder of test needs proper filesystem permissions")

    if annex:
        # the standard setup keeps the annex locks accessible to the user only
        nok_((ds.pathobj / '.git' / 'annex' / 'index.lck').stat().st_mode \
             & stat.S_IWGRP)
        # but we can set it up for group-shared access too
        sharedds = clone(
            src, sharedpath,
            reckless='shared-group',
            result_xfm='datasets',
            return_type='item-or-list')
        ok_((sharedds.pathobj / '.git' / 'annex' / 'index.lck').stat().st_mode \
            & stat.S_IWGRP)


def test_reckless():
    yield check_reckless, True
    yield check_reckless, False

@with_tempfile
@with_tempfile
def test_install_source_relpath(src, dest):
    src = Path(src)
    create(src)
    src_ = src.name
    with chpwd(src.parent):
        clone(src_, dest)


@with_tempfile
@with_tempfile
def test_clone_isnt_a_smartass(origin_path, path):
    origin = create(origin_path)
    cloned = clone(origin, path,
                   result_xfm='datasets', return_type='item-or-list')
    with chpwd(path):
        # no were are inside a dataset clone, and we make another one
        # we do not want automatic subdatasetification without given a dataset
        # explicitely
        clonedsub = clone(origin, 'testsub',
                          result_xfm='datasets', return_type='item-or-list')
    # correct destination
    assert clonedsub.path.startswith(path)
    # no subdataset relation
    eq_(cloned.subdatasets(), [])


@with_tempfile(mkdir=True)
def test_clone_report_permission_issue(tdir):
    pdir = Path(tdir) / 'protected'
    pdir.mkdir()
    # make it read-only
    pdir.chmod(0o555)
    with chpwd(pdir):
        # first check the premise of the test. If we can write (strangely
        # mounted/crippled file system, subsequent assumptions are violated
        # and we can stop
        probe = Path('probe')
        try:
            probe.write_text('should not work')
            raise SkipTest
        except PermissionError:
            # we are indeed in a read-only situation
            pass
        res = clone('///', result_xfm=None, return_type='list', on_failure='ignore')
        assert_status('error', res)
        assert_result_count(
            res, 1, status='error',
            message="could not create work tree dir '%s/%s': Permission denied"
                    % (pdir, get_datasets_topdir())
        )


# Started to hang on appveyor.
@known_failure_appveyor  #FIXME - hangs
@skip_if_no_network
@with_tempfile
def test_autoenabled_remote_msg(path):
    # Verify that no message about a remote not been enabled is displayed
    # whenever the remote we clone is the  type=git special remote, so the name
    # of the remote might not match
    with swallow_logs(new_level=logging.INFO) as cml:
        res = clone('///repronim/containers', path, result_xfm=None, return_type='list')
        assert_status('ok', res)
        assert_not_in("not auto-enabled", cml.out)


@with_sameas_remote(autoenabled=True)
@with_tempfile(mkdir=True)
def test_clone_autoenable_msg_handles_sameas(repo, clone_path):
    ds = Dataset(repo.path)
    with swallow_logs(new_level=logging.INFO) as cml:
        res = clone(ds, clone_path, result_xfm=None, return_type='list')
        assert_status('ok', res)
        assert_in("r_dir", cml.out)
        assert_in("not auto-enabled", cml.out)
        # The rsyncurl remote was enabled.
        assert_not_in("r_rsync", cml.out)
    ds_cloned = Dataset(clone_path)
    remotes = ds_cloned.repo.get_remotes()
    assert_in("r_rsync", remotes)
    assert_not_in("r_dir", remotes)


def test_installationpath_from_url():
    cases = (
        'http://example.com/lastbit',
        'http://example.com/lastbit.git',
        'http://lastbit:8000',
    ) + (
        'C:\\Users\\mih\\AppData\\Local\\Temp\\lastbit',
        'C:\\Users\\mih\\AppData\\Local\\Temp\\lastbit\\',
        'Temp\\lastbit',
        'Temp\\lastbit\\',
        'lastbit.git',
        'lastbit.git\\',
    ) if on_windows else (
        'lastbit',
        'lastbit/',
        '/lastbit',
        'lastbit.git',
        'lastbit.git/',
    )
    for p in cases:
        eq_(_get_installationpath_from_url(p), 'lastbit')
    # we need to deal with quoted urls
    for url in (
        # although some docs say that space could've been replaced with +
        'http://localhost:8000/+last%20bit',
        'http://localhost:8000/%2Blast%20bit',
        '///%2Blast%20bit',
        '///d1/%2Blast%20bit',
        '///d1/+last bit',
    ):
        eq_(_get_installationpath_from_url(url), '+last bit')
    # and the hostname alone
    eq_(_get_installationpath_from_url("http://hostname"), 'hostname')
    eq_(_get_installationpath_from_url("http://hostname/"), 'hostname')


# https://github.com/datalad/datalad/issues/3958
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_expanduser(srcpath, destpath):
    src = Dataset(Path(srcpath) / 'src').create()
    dest = Dataset(Path(destpath) / 'dest').create()

    with chpwd(destpath), patch.dict('os.environ', {'HOME': srcpath}):
        res = clone(op.join('~', 'src'), 'dest', result_xfm=None, return_type='list',
                    on_failure='ignore')
        assert_result_count(res, 1)
        assert_result_count(
            res, 1, action='install', status='error', path=dest.path,
            message='target path already exists and not empty, refuse to '
            'clone into target path')
        # wipe out destination, and try again
        assert_status('ok', remove(dataset=dest, check=False))
        # now it should do it, and clone the right one
        cloneds = clone(op.join('~', 'src'), 'dest')
        eq_(cloneds.pathobj, Path(destpath) / 'dest')
        eq_(src.id, cloneds.id)
        # and it shouldn't fail when doing it again, because it detects
        # the re-clone
        cloneds = clone(op.join('~', 'src'), 'dest')
        eq_(cloneds.pathobj, Path(destpath) / 'dest')


@with_tempfile(mkdir=True)
def test_cfg_originorigin(path):
    path = Path(path)
    origin = Dataset(path / 'origin').create()
    (origin.pathobj / 'file1.txt').write_text('content')
    origin.save()
    clone_lev1 = clone(origin, path / 'clone_lev1')
    clone_lev2 = clone(clone_lev1, path / 'clone_lev2')
    # the goal is to be able to get file content from origin without
    # the need to configure it manually
    assert_result_count(
        clone_lev2.get('file1.txt', on_failure='ignore'),
        1,
        action='get',
        status='ok',
        path=str(clone_lev2.pathobj / 'file1.txt'),
    )
    eq_((clone_lev2.pathobj / 'file1.txt').read_text(), 'content')
    eq_(
        Path(clone_lev2.siblings(
            'query',
            name='origin-2',
            return_type='item-or-list')['url']),
        origin.pathobj
    )

    # Clone another level, this time with a relative path. Drop content from
    # lev2 so that origin is the only place that the file is available from.
    clone_lev2.drop("file1.txt")
    with chpwd(path), swallow_logs(new_level=logging.DEBUG) as cml:
        clone_lev3 = clone('clone_lev2', 'clone_lev3')
        # we called git-annex-init; see gh-4367:
        cml.assert_logged(msg=r"[^[]*Async run \[('git', 'annex'|'git-annex'), "
                              r"'init'",
                          match=False,
                          level='DEBUG')
    assert_result_count(
        clone_lev3.get('file1.txt', on_failure='ignore'),
        1,
        action='get',
        status='ok',
        path=str(clone_lev3.pathobj / 'file1.txt'))


# test fix for gh-2601/gh-3538
@known_failure
@with_tempfile()
def test_relative_submodule_url(path):
    Dataset(op.join(path, 'origin')).create()
    ds = Dataset(op.join(path, 'ds')).create()
    with chpwd(ds.path):
        ds_cloned = ds.clone(
            source=op.join(op.pardir, 'origin'),
            path='sources')

    # Check that a simple fetch call does not fail.
    ds_cloned.repo.fetch()

    subinfo = ds.subdatasets(return_type='item-or-list')
    eq_(subinfo['gitmodule_url'],
        # must be a relative URL, not platform-specific relpath!
        '../../origin')


@with_tree(tree={"subdir": {}})
@with_tempfile(mkdir=True)
def test_local_url_with_fetch(path, path_other):
    path = Path(path)
    path_other = Path(path_other)
    Dataset(path / "source").create()

    for where, source, path in [
            (path, "source", "a"),
            (path / "subdir", op.join(op.pardir, "source"), "a"),
            (path, "source", path_other / "a")]:
        with chpwd(where):
            ds_cloned = clone(source=source, path=path)
            # Perform a fetch to check that the URL points to a valid location.
            ds_cloned.repo.fetch()


def test_decode_source_spec():
    # resolves datalad RIs:
    eq_(decode_source_spec('///subds'),
        dict(source='///subds', giturl=consts.DATASETS_TOPURL + 'subds', version=None,
             type='dataladri', default_destpath='subds'))
    assert_raises(NotImplementedError, decode_source_spec,
                  '//custom/subds')

    # doesn't harm others:
    for url in (
            'http://example.com',
            '/absolute/path',
            'file://localhost/some',
            'localhost/another/path',
            'user@someho.st/mydir',
            'ssh://somewhe.re/else',
            'git://github.com/datalad/testrepo--basic--r1',
    ):
        props = decode_source_spec(url)
        dest = props.pop('default_destpath')
        eq_(props, dict(source=url, version=None, giturl=url, type='giturl'))

    # RIA URIs with and without version specification
    dsid = '6d69ca68-7e85-11e6-904c-002590f97d84'
    for proto, loc, version in (
            ('http', 'example.com', None),
            ('http', 'example.com', 'v1.0'),
            ('http', 'example.com', 'some_with@in_it'),
            ('ssh', 'example.com', 'some_with@in_it'),
    ):
        spec = 'ria+{}://{}{}{}'.format(
            proto,
            loc,
            '#{}'.format(dsid),
            '@{}'.format(version) if version else '')
        eq_(decode_source_spec(spec),
            dict(
                source=spec,
                giturl='{}://{}/{}/{}'.format(
                    proto,
                    loc,
                    dsid[:3],
                    dsid[3:]),
                version=version,
                default_destpath=dsid,
                type='ria')
        )
    # not a dataset UUID
    assert_raises(ValueError, decode_source_spec, 'ria+http://example.com#123')

    # literal dataset name/location
    eq_(decode_source_spec('ria+http://example.com#~rootds'),
        {'source': 'ria+http://example.com#~rootds',
         'version': None, 'type': 'ria',
         'giturl': 'http://example.com/alias/rootds',
         'default_destpath': 'rootds'})
    # version etc still works
    eq_(decode_source_spec('ria+http://example.com#~rootds@specialbranch'),
        {'source': 'ria+http://example.com#~rootds@specialbranch',
         'version': 'specialbranch', 'type': 'ria',
         'giturl': 'http://example.com/alias/rootds',
         'default_destpath': 'rootds'})


def _move2store(storepath, d):
    # make a bare clone of it into a local that matches the organization
    # of a ria dataset store
    store_loc = str(storepath / d.id[:3] / d.id[3:])
    d.repo.call_git(['clone', '--bare', d.path, store_loc])
    d.siblings('configure', name='store', url=str(store_loc),
               result_renderer='disabled')
    Runner(cwd=store_loc).run(['git', 'update-server-info'])


@slow  # 12sec on Yarik's laptop
@with_tree(tree={
    'ds': {
        'test.txt': 'some',
        'subdir': {
            'subds': {'testsub.txt': 'somemore'},
        },
    },
})
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_ria_http(lcl, storepath, url):
    # create a local dataset with a subdataset
    lcl = Path(lcl)
    storepath = Path(storepath)
    subds = Dataset(lcl / 'ds' / 'subdir' / 'subds').create(force=True)
    subds.save()
    ds = Dataset(lcl / 'ds').create(force=True)
    ds.save(version_tag='original')
    assert_repo_status(ds.path)
    for d in (ds, subds):
        _move2store(storepath, d)
    # location of superds in store
    storeds_loc = str(storepath / ds.id[:3] / ds.id[3:])
    # now we should be able to clone from a ria+http url
    # the super
    riaclone = clone(
        'ria+{}#{}'.format(url, ds.id),
        lcl / 'clone',
    )

    # due to default configuration, clone() should automatically look for the
    # subdataset in the store, too -- if not the following would fail, because
    # we never configured a proper submodule URL
    riaclonesub = riaclone.get(
        op.join('subdir', 'subds'), get_data=False,
        result_xfm='datasets', return_type='item-or-list')

    # both datasets came from the store and must be set up in an identical
    # fashion
    for origds, cloneds in ((ds, riaclone), (subds, riaclonesub)):
        eq_(origds.id, cloneds.id)
        if not ds.repo.is_managed_branch():
            # test logic cannot handle adjusted branches
            eq_(origds.repo.get_hexsha(), cloneds.repo.get_hexsha())
        ok_(cloneds.config.get('remote.origin.url').startswith(url))
        eq_(cloneds.config.get('remote.origin.annex-ignore'), 'true')
        eq_(cloneds.config.get('datalad.get.subdataset-source-candidate-200origin'),
            'ria+%s#{id}' % url)

    # now advance the source dataset
    (ds.pathobj / 'newfile.txt').write_text('new')
    ds.save()
    ds.publish(to='store')
    Runner(cwd=storeds_loc).run(['git', 'update-server-info'])
    # re-clone as before
    riaclone2 = clone(
        'ria+{}#{}'.format(url, ds.id),
        lcl / 'clone2',
    )
    # and now clone a specific version, here given be the tag name
    riaclone_orig = clone(
        'ria+{}#{}@{}'.format(url, ds.id, 'original'),
        lcl / 'clone_orig',
    )
    if not ds.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        # we got the precise version we wanted
        eq_(riaclone.repo.get_hexsha(), riaclone_orig.repo.get_hexsha())
        # and not the latest
        eq_(riaclone2.repo.get_hexsha(), ds.repo.get_hexsha())
        neq_(riaclone2.repo.get_hexsha(), riaclone_orig.repo.get_hexsha())

    # attempt to clone a version that doesn't exist
    with swallow_logs():
        with assert_raises(IncompleteResultsError) as cme:
            clone('ria+{}#{}@impossible'.format(url, ds.id),
                  lcl / 'clone_failed')
        assert_in("not found in upstream", str(cme.exception))

    # lastly test if URL rewriting is in effect
    # on the surface we clone from an SSH source identified by some custom
    # label, no full URL, but URL rewriting setup maps it back to the
    # HTTP URL used above
    with patch_config({
            'url.ria+{}#.insteadof'.format(url): 'ria+ssh://somelabel#'}):
        cloned_by_label = clone(
            'ria+ssh://somelabel#{}'.format(origds.id),
            lcl / 'cloned_by_label',
        )
    # so we get the same setup as above, but....
    eq_(origds.id, cloned_by_label.id)
    if not ds.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        eq_(origds.repo.get_hexsha(), cloned_by_label.repo.get_hexsha())
    ok_(cloned_by_label.config.get('remote.origin.url').startswith(url))
    eq_(cloned_by_label.config.get('remote.origin.annex-ignore'), 'true')
    # ... the clone candidates go with the label-based URL such that
    # future get() requests acknowlege a (system-wide) configuration
    # update
    eq_(cloned_by_label.config.get('datalad.get.subdataset-source-candidate-200origin'),
        'ria+ssh://somelabel#{id}')

    if not has_symlink_capability():
        return
    # place a symlink in the store to serve as a dataset alias
    (storepath / 'alias').mkdir()
    (storepath / 'alias' / 'myname').symlink_to(storeds_loc)
    with chpwd(lcl):
        cloned_by_alias = clone('ria+{}#~{}'.format(url, 'myname'))
    # still get the same data
    eq_(cloned_by_alias.id, ds.id)
    # more sensible default install path
    eq_(cloned_by_alias.pathobj.name, 'myname')


@with_tempfile
def _test_ria_postclonecfg(url, dsid, clone_path):
    # Test cloning from RIA store while ORA special remote autoenabling failed
    # due to an invalid URL from the POV of the cloner.
    # Origin's git-config-file should contain the UUID to enable. This needs to
    # work via HTTP, SSH and local cloning.

    # Autoenabling should fail initially by git-annex-init and we would report
    # on INFO level. Only postclone routine would deal with it.
    with swallow_logs(new_level=logging.INFO) as cml:
        # First, the super ds:
        riaclone = clone('ria+{}#{}'.format(url, dsid), clone_path)
        cml.assert_logged(msg="access to 1 dataset sibling store-storage not "
                              "auto-enabled",
                          level="INFO",
                          regex=False)

    # However, we now can retrieve content since clone should have enabled the
    # special remote with new URL (or origin in case of HTTP).
    res = riaclone.get('test.txt')
    assert_result_count(res, 1,
                        status='ok',
                        path=str(riaclone.pathobj / 'test.txt'),
                        message="from {}...".format("origin"
                                                    if url.startswith('http')
                                                    else "store-storage"))

    # same thing for the sub ds (we don't need a store-url and id - get should
    # figure those itself):
    with swallow_logs(new_level=logging.INFO) as cml:
        riaclonesub = riaclone.get(
            op.join('subdir', 'subds'), get_data=False,
            result_xfm='datasets', return_type='item-or-list')
        cml.assert_logged(msg="access to 1 dataset sibling store-storage not "
                              "auto-enabled",
                          level="INFO",
                          regex=False)
    res = riaclonesub.get('testsub.txt')
    assert_result_count(res, 1,
                        status='ok',
                        path=str(riaclonesub.pathobj / 'testsub.txt'),
                        message="from {}...".format("origin"
                                                    if url.startswith('http')
                                                    else "store-storage"))

    # finally get the plain git subdataset.
    # Clone should figure to also clone it from a ria+ URL
    # (subdataset-source-candidate), notice that there wasn't an autoenabled ORA
    # remote, but shouldn't stumble upon it, since it's a plain git.
    res = riaclone.get(op.join('subdir', 'subgit', 'testgit.txt'))
    assert_result_count(res, 1, status='ok', type='dataset', action='install')
    assert_result_count(res, 1, status='notneeded', type='file')
    assert_result_count(res, 2)


@with_tempfile
def _postclonetest_prepare(lcl, storepath, link):

    from datalad.customremotes.ria_utils import (
        create_store,
        create_ds_in_store,
        get_layout_locations
    )
    from datalad.distributed.ora_remote import (
        LocalIO,
    )

    create_tree(lcl,
                tree={
                        'ds': {
                            'test.txt': 'some',
                            'subdir': {
                                'subds': {'testsub.txt': 'somemore'},
                                'subgit': {'testgit.txt': 'even more'}
                            },
                        },
                      })

    # create a local dataset with a subdataset
    lcl = Path(lcl)
    storepath = Path(storepath)
    link = Path(link)
    link.symlink_to(storepath)
    subds = Dataset(lcl / 'ds' / 'subdir' / 'subds').create(force=True)
    subds.save()
    # add a plain git dataset as well
    subgit = Dataset(lcl / 'ds' / 'subdir' / 'subgit').create(force=True,
                                                              no_annex=True)
    subgit.save()
    ds = Dataset(lcl / 'ds').create(force=True)
    ds.save(version_tag='original')
    assert_repo_status(ds.path)

    io = LocalIO()
    create_store(io, storepath, '1')

    # URL to use for upload. Point is, that this should be invalid for the clone
    # so that autoenable would fail. Therefore let it be based on a to be
    # deleted symlink
    upl_url = "ria+{}".format(link.as_uri())

    for d in (ds, subds, subgit):

        # TODO: create-sibling-ria required for config! => adapt to RF'd
        #       creation (missed on rebase?)
        create_ds_in_store(io, storepath, d.id, '2', '1')
        d.create_sibling_ria(upl_url, "store")

        if d is not subgit:
            # Now, simulate the problem by reconfiguring the special remote to
            # not be autoenabled.
            # Note, however, that the actual intention is a URL, that isn't
            # valid from the point of view of the clone (doesn't resolve, no
            # credentials, etc.) and therefore autoenabling on git-annex-init
            # when datalad-cloning would fail to succeed.
            Runner(cwd=d.path).run(['git', 'annex', 'enableremote',
                                    'store-storage',
                                    'autoenable=false'])
        d.push('.', to='store')
        store_loc, _, _ = get_layout_locations(1, storepath, d.id)
        Runner(cwd=str(store_loc)).run(['git', 'update-server-info'])

    link.unlink()
    # We should now have a store with datasets that have an autoenabled ORA
    # remote relying on an inaccessible URL.
    # datalad-clone is supposed to reconfigure based on the URL we cloned from.
    # Test this feature for cloning via HTTP, SSH and FILE URLs.

    return ds.id


@slow  # 14 sec on travis
def test_ria_postclonecfg():

    if not has_symlink_capability():
        # This is needed to create an ORA remote using an URL for upload,
        # that is then invalidated later on (delete the symlink it's based on).
        raise SkipTest("Can't create symlinks")

    from datalad.utils import make_tempfile
    from datalad.tests.utils import HTTPPath

    with make_tempfile(mkdir=True) as lcl, make_tempfile(mkdir=True) as store:
        id = _postclonetest_prepare(lcl, store)

        # test cloning via ria+file://
        yield _test_ria_postclonecfg, Path(store).as_uri(), id

        # Note: HTTP disabled for now. Requires proper implementation in ORA
        #       remote. See
        # https://github.com/datalad/datalad/pull/4203#discussion_r410284649

        # # test cloning via ria+http://
        # with HTTPPath(store) as url:
        #     yield _test_ria_postclonecfg, url, id

        # test cloning via ria+ssh://
        yield skip_ssh(_test_ria_postclonecfg), \
            "ssh://datalad-test:{}".format(Path(store).as_posix()), id


@slow  # 17sec on Yarik's laptop
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
@serve_path_via_http
def test_inherit_src_candidates(lcl, storepath, url):
    lcl = Path(lcl)
    storepath = Path(storepath)
    # dataset with a subdataset
    ds1 = Dataset(lcl / 'ds1').create()
    ds1sub = ds1.create('sub')
    # a different dataset into which we install ds1, but do not touch its subds
    ds2 = Dataset(lcl / 'ds2').create()
    ds2.clone(source=ds1.path, path='mysub')

    # we give no dataset a source candidate config!
    # move all dataset into the store
    for d in (ds1, ds1sub, ds2):
        _move2store(storepath, d)

    # now we must be able to obtain all three datasets from the store
    riaclone = clone(
        'ria+{}#{}'.format(
            # store URL
            url,
            # ID of the root dataset
            ds2.id),
        lcl / 'clone',
    )
    # what happens is the the initial clone call sets a source candidate
    # config, because it sees the dataset coming from a store
    # all obtained subdatasets get the config inherited on-clone
    datasets = riaclone.get('.', get_data=False, recursive=True, result_xfm='datasets')
    # we get two subdatasets
    eq_(len(datasets), 2)
    for ds in datasets:
        eq_(ConfigManager(dataset=ds, source='dataset-local').get(
            'datalad.get.subdataset-source-candidate-200origin'),
            'ria+%s#{id}' % url)


@skip_if_no_network
@with_tempfile()
def test_ria_http_storedataladorg(path):
    # can we clone from the store w/o any dedicated config
    ds = clone('ria+http://store.datalad.org#{}'.format(datalad_store_testds_id), path)
    ok_(ds.is_installed())
    eq_(ds.id, datalad_store_testds_id)


@skip_if_on_windows  # see gh-4131
@with_tree(tree={
    'ds': {
        'test.txt': 'some',
        'subdir': {'testsub.txt': 'somemore'},
    },
})
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_ephemeral(origin_path, bare_path,
                   clone1_path, clone2_path, clone3_path):

    file_test = Path('ds') / 'test.txt'
    file_testsub = Path('ds') / 'subdir' / 'testsub.txt'

    origin = Dataset(origin_path).create(force=True)
    if origin.repo.is_managed_branch():
        raise SkipTest('Ephemeral clones cannot use adjusted mode repos')

    origin.save()
    # 1. clone via path
    clone1 = clone(origin_path, clone1_path, reckless='ephemeral')

    can_symlink = has_symlink_capability()

    if can_symlink:
        clone1_annex = (clone1.repo.dot_git / 'annex')
        ok_(clone1_annex.is_symlink())
        ok_(clone1_annex.resolve().samefile(origin.repo.dot_git / 'annex'))
        if not clone1.repo.is_managed_branch():
            # TODO: We can't properly handle adjusted branch yet
            eq_((clone1.pathobj / file_test).read_text(), 'some')
            eq_((clone1.pathobj / file_testsub).read_text(), 'somemore')

    # 2. clone via file-scheme URL
    clone2 = clone('file://' + Path(origin_path).as_posix(), clone2_path,
                   reckless='ephemeral')

    if can_symlink:
        clone2_annex = (clone2.repo.dot_git / 'annex')
        ok_(clone2_annex.is_symlink())
        ok_(clone2_annex.resolve().samefile(origin.repo.dot_git / 'annex'))
        if not clone2.repo.is_managed_branch():
            # TODO: We can't properly handle adjusted branch yet
            eq_((clone2.pathobj / file_test).read_text(), 'some')
            eq_((clone2.pathobj / file_testsub).read_text(), 'somemore')

    # 3. add something to clone1 and push back to origin availability from
    # clone1 should not be propagated (we declared 'here' dead to that end)

    (clone1.pathobj / 'addition.txt').write_text("even more")
    clone1.save()
    origin.config.set("receive.denyCurrentBranch", "updateInstead",
                      where="local")
    # Note, that the only thing to test is git-annex-dead here,
    # if we couldn't symlink:
    clone1.publish(to='origin', transfer_data='none' if can_symlink else 'auto')
    if not origin.repo.is_managed_branch():
        # test logic cannot handle adjusted branches
        eq_(origin.repo.get_hexsha(), clone1.repo.get_hexsha())
    res = origin.repo.whereis("addition.txt")
    if can_symlink:
        # obv. present in origin, but this is not yet known to origin:
        eq_(res, [])
        res = origin.repo.fsck()
        assert_result_count(res, 3, success=True)
        # TODO: Double check whether annex reports POSIX paths o windows!
        eq_({str(file_test), str(file_testsub), "addition.txt"},
            {r['file'] for r in res})
        # now origin knows:
    res = origin.repo.whereis("addition.txt")
    eq_(res, [origin.config.get("annex.uuid")])

    # 4. ephemeral clone from a bare repo
    from datalad.cmd import GitWitlessRunner
    runner = GitWitlessRunner()
    runner.run(['git', 'clone', '--bare', origin_path, bare_path])
    runner.run(['git', 'annex', 'init'], cwd=bare_path)

    eph_from_bare = clone(bare_path, clone3_path, reckless='ephemeral')
    can_symlink = has_symlink_capability()

    if can_symlink:
        # Bare repo uses dirhashlower by default, while a standard repo uses
        # dirhashmixed. Symlinking different object trees doesn't really work.
        # Don't test that here, since this is not a matter of the "ephemeral"
        # option alone. We should have such a setup in the RIA tests and test
        # for data access there.
        # Here we only test for the correct linking.
        eph_annex = eph_from_bare.repo.dot_git / 'annex'
        ok_(eph_annex.is_symlink())
        ok_(eph_annex.resolve().samefile(Path(bare_path) / 'annex'))


@with_tempfile(mkdir=True)
def test_clone_unborn_head(path):
    ds_origin = Dataset(op.join(path, "a")).create()
    repo = ds_origin.repo
    managed = repo.is_managed_branch()

    # The setup below is involved, mostly because it's accounting for adjusted
    # branches. The scenario itself isn't so complicated, though:
    #
    #   * a checked out default branch with no commits
    #   * a (potentially adjusted) "abc" branch with commits.
    #   * a (potentially adjusted) "chooseme" branch whose tip commit has a
    #     more recent commit than any in "abc".
    (ds_origin.pathobj / "foo").write_text("foo content")
    ds_origin.save(message="foo")
    for res in repo.for_each_ref_(fields="refname"):
        ref = res["refname"]
        if DEFAULT_BRANCH in ref:
            repo.update_ref(ref.replace(DEFAULT_BRANCH, "abc"), ref)
            repo.call_git(["update-ref", "-d", ref])
    repo.update_ref("HEAD",
                    "refs/heads/{}".format(
                        "adjusted/abc(unlocked)" if managed else "abc"),
                    symbolic=True)
    abc_ts = int(repo.format_commit("%ct"))
    repo.call_git(["checkout", "-b", "chooseme", "abc~1"])
    if managed:
        repo.adjust()
    (ds_origin.pathobj / "bar").write_text("bar content")
    with set_date(abc_ts + 1):
        ds_origin.save(message="bar")
    # Make the git-annex branch the most recently updated ref so that we test
    # that it is skipped.
    with set_date(abc_ts + 2):
        ds_origin.drop("bar", check=False)
    ds_origin.repo.checkout(DEFAULT_BRANCH, options=["--orphan"])

    ds = clone(ds_origin.path, op.join(path, "b"))
    # We landed on the branch with the most recent commit, ignoring the
    # git-annex branch.
    branch = ds.repo.get_active_branch()
    eq_(ds.repo.get_corresponding_branch(branch) or branch,
        "chooseme")
    eq_(ds_origin.repo.get_hexsha("chooseme"),
        ds.repo.get_hexsha("chooseme"))
    # In the context of this test, the clone should be on an adjusted branch if
    # the source landed there initially because we're on the same file system.
    eq_(managed, ds.repo.is_managed_branch())


@with_tempfile(mkdir=True)
def test_clone_unborn_head_no_other_ref(path):
    ds_origin = Dataset(op.join(path, "a")).create(annex=False)
    ds_origin.repo.call_git(["update-ref", "-d",
                             "refs/heads/" + DEFAULT_BRANCH])
    with swallow_logs(new_level=logging.WARNING) as cml:
        clone(source=ds_origin.path, path=op.join(path, "b"))
        assert_in("could not find a branch with commits", cml.out)


@with_tempfile(mkdir=True)
def test_clone_unborn_head_sub(path):
    ds_origin = Dataset(op.join(path, "a")).create()
    ds_origin_sub = Dataset(op.join(path, "a", "sub")).create()
    managed = ds_origin_sub.repo.is_managed_branch()
    ds_origin.save(message="foo")
    sub_repo = ds_origin_sub.repo
    # As with test_clone_unborn_head(), the setup below is complicated mostly
    # because it's accounting for adjusted branches, but the scenario itself
    # isn't too complicated:
    #
    #   * a submodule's HEAD points to a checked out branch with no commits
    #     while a (potentially adjusted) "other" branch has commits
    #
    #   * the parent repo has the tip of "other" as the last recorded state
    for res in sub_repo.for_each_ref_(fields="refname"):
        ref = res["refname"]
        if DEFAULT_BRANCH in ref:
            sub_repo.update_ref(ref.replace(DEFAULT_BRANCH, "other"), ref)
            sub_repo.call_git(["update-ref", "-d", ref])
    sub_repo.update_ref(
        "HEAD",
        "refs/heads/{}".format(
            "adjusted/other(unlocked)" if managed else "other"),
        symbolic=True)
    # END complicated handling for adjusted branches
    ds_origin.save()
    ds_origin_sub.repo.checkout(DEFAULT_BRANCH, options=["--orphan"])

    ds_cloned = clone(source=ds_origin.path, path=op.join(path, "b"))
    ds_cloned_sub = ds_cloned.get(
        "sub", result_xfm="datasets", return_type="item-or-list")

    branch = ds_cloned_sub.repo.get_active_branch()
    eq_(ds_cloned_sub.repo.get_corresponding_branch(branch) or branch,
        "other")
    # In the context of this test, the clone should be on an adjusted branch if
    # the source landed there initially because we're on the same file system.
    eq_(managed, ds_cloned_sub.repo.is_managed_branch())


@skip_if_no_network
@with_tempfile
def test_gin_cloning(path):
    # can we clone a public ds anoynmously from gin and retrieve content
    ds = clone('https://gin.g-node.org/datalad/datalad-ci-target', path)
    ok_(ds.is_installed())
    annex_path = op.join('annex', 'two')
    git_path = op.join('git', 'one')
    eq_(ds.repo.file_has_content(annex_path), False)
    eq_(ds.repo.is_under_annex(git_path), False)
    result = ds.get(annex_path)
    assert_result_count(result, 1)
    assert_status('ok', result)
    eq_(result[0]['path'], op.join(ds.path, annex_path))
    ok_file_has_content(op.join(ds.path, annex_path), 'two\n')
    ok_file_has_content(op.join(ds.path, git_path), 'one\n')


@with_tree(tree={"special": {"f0": "0"}})
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_fetch_git_special_remote(url_path, url, path):
    url_path = Path(url_path)
    path = Path(path)
    ds_special = Dataset(url_path / "special").create(force=True)
    if ds_special.repo.is_managed_branch():
        # TODO: git-annex-init fails in the second clone call below when this is
        # executed under ./tools/eval_under_testloopfs.
        raise SkipTest("Test fails on managed branch")
    ds_special.save()
    ds_special.repo.call_git(["update-server-info"])

    clone_url = url + "special/.git"
    ds_a = clone(clone_url, path / "a")
    ds_a.repo._run_annex_command(
        "initremote",
        annex_options=["special", "type=git", "autoenable=true",
                       "location=" + clone_url])

    # Set up a situation where a file is present only on the special remote,
    # and its existence is known only to the special remote's git-annex branch.
    (ds_special.pathobj / "f1").write_text("1")
    ds_special.save()
    ds_special.repo.call_git(["update-server-info"])

    ds_a.repo.fetch("origin")
    ds_a.repo.merge("origin/" + DEFAULT_BRANCH)

    ds_b = clone(ds_a.path, path / "other")
    ds_b.get("f1")
    ok_(ds_b.repo.file_has_content("f1"))
