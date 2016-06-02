# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from ..keyring_ import Keyring

from datalad.tests.utils import assert_equal


def test_Keyring():
    kr = Keyring()
    assert_equal(str(kr), 'Keyring:SecretService')
    assert_equal(repr(kr), 'Keyring()')