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

import logging
import re
from logging import getLogger
from threading import Lock
from urllib.parse import unquote as urlunquote
from urllib.parse import urlsplit

import boto3
import botocore

from ..dochelpers import borrowkwargs
from ..support.exceptions import (
    AccessDeniedError,
    AccessPermissionExpiredError,
    TargetFileAbsent,
)
from ..support.network import get_url_straight_filename
from ..support.status import FileStatus
from ..utils import (
    auto_repr,
    ensure_dict_from_str,
)
from .base import (
    Authenticator,
    BaseDownloader,
    DownloaderSession,
)

lgr = getLogger('datalad.s3')
boto_lgr = logging.getLogger('boto3')
# not in effect at all, probably those are setup later
#boto_lgr.handlers = lgr.handlers  # Use our handlers

import warnings

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
          A URL to the endpoint or just a host name (then prepended with https://).
          Define either `host` or `region`, not both.
        region: str, optional
          will be passed to s3 client as region_name.
          Default region could also be defined in the `~/.aws/config`
          file or by setting the AWS_DEFAULT_REGION environment variable.
        """
        super(S3Authenticator, self).__init__(*args, **kwargs)
        self.client = None
        self.region = region
        if host:
            if region:
                raise ValueError("Define either 'host' or 'region', not both.")
            if not (host.startswith('http://') or host.startswith('https://')):
                host = 'https://' + host
        self.host = host

    def authenticate(self, bucket_name, credential, cache=True):
        """Authenticates to the specified bucket using provided credentials

        Sets up a boto3 S3 client. Uses supplied DataLad credentials
        or connects anonymously - in that order of preference.

        No test is done to verify bucket access, to avoid hitting the case
        where a bucket cannot be listed but its objects can be accessed.

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
                endpoint_url=self.host,
                aws_access_key_id=credentials["key_id"],
                aws_secret_access_key=credentials["secret_id"],
                aws_session_token=credentials.get("session"),
                config=conf,
            )
        else:
            # Boto3 has mechanisms to read credentials from the environment
            # or configuration files.
            # Signed requests for publicly accessible objects may fail, so
            # for now we will assume that anonymous access is preferred.
            session = boto3.Session()
            conn_kind = "anonymously"
            conf = conf.merge(
                botocore.config.Config(signature_version=botocore.UNSIGNED)
            )
            s3client = session.client("s3", region_name=self.region, config=conf)

        lgr.info(
            "S3 session: Connecting to the bucket %s %s", bucket_name, conn_kind
        )

        self.client = s3client
        return s3client


@auto_repr
class S3DownloaderSession(DownloaderSession):
    def __init__(self, size=None, filename=None, url=None, headers=None,
                 client=None,
                 bucket: str=None, key: str=None, version_kwargs: dict=None):
        super(S3DownloaderSession, self).__init__(
            size=size, filename=filename, headers=headers, url=url
        )
        self.client = client
        self.bucket = bucket
        self.key = key
        self.version_kwargs = version_kwargs
        self.pbar_callback_lock = Lock()

    def download(self, f=None, pbar=None, size=None):
        # S3 specific (the rest is common with e.g. http)
        def pbar_callback(downloaded):
            with self.pbar_callback_lock:
                if pbar:
                    try:
                        pbar.update(downloaded, increment=True)
                    except:  # MIH: what does it do? MemoryError?
                        pass  # do not let pbar spoil our fun

        if f:
            if size is None:
                # TODO: May be we could use If-Modified-Since
                # see http://docs.aws.amazon.com/AmazonS3/latest/API/RESTObjectGET.html
                # note (MSz): in boto3, see client.head_object(IfModifiedSince)
                self.client.download_fileobj(
                    Fileobj=f,
                    Callback=pbar_callback,
                    Bucket=self.bucket,
                    Key=self.key,
                    ExtraArgs=self.version_kwargs,
                )
                return
            # The problem is that there is no Range support in download_fileobj
            # https://github.com/boto/boto3/issues/1215 ,
            # so we have to use get_object, and will just save it into a file.
            # It will not work for large transfers, but hopefully we do not have them
            # for file downloads

        # return the contents of the file as bytes
        # ATM no progress indication!
        kwargs = dict(Bucket=self.bucket, Key=self.key, **self.version_kwargs)
        if size is not None:
            # This will work only for relatively small transfers but
            # in general we do not expect requests with large-ish size.
            kwargs['Range'] = f'bytes=0-{size - 1}'
        s3_response = self.client.get_object(
            **kwargs,
            # There is no callback for get_object!
            # Callback=pbar_callback,
        )
        content = s3_response.get('Body').read()
        if f:
            f.write(content)
        else:
            return content


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
        """Create a DownloaderSession for a given URL

        This function sets up a DownloaderSession object and reads the
        information necessary (e.g. size, headers) by issuing a
        head_object query.

        Returns
        -------
        S3DownloaderSession
        """
        bucket_name, url_filepath, params = self._parse_url(url)
        if params:
            newkeys = set(params.keys()) - {'versionId'}
            if newkeys:
                raise NotImplementedError("Did not implement support for %s" % newkeys)
            # see: boto3.s3.transfer.S3Transfer.ALLOWED_DOWNLOAD_ARGS
            version_kwargs = {"VersionId": params.get("versionId")}
        else:
            version_kwargs = {}

        assert(self._bucket_name == bucket_name)  # must be the same

        self._check_credential()

        # this is where the *real* access check (for the object) will happen;
        # may raise botocore.exceptions.ClientError for 404 not found
        # or 403 forbidden
        try:
            object_meta = self.client.head_object(
                Bucket=bucket_name,
                Key=url_filepath,
                **version_kwargs,
            )
        except botocore.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "403":
                raise AccessDeniedError(e) from e
            elif error_code == "404":
                raise TargetFileAbsent(url + " does not exist") from e
            elif error_code == '400' and version_kwargs:
                try:
                    self.client.head_object(
                        Bucket=bucket_name,
                        Key=url_filepath,
                    )
                    raise TargetFileAbsent(url + " has unknown version specified") from e
                except botocore.exceptions.ClientError as e2:
                    raise e
            else:
                raise

        target_size = object_meta.get('ContentLength')  # S3 specific
        headers = self.get_obj_headers(
            object_meta, other={'Content-Disposition': url_filepath})

        # Consult about filename
        url_filename = get_url_straight_filename(url)

        # head_object also reports VersionId if found, but we don't
        # take it from there, only from the URL; original comment by
        # yoh below
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

        return S3DownloaderSession(
            size=target_size,
            filename=url_filename,
            url=url,
            headers=headers,
            client=self.client,
            bucket=bucket_name,
            key=url_filepath,
            version_kwargs=version_kwargs,
        )

    @classmethod
    def get_obj_headers(cls, obj_meta, other=None):
        """Get a headers dict from head_object output

        Picks, renames, and converts certain keys from the boto3
        head_object response. Some (like Content-Disposition) may need
        to be added via kwargs.

        Note: the head_object output also includes the relevant
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
