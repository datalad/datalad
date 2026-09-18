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
from http.client import IncompleteRead

import pytest

from datalad.downloaders.base import (
    BaseDownloader,
    _describe_transfer,
    is_transient_download_error,
)
from datalad.support.exceptions import (
    AccessDeniedError,
    DownloadError,
    IncompleteDownloadError,
)
from datalad.tests.utils_pytest import (
    assert_equal,
    assert_in,
    assert_not_in,
    swallow_logs,
    with_tempfile,
)


def test_docstring():
    pass


def _oserror(errnum):
    return OSError(errnum, "some message")


@pytest.mark.ai_generated
@pytest.mark.parametrize("exc", [
    ConnectionResetError("reset by peer"),
    BrokenPipeError("broken pipe"),
    TimeoutError("timed out"),
    IncompleteRead(b'123', 100),
    # errnos which python does not give a dedicated OSError subclass
    _oserror(errno.ENETUNREACH),
    _oserror(errno.EHOSTUNREACH),
    # 3rd party exceptions are recognized by name, so a stand-in suffices
    type('ProtocolError', (Exception,), {})("Connection broken"),
    type('ChunkedEncodingError', (Exception,), {})("bad chunk"),
    type('EndpointConnectionError', (Exception,), {})("could not connect"),
    # ... and so are their subclasses, e.g. requests' ProxyError through the
    # ConnectionError it derives from
    type('ProxyError', (type('ConnectionError', (Exception,), {}),), {})("no proxy"),
])
def test_is_transient_download_error(exc):
    assert is_transient_download_error(exc)
    # also when buried in a chain of wrapping exceptions, the way the
    # libraries used by the downloaders tend to report them
    try:
        try:
            raise exc
        except Exception as e:
            raise RuntimeError("wrapped") from e
    except RuntimeError as e:
        assert is_transient_download_error(e)


@pytest.mark.ai_generated
def test_is_transient_download_error_requests_subclasses():
    # the real thing, not a stand-in: these derive from requests' own
    # ConnectionError/Timeout rather than carrying a name we list
    from requests.exceptions import (
        ProxyError,
        ReadTimeout,
    )
    assert is_transient_download_error(ProxyError("proxy went away"))
    assert is_transient_download_error(ReadTimeout("took too long"))


@pytest.mark.ai_generated
@pytest.mark.parametrize("exc", [
    # retrying will not free up any space
    _oserror(errno.ENOSPC),
    _oserror(errno.EACCES),
    ValueError("not a network problem at all"),
    # a certificate does not become valid by trying again
    type('SSLCertVerificationError', (Exception,), {})("bad certificate"),
])
def test_is_not_transient_download_error(exc):
    assert not is_transient_download_error(exc)


@pytest.mark.ai_generated
def test_is_transient_download_error_ignores_context():
    # only an explicit `raise ... from ...` says that the transient failure
    # is the reason; a permanent one merely raised while handling it is not
    # to be retried
    try:
        try:
            raise ConnectionResetError("reset by peer")
        except ConnectionResetError:
            raise ValueError("server returned malformed metadata")
    except ValueError as e:
        assert e.__context__ is not None  # the chain is there, just not a cause
        assert not is_transient_download_error(e)


@pytest.mark.ai_generated
def test_is_transient_download_error_reference_loop():
    # a chain which refers back to itself must not send us spinning
    exc = ValueError("a")
    exc.__cause__ = exc
    assert not is_transient_download_error(exc)


@pytest.mark.ai_generated
@with_tempfile(content="123")
def test_describe_transfer(path=None):
    # size of the file on disk is used when not given explicitly
    descr = _describe_transfer(path, target_size=1000)
    assert_in("3 Bytes out of 1.0 kB downloaded", descr)
    assert_in("free on the file system of %s" % path, descr)
    # an unknown total is stated as such, and not made up
    assert_in("out of an unknown total", _describe_transfer(path))
    # a path we know nothing about yields no information on the transfer
    # itself, but the free space of its file system is still reported
    assert_not_in("downloaded", _describe_transfer(path + "-not-there"))
    assert_in("free on the file system", _describe_transfer(path + "-not-there"))
    # without a path there is nothing to report on, but also nothing to crash on
    assert _describe_transfer(None)


@pytest.mark.ai_generated
@with_tempfile(content="123")
def test_warn_if_not_enough_space(path=None):
    url = "http://example.com/f.dat"
    # a download which cannot possibly fit is called out upfront, since
    # otherwise it just breaks off at a random offset -- see
    # https://github.com/ReproNim/containers/issues/169
    with swallow_logs(new_level=logging.WARNING) as cml:
        BaseDownloader._warn_if_not_enough_space(url, path, 1024 ** 6)
        assert_in(url, cml.out)
        assert_in("the download is likely to fail", cml.out)
    # but a download which fits, or one of unknown size, is not
    with swallow_logs(new_level=logging.WARNING) as cml:
        BaseDownloader._warn_if_not_enough_space(url, path, 1)
        BaseDownloader._warn_if_not_enough_space(url, path, None)
        assert_equal(cml.out, '')


@pytest.mark.ai_generated
@with_tempfile(content="123")
def test_get_transfer_error(path=None):
    url = "http://example.com/f.dat"

    def get_error(exc):
        return BaseDownloader._get_transfer_error(
            exc, url, path, target_size=1000)

    # a lost connection is reported as retryable -- see access()
    err = get_error(ConnectionResetError("reset by peer"))
    assert isinstance(err, IncompleteDownloadError)
    assert_in(url, str(err))
    assert_in("3 Bytes out of 1.0 kB downloaded", str(err))

    # a full file system is not: retrying would only waste the bandwidth.
    # Same for a quota, which is how a full file system looks on many a
    # shared cluster
    for errnum in (errno.ENOSPC, errno.EDQUOT):
        err = get_error(OSError(errnum, "No space left on device"))
        assert isinstance(err, DownloadError)
        assert not isinstance(err, IncompleteDownloadError)
        assert_in("Ran out of space", str(err))
        assert_in("free on the file system", str(err))

    # a session which already classified its own failure is handed back
    # untouched -- access() acts on the type
    original = AccessDeniedError("credentials went stale")
    assert get_error(original) is original

    # anything else is a plain failure, still with the transfer spelled out
    err = get_error(ValueError("no idea"))
    assert isinstance(err, DownloadError)
    assert not isinstance(err, IncompleteDownloadError)
    assert_in("Failed to download", str(err))
    assert_in("3 Bytes out of 1.0 kB downloaded", str(err))
    # the exception itself is not rendered into the message -- it belongs
    # into the __cause__, see ReproNim/containers#169
    assert_not_in("no idea", str(err))
