# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for credentials"""

from datalad.tests.utils import with_testsui
from datalad.tests.utils import assert_equal
from datalad.tests.utils import assert_true, assert_false
from datalad.tests.utils import assert_raises
from datalad.tests.utils import SkipTest
from datalad.support.keyring_ import MemoryKeyring
from ..credentials import Credential
from ..credentials import Credential


def test_unknown_type():
    assert_raises(ValueError, Credential, "name", "unknown_type")


@with_testsui(responses=['user1', 'password1'])
def test_cred1_enter_new():
    keyring = MemoryKeyring()
    cred = Credential("name", "user_password", keyring=keyring)
    assert_false(cred.is_known)
    assert_equal(cred.enter_new(), None)
    assert_true(cred.is_known)
    assert_equal(keyring.get('name', 'user'), 'user1')
    assert_equal(keyring.get('name', 'password'), 'password1')
    keyring.delete('name')
    assert_raises(KeyError, keyring.delete, 'name', 'user')
    assert_raises(KeyError, keyring.delete, 'name')
    assert_equal(keyring.get('name', 'user'), None)


@with_testsui(responses=['password1'])
def test_cred1_call():
    keyring = MemoryKeyring()
    cred = Credential("name", "user_password", keyring=keyring)
    # we will set the name but not the password, expecting UI
    # requesting it
    assert_equal(keyring.set('name', 'user', 'user1'), None)
    assert_equal(keyring.get('name', 'user'), 'user1')
    assert_equal(cred(), {'user': 'user1', 'password': 'password1'})
    assert_equal(keyring.get('name', 'password'), 'password1')


def test_keyring():
    # mock out keyring methods and test that we are providing correct values
    # with 'datalad-' prefix
    raise SkipTest("provide tests for Keyring which interfaces keyring module")