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

import boto3
import botocore

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

    def __init__(self, *args, host=None, region=None, **kwargs):
        """

        Parameters
        ----------
        host: str, optional
          this argument is deprecated and will be ignored; define region
          instead (you can also define a default region in your ~/.aws/config
          file or by setting the AWS_DEFAULT_REGION environment variable)
        region: str, optional
          will be passed to s3 client as region_name
        """
        super(S3Authenticator, self).__init__(*args, **kwargs)
        self.client = None
        self.region = region
        if host:
            warnings.warn(
                "Host argument is deprecated and will be ignored. "
                "Use 'region' argument instead, or define a default region "
                "in your ~/aws/config file, or set the environment variable "
                "AWS_DEFAULT_REGION",
                DeprecationWarning
            )

    def authenticate(self, bucket_name, credential, cache=True):
        """Authenticates to the specified bucket using provided credentials

        Sets up a boto3 S3 client. Uses supplied DataLad credentials,
        reads credentials from boto configuration sources (environmental
        variables or config files), or connects anonymously - in that order
        of preference. Tests the credentials for the given bucket.

        Returns
        -------
        s3client: botocore.client.S3
        """

        if not boto3:
            raise RuntimeError("%s requires boto3 module which is N/A" % self)

        # Shut up boto if we do not care to listen ;)
        boto_lgr.setLevel(
            logging.CRITICAL
            if lgr.getEffectiveLevel() > 1
            else logging.DEBUG
        )

        # use boto3 standard retry mode, not legacy
        conf_options = {"retries": {"mode": "standard"}}

        # per http://stackoverflow.com/a/19089045/1265472 & updated for boto3
        if bucket_name.lower() != bucket_name or "." in bucket_name:
            conf_options["s3"] = {"addressing_style": "path"}

        conf = botocore.config.Config(**conf_options)

        # credential might contain 'session' token as well
        # which could be provided   as   security_token=<token>.,
        # see http://stackoverflow.com/questions/7673840/is-there-a-way-to-create-a-s3-connection-with-a-sessions-token

        if credential is not None:
            credentials = credential()
            conn_kind = "with authentication"
            s3client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=credentials["key_id"],
                aws_secret_access_key=credentials["secret_id"],
                aws_session_token=credentials.get("session"),
                config=conf,
            )
        else:
            # let boto try and find credentials from config files or variables,
            # or connect anonymously if it finds none
            # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
            session = boto3.Session()
            if session.get_credentials() is not None:
                conn_kind = "with authentication"
                s3client = session.client("s3", region_name=self.region, config=conf)
            else:
                conn_kind = "anonymously"
                conf = conf.merge(
                    botocore.config.Config(signature_version=botocore.UNSIGNED)
                )
                s3client = session.client("s3", region_name=self.region, config=conf)

        lgr.info(
            "S3 session: Connecting to the bucket %s %s", bucket_name, conn_kind
        )

        # check if the bucket is accessible
        # (authentication happens only when request is made)
        #
        # note: using head_bucket() to test -- although that
        # effectively tests for List permission, not file access.  We
        # would ideally use head_object() instead, but the function in
        # its current shape only knows the bucket, not the object. Old
        # boto2 code used connect_s3 & get_bucket, which also led to
        # head_bucket implicitly, so this is not a regression.
        # https://boto3.amazonaws.com/v1/documentation/api/latest/guide/migrations3.html#accessing-a-bucket
        try:
            s3client.head_bucket(Bucket=bucket_name)
        except botocore.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                raise TargetFileAbsent(
                    "Bucket " + bucket_name + " does not exist"
                ) from e
            else:
                raise e

        self.client = s3client
        return s3client


@auto_repr
class S3DownloaderSession(DownloaderSession):
    def __init__(self, size=None, filename=None, url=None, headers=None,
                 client=None, download_kwargs=None):
        super(S3DownloaderSession, self).__init__(
            size=size, filename=filename, headers=headers, url=url
        )
        self.client = client
        self.download_kwargs = download_kwargs

    def download(self, f=None, pbar=None, size=None):
        # S3 specific (the rest is common with e.g. http)
        def pbar_callback(downloaded):
            if pbar:
                try:
                    pbar.update(downloaded, increment=True)
                except:  # MIH: what does it do? MemoryError?
                    pass  # do not let pbar spoil our fun

        if f:
            # TODO: May be we could use If-Modified-Since
            # see http://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectGET.html
            # note (mslw): in boto3, see client.head_object(IfModifiedSince)
            self.client.download_fileobj(
                Fileobj=f,
                Callback=pbar_callback,
                **self.download_kwargs,  # Bucket, Key, ExtraArgs (todo: explicit?)
            )
        else:
            # return the contents of the file as bytes
            s3_response = self.client.get_object(
                **self.download_kwargs,  # Bucket, Key, ExtraArgs
                Callback=pbar_callback,
            )
            return s3_response.get('Body').read()

@auto_repr
class S3Downloader(BaseDownloader):
    """Downloader from AWS S3 buckets
    """

    _DEFAULT_AUTHENTICATOR = S3Authenticator

    @borrowkwargs(BaseDownloader)
    def __init__(self, **kwargs):
        super(S3Downloader, self).__init__(**kwargs)
        self._client = None
        self._bucket_name = None

    @property
    def client(self):
        return self._client

    def reset(self):
        self._client = None
        self._bucket_name = None

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
        if allow_old and self.client is not None:
            if self._bucket_name == bucket_name:
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
        self._client = self.authenticator.authenticate(
            bucket_name, self.credential)
        self._bucket_name = bucket_name
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

    def get_downloader_session(self, url, **kwargs):
        bucket_name, url_filepath, params = self._parse_url(url)
        if params:
            newkeys = set(params.keys()) - {'versionId'}
            if newkeys:
                raise NotImplementedError("Did not implement support for %s" % newkeys)
            # see: boto3.s3.transfer.S3Transfer.ALLOWED_DOWNLOAD_ARGS
            extra_args = {"VersionId": params.get("versionId")}
        else:
            extra_args = {}

        assert(self._bucket_name == bucket_name)  # must be the same

        self._check_credential()

        object_meta = self.client.head_object(
            Bucket=bucket_name,
            Key=url_filepath,
            **extra_args,
        )
        # the above may raise botocore.exceptions.ClientError
        # for 404 not found or 403 forbidden

        target_size = object_meta.get('ContentLength')  # S3 specific
        headers = self.get_obj_headers(
            object_meta, other={'Content-Disposition': url_filepath})

        # Consult about filename
        url_filename = get_url_straight_filename(url)

        # head_object will report VersionId if found, but we don't take it from
        # there, only from the URL; original comment by yoh below
        #
        # It is a good idea in general to avoid race between moment of retrieving
        # the key information and actual download.
        # But depending on permissions, we might be unable (like in the case with NDA)
        # to download a guaranteed version of the key.
        # So we will just download the latest version (if still there)
        # if no versionId was specified in URL
        # Alternative would be to make this a generator and generate sessions
        # but also remember if the first download succeeded so we do not try
        # again to get versioned one first.
        # TODO: ask NDA to allow download of specific versionId?

        # download_fileobj has slightly different signature than head_object
        # we need to pass things below to the S3DownloaderSession
        s3_download_kwargs = {
            "Bucket": bucket_name,
            "Key": url_filepath,
            "ExtraArgs": extra_args if len(extra_args) > 0 else None,
        }

        return S3DownloaderSession(
            size=target_size,
            filename=url_filename,
            url=url,
            headers=headers,
            client=self.client,
            download_kwargs=s3_download_kwargs,
        )

    @classmethod
    def get_obj_headers(cls, obj_meta, other=None):
        """Get a headers dict from head_object output

        Picks, renames, and converts certain keys. Some (like
        Content-Disposition) may need to be added via kwargs. Note:
        the head_obj_metaect output also includes the relevant
        information under ['ResponseMetadata']['HTTPHeaders']
        (possibly using different data type), but this function only
        uses top-level keys.
        """
        headers = {"Content-Length": obj_meta.get("ContentLength")}
        if obj_meta.get("LastModified"):
            headers["Last-Modified"] = int(
                obj_meta.get("LastModified").timestamp())
        if other:
            headers.update(other)
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
