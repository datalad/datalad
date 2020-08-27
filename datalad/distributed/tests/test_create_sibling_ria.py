# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import os.path as op

from datalad import cfg as dl_cfg
from datalad.api import (
    clone,
    Dataset
)
from datalad.tests.utils import (
    attr,
    assert_in,
    assert_raises,
    assert_repo_status,
    assert_result_count,
    chpwd,
    eq_,
    skip_if_on_windows,
    skip_ssh,
    slow,
    with_tempfile,
    with_tree,
)
from datalad.utils import Path
from functools import wraps


def with_store_insteadof(func):
    """decorator to set a (user-) config and clean up afterwards"""

    @wraps(func)
    @attr('with_config')
    def  _wrap_with_store_insteadof(*args, **kwargs):
        host = args[0]
        base_path = args[1]
        try:
            dl_cfg.set('url.ria+{prot}://{host}{path}.insteadOf'
                       ''.format(prot='ssh' if host else 'file',
                                 host=host if host else '',
                                 path=base_path),
                       'ria+ssh://test-store:', where='global', reload=True)
            return func(*args, **kwargs)
        finally:
            dl_cfg.unset('url.ria+{prot}://{host}{path}.insteadOf'
                         ''.format(prot='ssh' if host else 'file',
                                   host=host if host else '',
                                   path=base_path),
                         where='global', reload=True)
    return  _wrap_with_store_insteadof


@with_tempfile
def test_invalid_calls(path):

    ds = Dataset(path).create()

    # no argument:
    assert_raises(TypeError, ds.create_sibling_ria)

    # same name for git- and special remote:
    assert_raises(ValueError, ds.create_sibling_ria, 'ria+file:///some/where',
                  name='some', storage_name='some')


@skip_if_on_windows  # running into short path issues; same as gh-4131
@with_tempfile
@with_store_insteadof
@with_tree({'ds': {'file1.txt': 'some'},
            'sub': {'other.txt': 'other'},
            'sub2': {'evenmore.txt': 'more'}})
@with_tempfile(mkdir=True)
def _test_create_store(host, base_path, ds_path, clone_path):

    ds = Dataset(ds_path).create(force=True)

    subds = ds.create('sub', force=True)
    subds2 = ds.create('sub2', force=True, no_annex=True)
    ds.save(recursive=True)
    assert_repo_status(ds.path)

    # don't specify special remote. By default should be git-remote + "-storage"
    res = ds.create_sibling_ria("ria+ssh://test-store:", "datastore")
    assert_result_count(res, 1, status='ok', action='create-sibling-ria')
    eq_(len(res), 1)

    # remotes exist, but only in super
    siblings = ds.siblings(result_renderer=None)
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in siblings})
    sub_siblings = subds.siblings(result_renderer=None)
    eq_({'here'}, {s['name'] for s in sub_siblings})
    sub2_siblings = subds2.siblings(result_renderer=None)
    eq_({'here'}, {s['name'] for s in sub2_siblings})

    # TODO: post-update hook was enabled

    # check bare repo:
    git_config = Path(base_path) / ds.id[:3] / ds.id[3:] / 'config'
    assert git_config.exists()
    content = git_config.read_text()
    assert_in("[datalad \"ora-remote\"]", content)
    super_uuid = ds.config.get("remote.{}.annex-uuid".format('datastore-storage'))
    assert_in("uuid = {}".format(super_uuid), content)

    # implicit test of success by ria-installing from store:
    ds.publish(to="datastore", transfer_data='all')
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
        assert_in(op.join('ds', 'file1.txt'),
                  installed_ds.repo.get_annexed_files())
        assert_result_count(installed_ds.get(op.join('ds', 'file1.txt')),
                            1,
                            status='ok',
                            action='get',
                            path=op.join(installed_ds.path, 'ds', 'file1.txt'))

    # now, again but recursive.
    res = ds.create_sibling_ria("ria+ssh://test-store:", "datastore",
                                recursive=True, existing='reconfigure')
    eq_(len(res), 3)
    assert_result_count(res, 1, path=str(ds.pathobj), status='ok', action="create-sibling-ria")
    assert_result_count(res, 1, path=str(subds.pathobj), status='ok', action="create-sibling-ria")
    assert_result_count(res, 1, path=str(subds2.pathobj), status='ok', action="create-sibling-ria")

    # remotes now exist in super and sub
    siblings = ds.siblings(result_renderer=None)
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in siblings})
    sub_siblings = subds.siblings(result_renderer=None)
    eq_({'datastore', 'datastore-storage', 'here'},
        {s['name'] for s in sub_siblings})
    # but no special remote in plain git subdataset:
    sub2_siblings = subds2.siblings(result_renderer=None)
    eq_({'datastore', 'here'},
        {s['name'] for s in sub2_siblings})

    # for testing trust_level parameter, redo for each label:
    for trust in ['trust', 'semitrust', 'untrust']:
        ds.create_sibling_ria("ria+ssh://test-store:",
                              "datastore",
                              existing='reconfigure',
                              trust_level=trust)
        res = ds.repo.repo_info()
        assert_in('[datastore-storage]',
                  [r['description']
                   for r in res['{}ed repositories'.format(trust)]])


@slow  # 11 + 42 sec on travis
def test_create_simple():

    yield _test_create_store, None
    # TODO: Skipped due to gh-4436
    yield skip_if_on_windows(skip_ssh(_test_create_store)), 'datalad-test'


# TODO: explicit naming of special remote
