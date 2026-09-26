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
from botocore.exceptions import EndpointConnectionError
from requests.exceptions import (
    ChunkedEncodingError,
    ProxyError,
    ReadTimeout,
)
from urllib3.exceptions import ProtocolError

from datalad.downloaders.base import (
    _MAX_RETRY_DELAY,
    BaseDownloader,
    is_transient_download_error,
)
from datalad.downloaders.http import HTTPDownloader
from datalad.support.exceptions import (
    CapturedException,
    IncompleteDownloadError,
)
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_greater,
    assert_in,
    assert_not_in,
    swallow_logs,
    with_tempfile,
)


def test_docstring():
    pass


@pytest.mark.ai_generated
@pytest.mark.parametrize("exc", [
    ConnectionResetError("reset by peer"),
    BrokenPipeError("broken pipe"),
    TimeoutError("timed out"),
    IncompleteRead(b'123', 100),
    OSError(errno.ENETUNREACH, "Network is unreachable"),
    ProtocolError("Connection broken"),
    ChunkedEncodingError("bad chunk"),
    ReadTimeout("took too long"),
    ProxyError("proxy went away"),  # by its base, requests' ConnectionError
    EndpointConnectionError(endpoint_url="https://example.com"),
])
def test_is_transient_download_error(exc):
    assert is_transient_download_error(exc)
    wrapper = RuntimeError("wrapped")
    wrapper.__cause__ = exc
    assert is_transient_download_error(wrapper)


@pytest.mark.ai_generated
@pytest.mark.parametrize("exc", [
    OSError(errno.ENOSPC, "No space left on device"),
    OSError(errno.EACCES, "Permission denied"),
    ValueError("not a network problem"),
    ssl.SSLCertVerificationError("bad certificate"),
])
def test_is_not_transient_download_error(exc):
    assert not is_transient_download_error(exc)
    # nor when merely raised while handling a transient one
    exc.__context__ = ConnectionResetError("reset by peer")
    assert not is_transient_download_error(exc)


@pytest.mark.ai_generated
@with_tempfile(content="123")
def test_warn_if_not_enough_space(path=None):
    url = "http://example.com/f.dat"
    with swallow_logs(new_level=logging.WARNING) as cml:
        BaseDownloader._warn_if_not_enough_space(url, path, 1024 ** 6)
        assert_in("the download is likely to fail", cml.out)
        assert_in("on the file system holding %s" % op.dirname(path), cml.out)
    with swallow_logs(new_level=logging.WARNING) as cml:
        BaseDownloader._warn_if_not_enough_space(url, path, 1)
        BaseDownloader._warn_if_not_enough_space(url, path, None)
        assert_equal(cml.out, '')


@pytest.mark.ai_generated
@with_tempfile
def test_get_transfer_error(path=None):
    url = "http://example.com/f.dat"

    def get_error(exc, target_size=1000):
        with open(path, 'wb') as fp:
            fp.write(b'123')
            return BaseDownloader._get_transfer_error(
                exc, url, path, fp, target_size)

    err = get_error(ConnectionResetError("reset by peer"))
    assert isinstance(err, IncompleteDownloadError)
    assert_equal(str(err),
                 "Transfer of %s was interrupted (3 Bytes of 1.0 kB stored)"
                 % url)
    assert_in("of an unknown total", str(get_error(ValueError(), None)))

    for errnum in (errno.ENOSPC, errno.EDQUOT):
        err = get_error(OSError(errnum, "No space left on device"))
        assert not isinstance(err, IncompleteDownloadError)
        assert_in("Ran out of space", str(err))
        assert_in("free on the file system holding %s" % op.dirname(path),
                  str(err))

    err = get_error(ValueError("no idea"))
    assert not isinstance(err, IncompleteDownloadError)
    assert_in("Failed to download", str(err))
    assert_not_in("no idea", str(err))
    # the free space is named only when short
    assert_not_in("free", str(err))
    with patch('datalad.downloaders.base._get_free_space', return_value=5):
        assert_in("only 5 Bytes free", str(get_error(ValueError())))
    # and left out when unknown
    with patch('datalad.downloaders.base.shutil.disk_usage',
               side_effect=OSError(errno.EACCES, "nope")), \
            swallow_logs():
        assert_in("(3 Bytes of 1.0 kB stored)",
                  str(get_error(OSError(errno.ENOSPC, "full"))))


@pytest.mark.ai_generated
def test_sleep_before_retry():
    delays = []
    ce = CapturedException(ValueError("nope"))
    with patch('datalad.downloaders.base.time.sleep', delays.append), \
            swallow_logs():
        for attempt in (1, 2, 5000):
            BaseDownloader._sleep_before_retry(ce, attempt, 5000)
    assert_greater(delays[1], delays[0])
    assert_equal(delays[-1], _MAX_RETRY_DELAY)


@pytest.mark.ai_generated
@with_tempfile(mkdir=True)
def test_download_announces_the_destination(path=None):
    for target, expected in (
            (path, "into directory '%s'" % path),
            (op.join(path, "new", ""), "into directory '%s'" % op.join(path, "new", "")),
            (op.join(path, "f.dat"), "into '%s'" % op.join(path, "f.dat")),
            (None, "into the current directory")):
        with swallow_logs(new_level=logging.INFO) as cml, \
                patch.object(HTTPDownloader, 'access'):
            HTTPDownloader().download("http://example.com/f.dat", path=target)
        assert_in(expected, cml.out)
