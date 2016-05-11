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


import re
import os
from os.path import exists, join as opj, isdir
from six.moves.urllib.parse import urljoin, urlsplit

from ..ui import ui
from ..utils import auto_repr
from ..utils import assure_dict_from_str
from ..dochelpers import borrowkwargs, exc_str
from ..support.network import get_url_straight_filename
from ..support.network import rfc2822_to_epoch, iso8601_to_epoch

from .base import Authenticator
from .base import BaseDownloader
from .base import DownloadError, AccessDeniedError, TargetFileAbsent
from ..support.s3 import boto, S3ResponseError
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

    #def authenticate(self, url, credential, session, update=False):
    def authenticate(self, bucket_name, credential):
        """Authenticates to the specified bucket using provided credentials

        Returns
        -------
        bucket
        """
        lgr.info("S3 session: Connecting to the bucket %s", bucket_name)
        credentials = credential()
        if not boto:
            raise RuntimeError("%s requires boto module which is N/A" % self)

        # Shut up boto if we do not care to listen ;)
        boto_lgr.setLevel(
            logging.CRITICAL
            if lgr.getEffectiveLevel() > 1
            else logging.DEBUG
        )

        conn = boto.connect_s3(credentials['key_id'], credentials['secret_id'])
        try:
            bucket = conn.get_bucket(bucket_name)
        except S3ResponseError as e:
            # can initially deny or error to connect to the specific bucket by name,
            # and we would need to list which buckets are available under following
            # credentials:
            lgr.debug("Cannot access bucket %s by name", bucket_name)
            all_buckets = conn.get_all_buckets()
            all_bucket_names = [b.name for b in all_buckets]
            lgr.debug("Found following buckets %s", ', '.join(all_bucket_names))
            if bucket_name in all_bucket_names:
                bucket = all_buckets[all_bucket_names.index(bucket_name)]
            elif e.error_code == 'AccessDenied':
                raise AccessDeniedError(exc_str(e))
            else:
                raise DownloadError("No S3 bucket named %s found. Initial exception: %s"
                                    % (bucket_name, exc_str(e)))

        return bucket


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
                lgr.debug("S3 session: Reusing previous bucket")
                return True  # we used old
            else:
                lgr.warning("No support yet for multiple buckets per S3Downloader")

        lgr.debug("S3 session: Reconnecting to the bucket")
        self._bucket = self.authenticator.authenticate(bucket_name, self.credential)
        return False

    def _get_download_details(self, url, **kwargs):
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

        def download_into_fp(f=None, pbar=None, size=None):
            # S3 specific (the rest is common with e.g. http)
            def pbar_callback(downloaded, totalsize):
                assert(totalsize == key.size)
                if pbar:
                    try:
                        pbar.update(downloaded)
                    except:
                        pass  # do not let pbar spoil our fun
            headers = {}
            kwargs = dict(headers=headers, cb=pbar_callback)
            if size:
                headers['Range'] = 'bytes=0-%d' % (size-1)
            if f:
                # TODO: May be we could use If-Modified-Since
                # see http://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectGET.html
                key.get_contents_to_file(f, num_cb=0, **kwargs)
            else:
                return key.get_contents_as_string(encoding='utf-8', **kwargs)

        # TODO: possibly return a "header"
        return download_into_fp, target_size, url_filename, headers

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
