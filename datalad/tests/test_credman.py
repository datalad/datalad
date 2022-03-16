# ex: set sts=4 ts=4 sw=4 noet:
# -*- coding: utf-8 -*-
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""

"""
from unittest.mock import patch

from datalad.config import ConfigManager
from datalad.distribution.dataset import Dataset
from datalad.credman import (
    CredentialManager,
    _get_cred_cfg_var,
)
from datalad.support.keyring_ import MemoryKeyring
from datalad.tests.utils import (
    assert_in,
    assert_not_in,
    assert_raises,
    eq_,
    patch_config,
    with_tempfile,
)


def test_credmanager():
    # we want all tests to bypass the actual system keyring
    with patch('datalad.support.keyring_.keyring', MemoryKeyring()):
        check_credmanager()


def check_credmanager():
    cfg = ConfigManager()
    credman = CredentialManager(cfg)
    # doesn't work with thing air
    assert_raises(ValueError, credman.get)
    eq_(credman.get('donotexiststest'), None)
    eq_(credman.get(crazy='empty'), None)
    # smoke test for legacy credential retrieval code
    eq_(credman.get('donotexiststest', type='user_password'), None)
    # does not fiddle with a secret that is readily provided
    eq_(credman.get('dummy', secret='mike', _type_hint='token'),
        dict(type='token', secret='mike'))

    # no instructions what to do, no legacy entry, nothing was changed
    # but the secret was written to the keystore
    eq_(credman.set('mycred', secret='some'), dict(secret='some'))
    # redo but with timestep
    assert_in('last-used',
              credman.set('lastusedcred', _lastused=True, secret='some'))
    # first property store attempt
    eq_(credman.set('changed', secret='some', prop='val'),
        dict(secret='some', prop='val'))
    # second, no changing the secret, but changing the prop, albeit with
    # the same value, change report should be empty
    eq_(credman.set('changed', prop='val'), dict())
    # change secret, with value pulled from config
    try:
        cfg.set('datalad.credential.changed.secret', 'envsec',
                scope='override')
        eq_(credman.set('changed', secret=None), dict(secret='envsec'))
    finally:
        cfg.unset('datalad.credential.changed.secret', scope='override')

    # remove non-existing property, secret not report, because unchanged
    eq_(credman.set('mycred', dummy=None), dict(dummy=None))
    assert_not_in(_get_cred_cfg_var("mycred", "dummy"), cfg)

    # set property
    eq_(credman.set('mycred', dummy='good', this='that'),
        dict(dummy='good', this='that'))
    # ensure set
    eq_(credman.get('mycred'), dict(dummy='good', this='that', secret='some'))
    # remove individual property
    eq_(credman.set('mycred', dummy=None), dict(dummy=None))
    # ensure removal
    eq_(credman.get('mycred'), dict(this='that', secret='some'))

    # test full query and constrained query
    q = list(credman.query_())
    eq_(len(q), 3)
    # now query for one of the creds created above
    q = list(credman.query_(prop='val'))
    eq_(len(q), 1)
    eq_(q[0][0], 'changed')
    eq_(q[0][1]['prop'], 'val')
    # and now a query with no match
    q = list(credman.query_(prop='val', funky='town'))
    eq_(len(q), 0)

    # remove complete credential
    credman.remove('mycred')
    eq_(credman.get('mycred'), None)


@with_tempfile
def test_credman_local(path):
    ds = Dataset.create(path)
    credman = CredentialManager(ds.config)

    # deposit a credential into the dataset's config, and die trying to
    # remove it
    ds.config.set('datalad.credential.stupid.secret', 'really', scope='branch')
    assert_raises(RuntimeError, credman.remove, 'stupid')

    # but it manages for the local scope
    ds.config.set('datalad.credential.notstupid.secret', 'really', scope='local')
    credman.remove('notstupid')


def test_query():
    # we want all tests to bypass the actual system keyring
    with patch('datalad.support.keyring_.keyring', MemoryKeyring()):
        check_query()


def check_query():
    cfg = ConfigManager()
    credman = CredentialManager(cfg)
    # set a bunch of credentials with a common realm AND timestamp
    for i in range(3):
        credman.set(
            f'cred{i}',
            _lastused=True,
            secret=f'diff{i}',
            realm='http://ex.com/login',
        )
    # now a credential with the common realm, but without a timestamp
    credman.set(
        'crednotime',
        _lastused=False,
        secret='notime',
        realm='http://ex.com/login',
    )
    # and the most recent one (with timestamp) is an unrelated one
    credman.set('unrelated', _lastused=True, secret='unrelated')

    # now we want all credentials that match the realm, sorted by
    # last-used timestamp -- most recent first
    slist = credman.query(realm='http://ex.com/login', _sortby='last-used')
    eq_(['cred2', 'cred1', 'cred0', 'crednotime'],
        [i[0] for i in slist])
    # same now, but least recent first, importantly no timestamp stays last
    slist = credman.query(realm='http://ex.com/login', _sortby='last-used',
                          _reverse=False)
    eq_(['cred0', 'cred1', 'cred2', 'crednotime'],
        [i[0] for i in slist])
