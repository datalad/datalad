# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Tests for downloaders base"""

import errno
import logging
import os.path as op
import ssl
from http.client import IncompleteRead
from unittest.mock import patch

import pytest
from requests.exceptions import ProxyError
from urllib3.exceptions import ProtocolError

from datalad.downloaders.base import (
    _get_transfer_error,
    _warn_if_not_enough_space,
    is_transient_download_error,
)
from datalad.support.exceptions import IncompleteDownloadError
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_in,
    swallow_logs,
    with_tempfile,
)


def test_docstring():
    pass


@pytest.mark.ai_generated
@pytest.mark.parametrize("exc, transient", [
    (ConnectionResetError("reset by peer"), True),
    (IncompleteRead(b'123', 100), True),
    (OSError(errno.ENETUNREACH, "Network is unreachable"), True),
    (ProtocolError("Connection broken"), True),
    (ProxyError("proxy went away"), True),  # a requests.ConnectionError
    (OSError(errno.ENOSPC, "No space left on device"), False),
    (ValueError("not a network problem"), False),
    (ssl.SSLCertVerificationError("bad certificate"), False),
])
def test_is_transient_download_error(exc, transient):
    caused, handling = RuntimeError(), RuntimeError()
    caused.__cause__ = handling.__context__ = exc
    assert is_transient_download_error(exc) is transient
    assert is_transient_download_error(caused) is transient
    assert not is_transient_download_error(handling)


@pytest.mark.ai_generated
@with_tempfile(content="123")
def test_warn_if_not_enough_space(path=None):
    url = "http://example.com/f.dat"
    with swallow_logs(new_level=logging.WARNING) as cml:
        _warn_if_not_enough_space(url, path, 1024 ** 6)
        assert_in("the download is likely to fail", cml.out)
        assert_in("on the file system holding %s" % op.dirname(path), cml.out)
    with swallow_logs(new_level=logging.WARNING) as cml:
        _warn_if_not_enough_space(url, path, 1)
        _warn_if_not_enough_space(url, path, None)
        assert_equal(cml.out, '')


@pytest.mark.ai_generated
@with_tempfile
def test_get_transfer_error(path=None):
    url = "http://example.com/f.dat"

    def get_error(exc, target_size=1000):
        with open(path, 'wb') as fp:
            fp.write(b'123')
            return _get_transfer_error(exc, url, path, fp, target_size)

    err = get_error(ConnectionResetError("reset by peer"))
    assert isinstance(err, IncompleteDownloadError)
    assert_equal(str(err),
                 "Transfer of %s was interrupted (3 Bytes of 1.0 kB stored)"
                 % url)
    assert_in("of an unknown total", str(get_error(ValueError(), None)))
    # free space is named when short
    with patch('datalad.downloaders.base._get_free_space', return_value=5):
        assert_in("only 5 Bytes free", str(get_error(ConnectionResetError())))

    err = get_error(OSError(errno.ENOSPC, "No space left on device"))
    assert not isinstance(err, IncompleteDownloadError)
    assert_in("Ran out of space", str(err))
    assert_in("free on the file system holding %s" % op.dirname(path),
              str(err))
