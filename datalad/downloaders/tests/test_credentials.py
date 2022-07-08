# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for credentials"""

from unittest.mock import patch

from datalad import cfg as dlcfg
from datalad.api import Dataset
from datalad.support.external_versions import external_versions
from datalad.support.keyring_ import (
    Keyring,
    MemoryKeyring,
)
from datalad.tests.utils_pytest import (
    SkipTest,
    assert_equal,
    assert_false,
    assert_in,
    assert_raises,
    assert_true,
    ok_file_has_content,
    skip_if,
    with_tempfile,
    with_testsui,
)

from ..credentials import (
    AWS_S3,
    CompositeCredential,
    GitCredential,
    UserPassword,
)


@with_testsui(responses=[
    'user1', 'password1',
    # when we do provide user to enter_new
    'newpassword',
])
def test_cred1_enter_new():
    keyring = MemoryKeyring()
    cred = UserPassword("name", keyring=keyring)
    assert_false(cred.is_known)
    assert_equal(cred.enter_new(), None)
    assert_true(cred.is_known)
    assert_equal(keyring.get('name', 'user'), 'user1')
    assert_equal(keyring.get('name', 'password'), 'password1')
    keyring.delete('name')
    assert_raises(KeyError, keyring.delete, 'name', 'user')
    assert_raises(KeyError, keyring.delete, 'name')
    assert_equal(keyring.get('name', 'user'), None)

    # Test it blowing up if we provide unknown field
    with assert_raises(ValueError) as cme:
        cred.enter_new(username='user')
    assert_in('field(s): username.  Known but not specified: password, user',
              str(cme.value))

    # Test that if user is provided, it is not asked
    cred.enter_new(user='user2')
    assert_equal(keyring.get('name', 'user'), 'user2')
    assert_equal(keyring.get('name', 'password'), 'newpassword')


@with_testsui(responses=['password1', 'newuser', 'newpassword'])
def test_cred1_call():
    keyring = MemoryKeyring()
    cred = UserPassword("name", keyring=keyring)
    # we will set the name but not the password, expecting UI
    # requesting it
    assert_equal(keyring.set('name', 'user', 'user1'), None)
    assert_equal(keyring.get('name', 'user'), 'user1')
    assert_equal(cred(), {'user': 'user1', 'password': 'password1'})
    assert_equal(keyring.get('name', 'password'), 'password1')
    # without intervention the same credentials will be reused
    # in subsequent attempts
    assert_equal(cred(), {'user': 'user1', 'password': 'password1'})
    with patch.dict(dlcfg._merged_store, {'datalad.credentials.force-ask': 'yes'}):
        assert_equal(cred(), {'user': 'newuser', 'password': 'newpassword'})
    assert_equal(keyring.get('name', 'user'), 'newuser')
    assert_equal(keyring.get('name', 'password'), 'newpassword')


def test_keyring():
    # mock out keyring methods and test that we are providing correct values
    # with 'datalad-' prefix
    raise SkipTest("provide tests for Keyring which interfaces keyring module")


def _cred1_adapter(composite, user=None, password=None):
    """Just a sample adapter from one user/pw type to another"""
    return dict(user=user + "_1", password=password + "_2")


class _CCred1(CompositeCredential):
    """A Simple composite credential which will do some entries transformation
    """
    _CREDENTIAL_CLASSES = (UserPassword, UserPassword)
    _CREDENTIAL_ADAPTERS = (_cred1_adapter,)


@with_testsui(responses=['user1', 'password1',
                         'user2', 'password2'])
def test_composite_credential1():
    # basic test of composite credential
    keyring = MemoryKeyring()
    cred = _CCred1("name", keyring=keyring)
    # When queried, does the chain
    assert_equal(cred(), {'user': 'user1_1', 'password': 'password1_2'})
    # But the "Front" credential is exposed to the user
    assert_equal(cred.get('user'), 'user1')
    assert_equal(keyring.get('name', 'user'), 'user1')
    assert_raises(ValueError, cred.get, 'unknown_field')
    assert_equal(cred.get('password'), 'password1')
    assert_equal(keyring.get('name', 'password'), 'password1')
    # ATM composite credential stores "derived" ones unconditionally in the
    # keyring as well
    assert_equal(keyring.get('name:1', 'user'), 'user1_1')
    assert_equal(keyring.get('name:1', 'password'), 'password1_2')

    # and now enter new should remove "derived" entries
    cred.enter_new()
    assert_equal(keyring.get('name', 'user'), 'user2')
    assert_equal(keyring.get('name', 'password'), 'password2')
    # we immediately refresh all credentials in the chain
    assert_equal(keyring.get('name:1', 'user'), 'user2_1')
    assert_equal(keyring.get('name:1', 'password'), 'password2_2')
    assert_equal(cred(), {'user': 'user2_1', 'password': 'password2_2'})


def test_credentials_from_env():
    keyring = Keyring()
    cred = AWS_S3("test-s3", keyring=keyring)
    assert_false(cred.is_known)
    assert_equal(cred.get('key_id'), None)
    assert_equal(cred.get('secret_id'), None)

    def _check1():
        assert_equal(cred.get('key_id'), '1')
        assert_false(cred.is_known)

    def _check2():
        assert_equal(cred.get('key_id'), '1')
        assert_equal(cred.get('secret_id'), '2')
        assert_true(cred.is_known)

    # this is the old way, should still work
    with patch.dict('os.environ', {'DATALAD_test_s3_key_id': '1'}):
        _check1()
        with patch.dict('os.environ', {'DATALAD_test_s3_secret_id': '2'}):
            _check2()
        assert_false(cred.is_known)  # no memory of the past

    # here is the new way
    import datalad
    try:
        with patch.dict('os.environ', {'DATALAD_CREDENTIAL_test__s3_key__id': '1'}):
            datalad.cfg.reload()
            _check1()
            with patch.dict('os.environ', {'DATALAD_CREDENTIAL_test__s3_secret__id': '2'}):
                datalad.cfg.reload()
                _check2()
            datalad.cfg.reload()
            assert_false(cred.is_known)  # no memory of the past
    finally:
        datalad.cfg.reload()


@skip_if(not external_versions['keyrings.alt'])
@with_tempfile
def test_delete_not_crashing(path=None):
    # although in above test we just use/interact with Keyring without specifying
    # any custom one, there we do not change it so I guess it is ok. Here we want
    # a real keyring backend which we will alter
    from keyrings.alt.file import PlaintextKeyring
    kb = PlaintextKeyring()
    kb.filename = path

    keyring = Keyring(keyring_backend=kb)
    cred = UserPassword("test1", keyring=keyring)

    cred.set(user="user1", password="password")
    ok_file_has_content(path, ".*test1.*", re_=True)  # keyring backend saves where we expect

    # manually delete one component of the credential
    cred._keyring.delete(cred.name, next(iter(cred._FIELDS)))

    # now delete entire credential -- we must not crash
    cred.delete()
    try:
        ok_file_has_content(path, ".*test1.*", re_=True)  # keyring backend saves where we expect
        raise AssertionError("keyring still has our key")
    except AssertionError:
        pass


@with_tempfile
def test_gitcredential_read(path=None):

    matching_url = "https://example.datalad.org"
    non_matching_url = "http://some.other.org"
    ds = Dataset(path).create()

    # Set configs so git-credential does provide something,
    # using an inline helper:

    # Simple inline credential helper to provide a password to read.
    # Strangely seems to pass on windows. Probably depends on what git is
    # passing this definition to (git-bash).
    cred_helper = \
        "!f() { test \"$1\" = get && echo \"password=apassword\"; }; f"

    ds.config.add(f"credential.{matching_url}.username", "auser",
                  scope="local")
    ds.config.add(f"credential.{matching_url}.helper", cred_helper,
                  scope="local")

    # we can get those credentials when the context is right:
    cred = GitCredential("some", auth_url=matching_url,
                         dataset=ds)

    assert_true(cred.is_known)
    assert_equal(cred.get('user'), 'auser')
    assert_equal(cred.get('password'), 'apassword')

    # env var overrules
    import datalad
    try:
        with patch.dict('os.environ', {'DATALAD_CREDENTIAL_some_user': 'new'}):
            datalad.cfg.reload()
            assert_true(cred.is_known)
            assert_equal(cred.get('user'), 'new')
            assert_equal(cred.get('password'), 'apassword')
            with patch.dict('os.environ',
                            {'DATALAD_CREDENTIAL_some_password': 'pwd'}):
                datalad.cfg.reload()
                assert_true(cred.is_known)
                assert_equal(cred.get('user'), 'new')
                assert_equal(cred.get('password'), 'pwd')
    finally:
        datalad.cfg.reload()

    # different context
    cred = GitCredential("some", auth_url=non_matching_url,
                         dataset=ds)
    # unknown since git-credential config doesn't match
    assert_false(cred.is_known)

    # however, w/ env vars still works:
    try:
        with patch.dict('os.environ',
                        {'DATALAD_CREDENTIAL_some_user': 'user3'}):
            datalad.cfg.reload()
            assert_false(cred.is_known)  # no pwd yet
            assert_equal(cred.get('user'), 'user3')
            assert_equal(cred.get('password'), None)
            with patch.dict('os.environ',
                            {'DATALAD_CREDENTIAL_some_password': 'pass3'}):
                datalad.cfg.reload()
                assert_true(cred.is_known)
                assert_equal(cred.get('user'), 'user3')
                assert_equal(cred.get('password'), 'pass3')
        # without the env vars unknown yet again:
        assert_false(cred.is_known)
    finally:
        datalad.cfg.reload()


@with_tempfile
def test_gitcredential(path=None):

    # Note, that credential labels are irrelevant in context of the to be tested
    # Object here.

    matching_url = "https://example.datalad.org"
    non_matching_url = "http://some.other.org"
    ds = Dataset(path).create()
    # use git native credential store
    ds.config.add("credential.helper", "store", scope='local')

    # store credentials
    cred = GitCredential("cred_label", auth_url=matching_url, dataset=ds)
    cred.set(user="dl-user", password="dl-pwd")

    # read it again
    cred2 = GitCredential("whatever", auth_url=matching_url, dataset=ds)
    assert_equal(cred2.get("user"), "dl-user")
    assert_equal(cred2.get("password"), "dl-pwd")
    # but doesn't deliver w/o matching url
    cred3 = GitCredential("whatever", auth_url=non_matching_url, dataset=ds)
    assert_equal(cred3.get("user"), None)
    assert_equal(cred3.get("password"), None)

    # delete it
    cred2.delete()

    # not there anymore
    cred4 = GitCredential("yet_another", auth_url=matching_url, dataset=ds)
    assert_equal(cred4.get("user"), None)
    assert_equal(cred4.get("password"), None)

    # delete non-existing
    cred2.delete()
