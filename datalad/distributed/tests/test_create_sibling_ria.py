# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import logging
import os.path as op
from functools import wraps
from unittest.mock import patch

from datalad import cfg as dl_cfg
from datalad.api import (
    Dataset,
    clone,
)
from datalad.support.network import get_local_file_url
from datalad.tests.utils_pytest import (
    assert_false,
    assert_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    attr,
    chpwd,
    eq_,
    known_failure_githubci_win,
    ok_exists,
    skip_if_on_windows,
    skip_ssh,
    skip_wo_symlink_capability,
    slow,
    swallow_logs,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path


def with_store_insteadof(func):
    """decorator to set a (user-) config and clean up afterwards"""

    @wraps(func)
    @attr('with_config')
    def _wrap_with_store_insteadof(*args, **kwargs):
        host = args[0]
        base_path = args[1]
        try:
            dl_cfg.set('url.ria+{prot}://{host}{path}.insteadOf'
                       ''.format(prot='ssh' if host else 'file',
                                 host=host if host else '',
                                 path=base_path),
                       'ria+ssh://test-store:', scope='global', reload=True)
            return func(*args, **kwargs)
        finally:
            dl_cfg.unset('url.ria+{prot}://{host}{path}.insteadOf'
                         ''.format(prot='ssh' if host else 'file',
                                   host=host if host else '',
                                   path=base_path),
                         scope='global', reload=True)
    return _wrap_with_store_insteadof


@with_tempfile
def test_invalid_calls(path=None):

    ds = Dataset(path).create()

    # no argument:
    assert_raises(TypeError, ds.create_sibling_ria)

    # same name for git- and special remote:
    assert_raises(ValueError, ds.create_sibling_ria, 'ria+file:///some/where',
                  name='some', storage_name='some')

    # missing ria+ URL prefix
    assert_result_count(
        ds.create_sibling_ria(
            'file:///some/where', name='some', on_failure='ignore'),
        1,
        status='error',
    )


@skip_if_on_windows  # running into short path issues; same as gh-4131
@with_tempfile
@with_store_insteadof
@with_tree({'ds': {'file1.txt': 'some'},
            'sub': {'other.txt': 'other'},
            'sub2': {'evenmore.txt': 'more'}})
@with_tempfile(mkdir=True)
def _test_create_store(host, base_path=None, ds_path=None, clone_path=None):

    ds = Dataset(ds_path).create(force=True)

    subds = ds.create('sub', force=True)
    subds2 = ds.create('sub2', force=True, annex=False)
    ds.save(recursive=True)
    assert_repo_status(ds.path)
    # don't specify special remote. By default should be git-remote + "-storage"
    res = ds.create_sibling_ria("ria+ssh://test-store:", "datastore",
                                post_update_hook=True, new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')

    # remotes exist, but only in super
    siblings = ds.siblings(result_renderer='disabled')
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in siblings})
    sub_siblings = subds.siblings(result_renderer='disabled')
    eq_({'here'}, {s['name'] for s in sub_siblings})
    sub2_siblings = subds2.siblings(result_renderer='disabled')
    eq_({'here'}, {s['name'] for s in sub2_siblings})

    # check bare repo:
    git_dir = Path(base_path) / ds.id[:3] / ds.id[3:]

    # The post-update hook was enabled.
    ok_exists(git_dir / "hooks" / "post-update")
    # And create_sibling_ria took care of an initial call to
    # git-update-server-info.
    ok_exists(git_dir / "info" / "refs")

    git_config = git_dir / 'config'
    ok_exists(git_config)
    content = git_config.read_text()
    assert_in("[datalad \"ora-remote\"]", content)
    super_uuid = ds.config.get("remote.{}.annex-uuid".format('datastore-storage'))
    assert_in("uuid = {}".format(super_uuid), content)

    # implicit test of success by ria-installing from store:
    ds.push(to="datastore")
    with chpwd(clone_path):
        if host:
            # note, we are not using the "test-store"-label here
            clone('ria+ssh://{}{}#{}'.format(host, base_path, ds.id),
                  path='test_install')
        else:
            # TODO: Whenever ria+file supports special remote config (label),
            # change here:
            clone('ria+file://{}#{}'.format(base_path, ds.id),
                  path='test_install')
        installed_ds = Dataset(op.join(clone_path, 'test_install'))
        assert installed_ds.is_installed()
        assert_repo_status(installed_ds.repo)
        eq_(installed_ds.id, ds.id)
        # Note: get_annexed_files() always reports POSIX paths.
        assert_in('ds/file1.txt',
                  installed_ds.repo.get_annexed_files())
        assert_result_count(installed_ds.get(op.join('ds', 'file1.txt')),
                            1,
                            status='ok',
                            action='get',
                            path=op.join(installed_ds.path, 'ds', 'file1.txt'))
    # repeat the call to ensure it doesn't crash (see #6950)
    res = ds.create_sibling_ria("ria+ssh://test-store:", "datastore", on_failure='ignore')
    assert_result_count(res, 1, status='error', action='create-sibling-ria', message=(
                        "a sibling %r is already configured in dataset %r",
                        'datastore', ds.path))

    # now, again but recursive.
    res = ds.create_sibling_ria("ria+ssh://test-store:", "datastore",
                                recursive=True, existing='reconfigure',
                                new_store_ok=True)
    assert_result_count(res, 1, path=str(ds.pathobj), status='ok', action="create-sibling-ria")
    assert_result_count(res, 1, path=str(subds.pathobj), status='ok', action="create-sibling-ria")
    assert_result_count(res, 1, path=str(subds2.pathobj), status='ok', action="create-sibling-ria")

    # remotes now exist in super and sub
    siblings = ds.siblings(result_renderer='disabled')
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in siblings})
    sub_siblings = subds.siblings(result_renderer='disabled')
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in sub_siblings})
    # but no special remote in plain git subdataset:
    sub2_siblings = subds2.siblings(result_renderer='disabled')
    eq_({'datastore', 'here'},
        {s['name'] for s in sub2_siblings})

    # for testing trust_level parameter, redo for each label:
    for trust in ['trust', 'semitrust', 'untrust']:
        ds.create_sibling_ria("ria+ssh://test-store:",
                              "datastore",
                              existing='reconfigure',
                              trust_level=trust,
                              new_store_ok=True)
        res = ds.repo.repo_info()
        assert_in('[datastore-storage]',
                  [r['description']
                   for r in res['{}ed repositories'.format(trust)]])


@slow  # 11 + 42 sec on travis
def test_create_simple():

    _test_create_store(None)
    # TODO: Skipped due to gh-4436
    skip_if_on_windows(skip_ssh(_test_create_store))('datalad-test')


@skip_ssh
@skip_if_on_windows  # ORA remote is incompatible with windows clients
@with_tempfile
@with_tree({'ds': {'file1.txt': 'some'},
            'sub': {'other.txt': 'other'},
            'sub2': {'evenmore.txt': 'more'}})
@with_tempfile
def test_create_push_url(detection_path=None, ds_path=None, store_path=None):

    store_path = Path(store_path)
    ds_path = Path(ds_path)
    detection_path = Path(detection_path)

    ds = Dataset(ds_path).create(force=True)
    ds.save()

    # patch SSHConnection to signal it was used:
    from datalad.support.sshconnector import SSHManager
    def detector(f, d):
        @wraps(f)
        def _wrapper(*args, **kwargs):
            d.touch()
            return f(*args, **kwargs)
        return _wrapper

    url = "ria+{}".format(store_path.as_uri())
    push_url = "ria+ssh://datalad-test{}".format(store_path.as_posix())
    assert not detection_path.exists()

    with patch('datalad.support.sshconnector.SSHManager.get_connection',
               new=detector(SSHManager.get_connection, detection_path)):

        ds.create_sibling_ria(url, "datastore", push_url=push_url,
                              new_store_ok=True)
        # used ssh_manager despite file-url hence used push-url (ria+ssh):
        assert detection_path.exists()

        # correct config in special remote:
        sr_cfg = ds.repo.get_special_remotes()[
            ds.siblings(name='datastore-storage')[0]['annex-uuid']]
        eq_(sr_cfg['url'], url)
        eq_(sr_cfg['push-url'], push_url)

        # git remote based on url (local path):
        eq_(ds.config.get("remote.datastore.url"),
            (store_path / ds.id[:3] / ds.id[3:]).as_posix())
        eq_(ds.config.get("remote.datastore.pushurl"),
            "ssh://datalad-test{}".format((store_path / ds.id[:3] / ds.id[3:]).as_posix()))

        # git-push uses SSH:
        detection_path.unlink()
        ds.push('.', to="datastore", data='nothing')
        assert detection_path.exists()

        # data push
        # Note, that here the patching has no effect, since the special remote
        # is running in a subprocess of git-annex. Hence we can't detect SSH
        # usage really. However, ORA remote is tested elsewhere - if it succeeds
        # all should be good wrt `create-sibling-ria`.
        ds.repo.call_annex(['copy', '.', '--to', 'datastore-storage'])


@skip_if_on_windows
@skip_wo_symlink_capability
@with_tempfile
@with_tempfile
@with_tempfile
def test_create_alias(ds_path=None, ria_path=None, clone_path=None):
    ds_path = Path(ds_path)
    clone_path = Path(clone_path)

    ds_path.mkdir()
    dsa = Dataset(ds_path / "a").create()

    res = dsa.create_sibling_ria(url="ria+file://{}".format(ria_path),
                                 name="origin",
                                 alias="ds-a",
                                 new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')

    ds_clone = clone(source="ria+file://{}#~ds-a".format(ria_path),
                     path=clone_path / "a")
    assert_repo_status(ds_clone.path)

    # multiple datasets in a RIA store with different aliases work
    dsb = Dataset(ds_path / "b").create()

    res = dsb.create_sibling_ria(url="ria+file://{}".format(ria_path),
                                 name="origin",
                                 alias="ds-b",
                                 new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')

    ds_clone = clone(source="ria+file://{}#~ds-b".format(ria_path),
                     path=clone_path / "b")
    assert_repo_status(ds_clone.path)

    # second dataset in a RIA store with the same alias emits a warning
    dsc = Dataset(ds_path / "c").create()

    with swallow_logs(logging.WARNING) as cml:
        res = dsc.create_sibling_ria(url="ria+file://{}".format(ria_path),
                                     name="origin",
                                     alias="ds-a",
                                     new_store_ok=True)
        assert_in("Alias 'ds-a' already exists in the RIA store, not adding an alias",
                  cml.out)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')


@skip_if_on_windows  # ORA remote is incompatible with windows clients
@with_tempfile
@with_tree({'ds': {'file1.txt': 'some'}})
def test_storage_only(base_path=None, ds_path=None):
    store_url = 'ria+' + get_local_file_url(base_path)

    ds = Dataset(ds_path).create(force=True)
    ds.save(recursive=True)
    assert_repo_status(ds.path)

    res = ds.create_sibling_ria(store_url, "datastore", storage_sibling='only',
                                new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')
    eq_(len(res), 1)

    # the storage sibling uses the main name, not -storage
    siblings = ds.siblings(result_renderer='disabled')
    eq_({'datastore', 'here'},
        {s['name'] for s in siblings})

    # smoke test that we can push to it
    res = ds.push(to='datastore')
    assert_status('ok', res)
    assert_result_count(res, 1, action='copy')


@known_failure_githubci_win  # reported in https://github.com/datalad/datalad/issues/5210
@with_tempfile
@with_tempfile
@with_tree({'ds': {'file1.txt': 'some'}})
def test_no_storage(store1=None, store2=None, ds_path=None):
    store1_url = 'ria+' + get_local_file_url(store1)
    store2_url = 'ria+' + get_local_file_url(store2)

    ds = Dataset(ds_path).create(force=True)
    ds.save(recursive=True)
    assert_repo_status(ds.path)

    res = ds.create_sibling_ria(store1_url, "datastore1", storage_sibling=False,
                                new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')
    eq_({'datastore1', 'here'},
        {s['name'] for s in ds.siblings(result_renderer='disabled')})

    # deprecated way of disabling storage still works
    res = ds.create_sibling_ria(store2_url, "datastore2",
                                storage_sibling=False, new_store_ok=True)
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')
    eq_({'datastore2', 'datastore1', 'here'},
        {s['name'] for s in ds.siblings(result_renderer='disabled')})

    # no annex/object dir should be created when there is no special remote
    # to use it.
    for s in [store1, store2]:
        p = Path(s) / ds.id[:3] / ds.id [3:] / 'annex' / 'objects'
        assert_false(p.exists())

    # smoke test that we can push to it
    res = ds.push(to='datastore1')
    assert_status('ok', res)
    # but nothing was copied, because there is no storage sibling
    assert_result_count(res, 0, action='copy')


@with_tempfile
def test_no_store(path=None):
    ds = Dataset(path).create()
    # check that we fail without '--new-store-ok' when there is no store
    assert_result_count(
        ds.create_sibling_ria(
            "'ria+file:///no/where'", "datastore",
            on_failure='ignore'),
        1,
        status="error")

# TODO: explicit naming of special remote
