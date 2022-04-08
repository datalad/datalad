# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to Amazon S3 objects.
"""

import re

from urllib.parse import urlsplit, unquote as urlunquote

from ..utils import (
    auto_repr,
    ensure_dict_from_str,
)
from ..dochelpers import (
    borrowkwargs,
)
from ..support.network import (
    get_url_straight_filename,
    iso8601_to_epoch,
    rfc2822_to_epoch,
)

from .base import Authenticator
from .base import BaseDownloader, DownloaderSession
from ..support.exceptions import (
    AccessPermissionExpiredError,
    CapturedException,
    TargetFileAbsent,
)
from ..support.s3 import (
    Key,
    OrdinaryCallingFormat,
    S3ResponseError,
    boto,
    get_bucket,
    try_multiple_dec_s3,
)
from ..support.status import FileStatus

import logging
from logging import getLogger
lgr = getLogger('datalad.s3')
boto_lgr = logging.getLogger('boto')
# not in effect at all, probably those are setup later
#boto_lgr.handlers = lgr.handlers  # Use our handlers

__docformat__ = 'restructuredtext'


@auto_repr
class S3Authenticator(Authenticator):
    """Authenticator for S3 AWS
    """
    allows_anonymous = True
    DEFAULT_CREDENTIAL_TYPE = 'aws-s3'

    def __init__(self, *args, host=None, **kwargs):
        """

        Parameters
        ----------
        host: str, optional
          In some cases it is necessary to provide host to connect to. Passed
          to boto.connect_s3
        """
        super(S3Authenticator, self).__init__(*args, **kwargs)
        self.connection = None
        self.bucket = None
        self._conn_kwargs = {}
        if host:
            self._conn_kwargs['host'] = host

    def authenticate(self, bucket_name, credential, cache=True):
        """Authenticates to the specified bucket using provided credentials

        Returns
        -------
        bucket
        """

        if not boto:
            raise RuntimeError("%s requires boto module which is N/A" % self)

        # Shut up boto if we do not care to listen ;)
        boto_lgr.setLevel(
            logging.CRITICAL
            if lgr.getEffectiveLevel() > 1
            else logging.DEBUG
        )

        # credential might contain 'session' token as well
        # which could be provided   as   security_token=<token>.,
        # see http://stackoverflow.com/questions/7673840/is-there-a-way-to-create-a-s3-connection-with-a-sessions-token
        conn_kwargs = self._conn_kwargs.copy()
        if bucket_name.lower() != bucket_name:
            # per http://stackoverflow.com/a/19089045/1265472
            conn_kwargs['calling_format'] = OrdinaryCallingFormat()

        if credential is not None:
            credentials = credential()
            conn_kind = "with authentication"
            conn_args = [credentials['key_id'], credentials['secret_id']]
            conn_kwargs['security_token'] = credentials.get('session')
        else:
            conn_kind = "anonymously"
            conn_args = []
            conn_kwargs['anon'] = True
        if '.' in bucket_name:
            conn_kwargs['calling_format'] = OrdinaryCallingFormat()

        lgr.info(
            "S3 session: Connecting to the bucket %s %s", bucket_name, conn_kind
        )
        self.connection = conn = boto.connect_s3(*conn_args, **conn_kwargs)
        self.bucket = bucket = get_bucket(conn, bucket_name)
        return bucket


@auto_repr
class S3DownloaderSession(DownloaderSession):
    def __init__(self, size=None, filename=None, url=None, headers=None,
                 key=None):
        super(S3DownloaderSession, self).__init__(
            size=size, filename=filename, headers=headers, url=url
        )
        self.key = key

    def download(self, f=None, pbar=None, size=None):
        # S3 specific (the rest is common with e.g. http)
        def pbar_callback(downloaded, totalsize):
            assert (totalsize == self.key.size)
            if pbar:
                try:
                    pbar.update(downloaded)
                except:  # MIH: what does it do? MemoryError?
                    pass  # do not let pbar spoil our fun

        headers = {}
        # report for every % for files > 10MB, otherwise every 10%
        kwargs = dict(headers=headers, cb=pbar_callback,
                      num_cb=100 if self.key.size > 10*(1024**2) else 10)
        if size:
            headers['Range'] = 'bytes=0-%d' % (size - 1)
        if f:
            # TODO: May be we could use If-Modified-Since
            # see http://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectGET.html
            self.key.get_contents_to_file(f, **kwargs)
        else:
            return self.key.get_contents_as_string(encoding=None, **kwargs)


@auto_repr
class S3Downloader(BaseDownloader):
    """Downloader from AWS S3 buckets
    """

    _DEFAULT_AUTHENTICATOR = S3Authenticator

    @borrowkwargs(BaseDownloader)
    def __init__(self, **kwargs):
        super(S3Downloader, self).__init__(**kwargs)
        self._bucket = None

    @property
    def bucket(self):
        return self._bucket

    def reset(self):
        self._bucket = None

    @classmethod
    def _parse_url(cls, url, bucket_only=False):
        """Parses s3:// url and returns bucket name, prefix, additional query elements
         as a dict (such as VersionId)"""
        rec = urlsplit(url)
        if bucket_only:
            return rec.netloc
        assert(rec.scheme == 's3')
        # We are often working with urlencoded URLs so we could safely interact
        # with git-annex via its text based protocol etc.  So, if URL looks like
        # it was urlencoded the filepath, we should revert back to an original key
        # name.  Since we did not demarcate whether it was urlencoded, we will do
        # magical check, which would fail if someone had % followed by two digits
        filepath = rec.path.lstrip('/')
        if re.search('%[0-9a-fA-F]{2}', filepath):
            lgr.debug("URL unquoting S3 URL filepath %s", filepath)
            filepath = urlunquote(filepath)
        # TODO: needs replacement to ensure_ since it doesn't
        # deal with non key=value
        return rec.netloc, filepath, ensure_dict_from_str(rec.query, sep='&') or {}

    def _establish_session(self, url, allow_old=True):
        """

        Parameters
        ----------
        allow_old: bool, optional
          If a Downloader allows for persistent sessions by some means -- flag
          instructs whether to use previous session, or establish a new one

        Returns
        -------
        bool
          To state if old instance of a session/authentication was used
        """
        bucket_name = self._parse_url(url, bucket_only=True)
        if allow_old and self._bucket:
            if self._bucket.name == bucket_name:
                try:
                    self._check_credential()
                    lgr.debug(
                        "S3 session: Reusing previous connection to bucket %s",
                        bucket_name
                    )
                    return True  # we used old
                except AccessPermissionExpiredError:
                    lgr.debug("S3 session: credential expired")
            else:
                lgr.warning("No support yet for multiple buckets per S3Downloader")

        lgr.debug("S3 session: Reconnecting to the bucket")
        self._bucket = try_multiple_dec_s3(self.authenticator.authenticate)(
            bucket_name, self.credential)
        return False

    def _check_credential(self):
        """Quick check of the credential if known on either it has not expired

        Raises
        ------
        AccessPermissionExpiredError
          if credential is found to be expired
        """
        if self.credential and self.credential.is_expired:
            raise AccessPermissionExpiredError(
                "Credential %s has expired" % self.credential)

    def _get_key(self, key_name, version_id=None, headers=None):
        try:
            return self._bucket.get_key(key_name, version_id=version_id, headers=headers)
        except S3ResponseError as e:
            if e.status != 400:
                raise  # we will not deal with those here
            # e.g. 400 Bad request could happen due to timed out key.
            # Since likely things went bad if credential expired, just raise general
            # AccessDeniedError. Logic upstream should retry
            self._check_credential()
            ce1 = CapturedException(e)
            lgr.debug("bucket.get_key (HEAD) failed with %s, trying GET request now",
                      ce1)
            try:
                return self._get_key_via_get(key_name, version_id=version_id, headers=headers)
            except S3ResponseError:
                # propagate S3 exceptions since they actually can provide the reason why we failed!
                raise
            except Exception as e2:
                ce2 = CapturedException(e2)
                lgr.debug("We failed to get a key via HEAD due to %s and then via partial GET due to %s",
                          ce1, ce2)
                # reraise original one
                raise e

    def _get_key_via_get(self, key_name, version_id=None, headers=None):
        """Get key information via GET so we can get error_code if any

        The problem with bucket.get_key is that it uses HEAD request.
        With that request response header has only the status (e.g. 400)
        but not a specific error_code.  That makes it impossible to properly
        react on failed requests (wait? re-auth?).

        Yarik found no easy way in boto to reissue the request with GET,
        so this code is lobotomized version of _get_key_internal but with GET
        instead of HEAD and thus providing body into error handling.
        """
        query_args_l = []
        if version_id:
            query_args_l.append('versionId=%s' % version_id)
        query_args = '&'.join(query_args_l) or None
        bucket = self._bucket
        headers = headers or {}
        headers['Range'] = 'bytes=0-0'
        response = bucket.connection.make_request(
            'GET',
            bucket.name,
            key_name,
            headers=headers,
            query_args=query_args)
        body = response.read()
        if response.status // 100 == 2:
            # it was all good
            k = bucket.key_class(bucket)
            provider = bucket.connection.provider
            k.metadata = boto.utils.get_aws_metadata(response.msg, provider)
            for field in Key.base_fields:
                k.__dict__[field.lower().replace('-', '_')] = \
                    response.getheader(field)
            crange, crange_size = response.getheader('content-range'), None
            if crange:
                # should look like 'bytes 0-0/50993'
                if not crange.startswith('bytes 0-0/'):
                    # we will just spit out original exception and be done -- we have tried!
                    raise ValueError("Got content-range %s which I do not know how to handle to "
                                     "get the full size" % repr(crange))
                crange_size = int(crange.split('/', 1)[-1])
                k.size = crange_size
            # the following machinations are a workaround to the fact that
            # apache/fastcgi omits the content-length header on HEAD
            # requests when the content-length is zero.
            # See http://goo.gl/0Tdax for more details.
            if response.status != 206:  # partial content
                # assume full return of 0 bytes etc
                clen_size = int(response.getheader('content-length'), 0)

                if crange_size is not None:
                    if crange_size != clen_size:
                        raise ValueError(
                            "We got content-length %d and size from content-range %d - they do "
                            "not match", clen_size, crange_size)
                k.size = clen_size
            k.name = key_name
            k.handle_version_headers(response)
            k.handle_encryption_headers(response)
            k.handle_restore_headers(response)
            k.handle_storage_class_header(response)
            k.handle_addl_headers(response.getheaders())
            return k
        else:
            if response.status == 404:
                return None
            else:
                raise bucket.connection.provider.storage_response_error(
                    response.status, response.reason, body)

    def get_downloader_session(self, url, **kwargs):
        bucket_name, url_filepath, params = self._parse_url(url)
        if params:
            newkeys = set(params.keys()) - {'versionId'}
            if newkeys:
                raise NotImplementedError("Did not implement support for %s" % newkeys)
        assert(self._bucket.name == bucket_name)  # must be the same

        self._check_credential()
        try:
            key = try_multiple_dec_s3(self._get_key)(
                url_filepath, version_id=params.get('versionId', None)
            )
        except S3ResponseError as e:
            raise TargetFileAbsent("S3 refused to provide the key for %s from url %s"
                                % (url_filepath, url)) from e
        if key is None:
            raise TargetFileAbsent("No key returned for %s from url %s" % (url_filepath, url))

        target_size = key.size  # S3 specific
        headers = {
            'Content-Length': key.size,
            'Content-Disposition': key.name
        }

        if key.last_modified:
            headers['Last-Modified'] = rfc2822_to_epoch(key.last_modified)

        # Consult about filename
        url_filename = get_url_straight_filename(url)

        if 'versionId' not in params and key.version_id:
            # boto adds version_id to the request if it is known present.
            # It is a good idea in general to avoid race between moment of retrieving
            # the key information and actual download.
            # But depending on permissions, we might be unable (like in the case with NDA)
            # to download a guaranteed version of the key.
            # So we will just download the latest version (if still there)
            # if no versionId was specified in URL
            # Alternative would be to make this a generator and generate sessions
            # but also remember if the first download succeeded so we do not try
            # again to get versioned one first.
            key.version_id = None
            # TODO: ask NDA to allow download of specific versionId?

        return S3DownloaderSession(
            size=target_size,
            filename=url_filename,
            url=url,
            headers=headers,
            key=key
        )

    @classmethod
    def get_key_headers(cls, key, dateformat='rfc2822'):
        headers = {
            'Content-Length': key.size,
            'Content-Disposition': key.name
        }

        if key.last_modified:
            # boto would return time string the way amazon returns which returns
            # it in two different ones depending on how key information was obtained:
            # https://github.com/boto/boto/issues/466
            headers['Last-Modified'] = {'rfc2822': rfc2822_to_epoch,
                                        'iso8601': iso8601_to_epoch}[dateformat](key.last_modified)
        return headers

    @classmethod
    def get_status_from_headers(cls, headers):
        # TODO: duplicated with http functionality
        # convert to FileStatus
        return FileStatus(
            size=headers.get('Content-Length'),
            mtime=headers.get('Last-Modified'),
            filename=headers.get('Content-Disposition')
        )

    @classmethod
    def get_key_status(cls, key, dateformat='rfc2822'):
        return cls.get_status_from_headers(cls.get_key_headers(key, dateformat=dateformat))
