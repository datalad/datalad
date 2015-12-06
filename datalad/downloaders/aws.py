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

try:
    import boto
    from boto.s3.key import Key
    from boto.exception import S3ResponseError
except ImportError:
    boto = None

import re
import os
from os.path import exists, join as opj, isdir
from six.moves.urllib.parse import urljoin, urlsplit

from ..ui import ui
from ..utils import auto_repr
from ..utils import assure_dict_from_str
from ..support.network import get_url_straight_filename
from ..support.network import get_tld

from .base import Authenticator
from .base import BaseDownloader
from .base import DownloadError, AccessDeniedError

from logging import getLogger
lgr = getLogger('datalad.http')

__docformat__ = 'restructuredtext'

@auto_repr
class S3Authenticator(Authenticator):
    """Authenticator for S3 AWS
    """

    #def authenticate(self, url, credential, session, update=False):
    def authenticate(self, bucket_name, credential):
        lgr.info("S3 session: Connecting to the bucket %s", bucket_name)
        credentials = credential()
        conn = boto.connect_s3(credentials['key_id'], credentials['secret_id'])

        try:
            bucket = conn.get_bucket(bucket_name)
        except S3ResponseError as e:
            lgr.debug("Cannot access bucket %s by name", bucket_name)
            all_buckets = conn.get_all_buckets()
            all_bucket_names = [b.name for b in all_buckets]
            lgr.debug("Found following buckets %s", ', '.join(all_bucket_names))
            if bucket_name in all_bucket_names:
                bucket = all_buckets[all_bucket_names.index(bucket_name)]
            else:
                raise DownloadError("No S3 bucket named %s found" % bucket_name)

        return bucket


@auto_repr
class S3Downloader(BaseDownloader):
    """Downloader from AWS S3 buckets
    """

    def __init__(self, credential=None, authenticator=None):
        """

        Parameters
        ----------
        TODO
        """

        self.credential = credential
        if authenticator:
            if not self.credential:
                raise ValueError(
                    "Both authenticator and credentials must be provided."
                    " Got only authenticator %s" % repr(authenticator))

        if not authenticator:
            authenticator = S3Authenticator()
        else:
            assert(isinstance(authenticator, S3Authenticator))
        self.authenticator = authenticator

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


    def _download(self, url, path=None, overwrite=False):
        """

        Parameters
        ----------
        url: str
          URL to download
        path: str, optional
          Path to file where to store the downloaded content.  If None, downloaded
          content provided back in the return value (not decoded???)

        Returns
        -------
        None or bytes

        """
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

        #### Specific to download
        # TODO: Somewhat duplication with http logic, but we need this custom get_url_filename
        # handling which might have its own parameters.
        # Also we do not anyhow use original hierarchy from url

        # Consult about filename
        if path:
            if isdir(path):
                # provided path is a directory under which to save
                filename = get_url_straight_filename(url)
                filepath = opj(path, filename)
            else:
                filepath = path
        else:
            filepath = get_url_straight_filename(url)

        if exists(filepath) and not overwrite:
            raise DownloadError("File %s already exists" % filepath)

        # TODO:  again very common logic with http download on dealing with download to temp
        # file.  REFACTOR
        target_size = key.size  # S3 specific

        try:
            # TODO All below might be implemented as a context manager which is given
            # target filepath, size, callback for actual download into open fp,
            # callback for checking downloaded content may be even??? or just delegate it
            # always to the authenticator

            temp_filepath = self._get_temp_download_filename(filepath)
            if exists(temp_filepath):
                # eventually we might want to continue the download
                lgr.warning(
                    "Temporary file %s from the previous download was found. "
                    "It will be overriden" % temp_filepath)
                # TODO.  also logic below would clean it up atm



            with open(temp_filepath, 'wb') as f:
                # TODO: url might be a bit too long for the beast.
                # Consider to improve to make it animated as well, or shorten here
                pbar = ui.get_progressbar(label=url, fill_text=filepath, maxval=target_size)

                # S3 specific (the rest is common with e.g. http)
                def pbar_callback(downloaded, totalsize):
                    assert(totalsize == key.size)
                    pbar.update(downloaded)

                key.get_contents_to_file(f, cb=pbar_callback, num_cb=None)

                pbar.finish()
            downloaded_size = os.stat(temp_filepath).st_size

            # TODO: RF Again common check
            if target_size and target_size != downloaded_size:
                lgr.error("Downloaded file size %d differs from originally announced %d",
                          downloaded_size, target_size)

            # place successfully downloaded over the filepath
            os.rename(temp_filepath, filepath)

        # TODO: adjust ctime/mtime according to headers
        # TODO: not hardcoded size, and probably we should check header

        except AccessDeniedError as e:
            raise
        except Exception as e:
            lgr.error("Failed to download {url} into {filepath}: {e}".format(
                **locals()
            ))
            raise DownloadError(str(e))  # for now
        finally:
            if exists(temp_filepath):
                # clean up
                lgr.debug("Removing a temporary download %s", temp_filepath)
                os.unlink(temp_filepath)




        return filepath

    def _check(self, url):
        raise NotImplementedError("check is not yet implemented")
