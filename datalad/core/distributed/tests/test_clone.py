# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test clone action

"""


from datalad.tests.utils import (
    get_datasets_topdir,
    integration,
    slow
)

import logging
import os
import os.path as op

from unittest.mock import patch

from datalad.config import ConfigManager
from datalad import consts
from datalad.api import (
    create,
    clone,
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
    create_tree,
    with_tempfile,
    assert_in,
    with_tree,
    with_testrepos,
    eq_,
    neq_,
    ok_,
    assert_false,
    ok_file_has_content,
    assert_not_in,
    assert_raises,
    assert_status,
    assert_message,
    assert_result_count,
    assert_result_values_equal,
    ok_startswith,
    assert_repo_status,
    serve_path_via_http,
    swallow_logs,
    use_cassette,
    skip_if_no_network,
    skip_if,
    with_sameas_remote,
    known_failure,
    known_failure_appveyor,
    patch_config,
)
from datalad.core.distributed.clone import (
    decode_source_spec,
    _get_installationpath_from_url,
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


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_reckless(src, top_path):
    ds = clone(src, top_path, reckless=True,
               result_xfm='datasets', return_type='item-or-list')
    eq_(ds.config.get('annex.hardlink', None), 'true')
    # actual value is 'auto', because True is a legacy value and we map it
    eq_(ds.config.get('datalad.clone.reckless', None), 'auto')
    eq_(ds.repo.repo_info()['untrusted repositories'][0]['here'], True)
    # now, if we clone another repo into this one, it will inherit the setting
    # without having to provide it explicitly
    sub = ds.clone(src, 'sub', result_xfm='datasets', return_type='item-or-list')
    eq_(sub.config.get('datalad.clone.reckless', None), 'auto')
    eq_(sub.config.get('annex.hardlink', None), 'true')


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


@skip_if(on_windows or not os.geteuid(), "Will fail under super-user")
@with_tempfile(mkdir=True)
def test_clone_report_permission_issue(tdir):
    pdir = Path(tdir) / 'protected'
    pdir.mkdir()
    # make it read-only
    pdir.chmod(0o555)
    with chpwd(pdir):
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
    with chpwd(path), swallow_logs(new_level=9) as cml:
        clone_lev3 = clone('clone_lev2', 'clone_lev3')
        # we called git-annex-init; see gh-4367:
        cml.assert_logged(msg=r"[^[]*Running: \[('git', 'annex'|'git-annex'), "
                              r"'init'",
                          match=False,
                          level='Level 9')
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


def _move2store(storepath, d):
    # make a bare clone of it into a local that matches the organization
    # of a ria dataset store
    store_loc = str(storepath / d.id[:3] / d.id[3:])
    d.repo.call_git(['clone', '--bare', d.path, store_loc])
    d.siblings('configure', name='store', url=str(store_loc),
               result_renderer='disabled')
    Runner(cwd=store_loc).run(['git', 'update-server-info'])


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
        eq_(cloneds.config.get('datalad.get.subdataset-source-candidate-origin'),
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
    eq_(cloned_by_label.config.get('datalad.get.subdataset-source-candidate-origin'),
        'ria+ssh://somelabel#{id}')


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
            'datalad.get.subdataset-source-candidate-origin'),
            'ria+%s#{id}' % url)


@skip_if_no_network
@with_tempfile()
def test_ria_http_storedataladorg(path):
    # can we clone from the store w/o any dedicated config
    ds = clone('ria+http://store.datalad.org#{}'.format(datalad_store_testds_id), path)
    ok_(ds.is_installed())
    eq_(ds.id, datalad_store_testds_id)


@with_tempfile(mkdir=True)
def test_clone_unborn_head(path):
    ds_origin = Dataset(op.join(path, "a")).create()
    repo = ds_origin.repo
    managed = repo.is_managed_branch()

    # The setup below is involved, mostly because it's accounting for adjusted
    # branches. The scenario itself isn't so complicated, though:
    #
    #   * a checked out master branch with no commits
    #   * a (potentially adjusted) "abc" branch with commits.
    #   * a (potentially adjusted) "chooseme" branch whose tip commit has a
    #     more recent commit than any in "abc".
    (ds_origin.pathobj / "foo").write_text("foo content")
    ds_origin.save(message="foo")
    for res in repo.for_each_ref_(fields="refname"):
        ref = res["refname"]
        if "master" in ref:
            repo.update_ref(ref.replace("master", "abc"), ref)
            repo.call_git(["update-ref", "-d", ref])
    repo.update_ref("HEAD",
                    "refs/heads/{}".format(
                        "adjusted/abc(unlocked)" if managed else "abc"),
                    symbolic=True)
    repo.call_git(["checkout", "-b", "chooseme", "abc~1"])
    if managed:
        repo.adjust()
    (ds_origin.pathobj / "bar").write_text("bar content")
    ds_origin.save(message="bar")
    # Try to make the git-annex branch the most recently updated ref so that we
    # test that it is skipped.
    ds_origin.drop("bar", check=False)
    ds_origin.repo.checkout("master", options=["--orphan"])

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
    # TODO: On master, update to use annex=False.
    ds_origin = Dataset(op.join(path, "a")).create(no_annex=True)
    ds_origin.repo.call_git(["update-ref", "-d", "refs/heads/master"])
    with swallow_logs(new_level=logging.WARNING) as cml:
        clone(source=ds_origin.path, path=op.join(path, "b"))
        assert_in("could not find a branch with commits", cml.out)


@with_tempfile(mkdir=True)
def test_clone_unborn_head_sub(path):
    ds_origin = Dataset(op.join(path, "a")).create()
    ds_origin_sub = Dataset(op.join(path, "a", "sub")).create()
    managed = ds_origin_sub.repo.is_managed_branch()
    ds_origin_sub.repo.call_git(["branch", "-m", "master", "other"])
    ds_origin.save()
    ds_origin_sub.repo.checkout("master", options=["--orphan"])

    ds_cloned = clone(source=ds_origin.path, path=op.join(path, "b"))
    ds_cloned_sub = ds_cloned.get(
        "sub", result_xfm="datasets", return_type="item-or-list")

    branch = ds_cloned_sub.repo.get_active_branch()
    eq_(ds_cloned_sub.repo.get_corresponding_branch(branch) or branch,
        "other")
    # In the context of this test, the clone should be on an adjusted branch if
    # the source landed there initially because we're on the same file system.
    eq_(managed, ds_cloned_sub.repo.is_managed_branch())
