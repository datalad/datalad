# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Provide access to stuff (html, data files) via HTTP and HTTPS

"""


from six.moves.urllib.parse import urlsplit

from ..utils import auto_repr
from ..utils import assure_dict_from_str
from ..dochelpers import borrowkwargs
from ..support.network import get_url_straight_filename
from ..support.network import rfc2822_to_epoch, iso8601_to_epoch

from .base import Authenticator
from .base import BaseDownloader, DownloaderSession
from .base import DownloadError, TargetFileAbsent
from ..support.s3 import boto, S3ResponseError, OrdinaryCallingFormat
from ..support.s3 import get_bucket
from ..support.status import FileStatus

import logging
from logging import getLogger
lgr = getLogger('datalad.http')
boto_lgr = logging.getLogger('boto')
# not in effect at all, probably those are setup later
#boto_lgr.handlers = lgr.handlers  # Use our handlers

__docformat__ = 'restructuredtext'


@auto_repr
class S3Authenticator(Authenticator):
    """Authenticator for S3 AWS
    """

    DEFAULT_CREDENTIAL_TYPE = 'aws-s3'

    def __init__(self, *args, **kwargs):
        super(S3Authenticator, self).__init__(*args, **kwargs)
        self.connection = None
        self.bucket = None

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
        conn_kwargs = {}
        if bucket_name.lower() != bucket_name:
            # per http://stackoverflow.com/a/19089045/1265472
            conn_kwargs['calling_format'] = OrdinaryCallingFormat()
        credentials = credential()

        lgr.info("S3 session: Connecting to the bucket %s", bucket_name)

        self.connection = conn = boto.connect_s3(
            credentials['key_id'], credentials['secret_id'],
            security_token=credentials.get('session'),
            **conn_kwargs
        )
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
            return self.key.get_contents_as_string(encoding='utf-8', **kwargs)


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
    def _parse_url(cls, url):
        """Parses s3:// url and returns bucket name, prefix, additional query elements
         as a dict (such as VersionId)"""
        rec = urlsplit(url)
        assert(rec.scheme == 's3')
        # TODO: needs replacement to assure_ since it doesn't
        # deal with non key=value
        return rec.netloc, rec.path.lstrip('/'), assure_dict_from_str(rec.query, sep='&') or {}

    def _establish_session(self, url, allow_old=True):
        """

        Parameters
        ----------
        allow_old: bool, optional
          If a Downloader allows for persistent sessions by some means -- flag
          instructs either to use previous session, or establish a new one

        Returns
        -------
        bool
          To state if old instance of a session/authentication was used
        """
        bucket_name = self._parse_url(url)[0]
        if allow_old and self._bucket:
            if self._bucket.name == bucket_name:
                lgr.debug(
                    "S3 session: Reusing previous connection to bucket %s",
                    bucket_name
                )
                return True  # we used old
            else:
                lgr.warning("No support yet for multiple buckets per S3Downloader")

        lgr.debug("S3 session: Reconnecting to the bucket")
        self._bucket = self.authenticator.authenticate(bucket_name, self.credential)
        return False

    def get_downloader_session(self, url, **kwargs):
        bucket_name, url_filepath, params = self._parse_url(url)
        if params:
            newkeys = set(params.keys()) - {'versionId'}
            if newkeys:
                raise NotImplementedError("Did not implement support for %s" % newkeys)
        assert(self._bucket.name == bucket_name)  # must be the same

        try:
            key = self._bucket.get_key(url_filepath, version_id=params.get('versionId', None))
        except S3ResponseError as e:
            raise DownloadError("S3 refused to provide the key for %s from url %s: %s"
                                % (url_filepath, url, e))
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
