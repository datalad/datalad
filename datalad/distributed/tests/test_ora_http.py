import shutil

from datalad.api import Dataset
from datalad.customremotes.ria_utils import (
    create_ds_in_store,
    create_store,
)
from datalad.distributed.ora_remote import LocalIO
from datalad.distributed.tests.ria_utils import (
    common_init_opts,
    populate_dataset,
)
from datalad.support.exceptions import CommandError
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_in,
    assert_not_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    assert_status,
    known_failure_windows,
    serve_path_via_http,
    skip_if_adjusted_branch,
    with_tempfile,
)
from datalad.utils import Path

# NOTE: All we want and can test here is the HTTP functionality of the ORA
#       remote. As of now, this is get and checkpresent only, sending one
#       request each. The used URI for those requests is based on store layout
#       version 1 and dataset layout version 2. Serving archives and/or
#       different layouts via those requests is up to the server side, which we
#       don't test here.

@with_tempfile(mkdir=True)
@serve_path_via_http
@with_tempfile
def test_initremote(store_path=None, store_url=None, ds_path=None):
    ds = Dataset(ds_path).create()
    store_path = Path(store_path)
    url = "ria+" + store_url
    init_opts = common_init_opts + ['url={}'.format(url)]

    # fail when there's no RIA store at the destination
    assert_raises(CommandError, ds.repo.init_remote, 'ora-remote',
                  options=init_opts)
    # Doesn't actually create a remote if it fails
    assert_not_in('ora-remote',
                  [cfg['name']
                   for uuid, cfg in ds.repo.get_special_remotes().items()]
                  )

    # now make it a store
    io = LocalIO()
    create_store(io, store_path, '1')
    create_ds_in_store(io, store_path, ds.id, '2', '1')

    # fails on non-RIA URL
    assert_raises(CommandError, ds.repo.init_remote, 'ora-remote',
                  options=common_init_opts + ['url={}'
                                              ''.format(store_path.as_uri())]
                  )
    # Doesn't actually create a remote if it fails
    assert_not_in('ora-remote',
                  [cfg['name']
                   for uuid, cfg in ds.repo.get_special_remotes().items()]
                  )

    ds.repo.init_remote('ora-remote', options=init_opts)
    assert_in('ora-remote',
              [cfg['name']
               for uuid, cfg in ds.repo.get_special_remotes().items()]
              )
    assert_repo_status(ds.path)
    # git-annex:remote.log should have:
    #   - url
    #   - common_init_opts
    #   - archive_id (which equals ds id)
    remote_log = ds.repo.call_git(['cat-file', 'blob', 'git-annex:remote.log'],
                                  read_only=True)
    assert_in("url={}".format(url), remote_log)
    [assert_in(c, remote_log) for c in common_init_opts]
    assert_in("archive-id={}".format(ds.id), remote_log)


# TODO: on crippled FS copytree to populate store doesn't seem to work.
#       Or may be it's just the serving via HTTP that doesn't work.
#       Either way, after copytree and fsck, whereis doesn't report
#       the store as an available source.
@skip_if_adjusted_branch
@known_failure_windows  # see gh-4469
@with_tempfile(mkdir=True)
@serve_path_via_http
@with_tempfile
def test_read_access(store_path=None, store_url=None, ds_path=None):

    ds = Dataset(ds_path).create()
    populate_dataset(ds)

    files = [Path('one.txt'), Path('subdir') / 'two']
    store_path = Path(store_path)
    url = "ria+" + store_url
    init_opts = common_init_opts + ['url={}'.format(url)]

    io = LocalIO()
    create_store(io, store_path, '1')
    create_ds_in_store(io, store_path, ds.id, '2', '1')
    ds.repo.init_remote('ora-remote', options=init_opts)
    fsck_results = ds.repo.fsck(remote='ora-remote', fast=True)
    # Note: Failures in the special remote will show up as a success=False
    # result for fsck -> the call itself would not fail.
    for r in fsck_results:
        if "note" in r:
            # we could simply assert "note" to not be in r, but we want proper
            # error reporting - content of note, not just its unexpected
            # existence.
            assert_equal(r["success"], "true",
                         msg="git-annex-fsck failed with ORA over HTTP: %s" % r)
        assert_equal(r["error-messages"], [])
    store_uuid = ds.siblings(name='ora-remote',
                             return_type='item-or-list',
                             result_renderer='disabled')['annex-uuid']
    here_uuid = ds.siblings(name='here',
                            return_type='item-or-list',
                            result_renderer='disabled')['annex-uuid']

    # nothing in store yet:
    for f in files:
        known_sources = ds.repo.whereis(str(f))
        assert_in(here_uuid, known_sources)
        assert_not_in(store_uuid, known_sources)

    annex_obj_target = str(store_path / ds.id[:3] / ds.id[3:]
                           / 'annex' / 'objects')
    shutil.rmtree(annex_obj_target)
    shutil.copytree(src=str(ds.repo.dot_git / 'annex' / 'objects'),
                    dst=annex_obj_target)

    ds.repo.fsck(remote='ora-remote', fast=True)
    # all in store now:
    for f in files:
        known_sources = ds.repo.whereis(str(f))
        assert_in(here_uuid, known_sources)
        assert_in(store_uuid, known_sources)

    ds.drop('.')
    res = ds.get('.')
    assert_equal(len(res), 4)
    assert_result_count(res, 4, status='ok', type='file', action='get',
                        message="from ora-remote...")

    # try whether the reported access URL is correct
    one_url = ds.repo.whereis('one.txt', output='full'
        )[store_uuid]['urls'].pop()
    assert_status('ok', ds.download_url(urls=[one_url], path=str(ds.pathobj / 'dummy')))
