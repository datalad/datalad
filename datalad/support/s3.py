# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil; coding: utf-8  -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##g
"""Variety of helpers to deal with AWS S3

Use as a script to generate test buckets via e.g.

    python -m datalad.support.s3 generate test1_dirs
"""

__docformat__ = 'restructuredtext'

import mimetypes

from os.path import splitext
import re

from datalad.support.network import urlquote, URL

import logging
import datalad.log  # Just to have lgr setup happen this one used a script
lgr = logging.getLogger('datalad.s3')

from datalad.support.exceptions import (
    CapturedException,
    DownloadError,
    AccessDeniedError,
    AccessPermissionExpiredError,
    AnonymousAccessDeniedError,
)
from datalad.utils import try_multiple_dec

from urllib.request import urlopen, Request


try:
    import boto
    from boto.s3.key import Key
    from boto.exception import S3ResponseError
    from boto.s3.connection import OrdinaryCallingFormat
except Exception as e:
    if not isinstance(e, ImportError):
        lgr.warning(
            "boto module failed to import although available: %s",
            CapturedException(e))
    boto = Key = S3ResponseError = OrdinaryCallingFormat = None


# TODO: should become a config option and managed along with the rest
S3_ADMIN_CREDENTIAL = "datalad-datalad-admin-s3"
S3_TEST_CREDENTIAL = "datalad-datalad-test-s3"


def _get_bucket_connection(credential):
    # eventually we should be able to have multiple credentials associated
    # with different resources. Thus for now just making an option which
    # one to use
    # do full shebang with entering credentials
    from datalad.downloaders.credentials import AWS_S3
    credential = AWS_S3(credential, None)
    if not credential.is_known:
        credential.enter_new()
    creds = credential()
    return boto.connect_s3(creds["key_id"], creds["secret_id"])


def _handle_exception(e, bucket_name):
    """Helper to handle S3 connection exception"""
    raise (
        AccessDeniedError
        if e.error_code == 'AccessDenied'
        else DownloadError)(
            "Cannot connect to %s S3 bucket."
            % (bucket_name)
        ) from e


def _check_S3ResponseError(e):
    """Returns True if should be retried.

    raises ... if token has expired"""
    # https://docs.aws.amazon.com/AmazonS3/latest/API/ErrorResponses.html#ErrorCodeList
    if e.status in (
                    307,  # MovedTemporarily -- DNS updates etc
                    503,  # Slow down -- too many requests, so perfect fit to sleep a bit
                    ):
        return True
    if e.status == 400:
        # Generic Bad Request -- could be many things! generally -- we retry, but
        # some times provide more directed reaction
        # ATM, as used, many requests we send with boto might be just HEAD requests
        # (if I got it right) and we would not receive BODY back with the detailed
        # error_code.  Then we will allow to retry until we get something we know how to
        # handle it more specifically
        if e.error_code == 'ExpiredToken':
            raise AccessPermissionExpiredError(
                "Used token to access S3 has expired") from e
        elif not e.error_code:
            lgr.log(5, "Empty error_code in %s", e)
        return True
    return False


def try_multiple_dec_s3(func):
    """An S3 specific adapter to @try_multiple_dec

    To decorate func to try multiple times after some sleep upon encountering
    some intermittent error from S3
    """
    return try_multiple_dec(
                ntrials=4,
                duration=2.,
                increment_type='exponential',
                exceptions=S3ResponseError,
                exceptions_filter=_check_S3ResponseError,
                logger=lgr.debug,
    )(func)


def get_bucket(conn, bucket_name):
    """A helper to get a bucket

    Parameters
    ----------
    bucket_name: str
        Name of the bucket to connect to
    """
    try:
        return try_multiple_dec_s3(conn.get_bucket)(bucket_name)
    except S3ResponseError as e:
        ce = CapturedException(e)
        # can initially deny or error to connect to the specific bucket by name,
        # and we would need to list which buckets are available under following
        # credentials:
        lgr.debug("Cannot access bucket %s by name with validation: %s",
                  bucket_name, ce)
        if conn.anon:
            raise AnonymousAccessDeniedError(
                "Access to the bucket %s did not succeed.  Requesting "
                "'all buckets' for anonymous S3 connection makes "
                "little sense and thus not supported." % bucket_name,
                supported_types=['aws-s3']
            )

        if e.reason == "Forbidden":
            # Could be just HEAD call boto issues is not allowed, and we should not
            # try to verify that bucket is "reachable".  Just carry on
            try:
                return try_multiple_dec_s3(conn.get_bucket)(bucket_name, validate=False)
            except S3ResponseError as e2:
                lgr.debug("Cannot access bucket %s even without validation: %s",
                          bucket_name, CapturedException(e2))
                _handle_exception(e, bucket_name)

        try:
            all_buckets = try_multiple_dec_s3(conn.get_all_buckets)()
            all_bucket_names = [b.name for b in all_buckets]
            lgr.debug("Found following buckets %s", ', '.join(all_bucket_names))
            if bucket_name in all_bucket_names:
                return all_buckets[all_bucket_names.index(bucket_name)]
        except S3ResponseError as e2:
            lgr.debug("Cannot access all buckets: %s", CapturedException(e2))
            _handle_exception(e, 'any (originally requested %s)' % bucket_name)
        else:
            _handle_exception(e, bucket_name)


class VersionedFilesPool(object):
    """Just a helper which would help to create versioned files in the bucket"""
    def __init__(self, bucket):
        self._versions = {}
        self._bucket = bucket

    @property
    def bucket(self):
        return self._bucket

    def __call__(self, filename, prefix='', load=None):
        self._versions[filename] = version = self._versions.get(filename, 0) + 1
        version_str = "version%d" % version
        # if we are to upload fresh content
        k = Key(self._bucket)
        k.key = filename
        #k.set_contents_from_filename('/home/yoh/.emacs')
        base, ext = splitext(filename)
        #content_type = None
        mtype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = {'Content-Type': mtype}

        if load is None:
            load = prefix
            if ext == 'html':
                load += '<html><body>%s</body></html>' % version_str
            else:
                load += version_str

        k.set_contents_from_string(load, headers=headers)
        return k

    def reset_version(self, filename):
        self._versions[filename] = 0


def get_key_url(e, schema='http', versioned=True):
    """Generate an s3:// or http:// url given a key

    if versioned url is requested but version_id is None, no versionId suffix
    will be added
    """
    # TODO: here we would need to encode the name since urlquote actually
    # can't do that on its own... but then we should get a copy of the thing
    # so we could still do the .format....
    # ... = e.name.encode('utf-8')  # unicode isn't advised in URLs
    e.name_urlquoted = urlquote(e.name)
    if schema == 'http':
        fmt = "http://{e.bucket.name}.s3.amazonaws.com/{e.name_urlquoted}"
    elif schema == 's3':
        fmt = "s3://{e.bucket.name}/{e.name_urlquoted}"
    else:
        raise ValueError(schema)
    if versioned and e.version_id is not None:
        fmt += "?versionId={e.version_id}"
    return fmt.format(e=e)


def prune_and_delete_bucket(bucket):
    """Deletes all the content and then deletes bucket

    Should be used with care -- no confirmation requested
    """
    bucket.delete_keys(bucket.list_versions(''))
    # this one doesn't work since it generates DeleteMarkers instead ;)
    #for key in b.list_versions(''):
    #    b.delete_key(key)
    bucket.delete()
    lgr.info("Bucket %s was removed", bucket.name)


def set_bucket_public_access_policy(bucket):
    # we need to enable permissions for making content available
    bucket.set_policy("""{
      "Version":"2012-10-17",
      "Statement":[{
          "Sid":"AddPerm",
          "Effect":"Allow",
          "Principal": "*",
          "Action":["s3:GetObject", "s3:GetObjectVersion", "s3:GetObjectTorrent", "s3:GetObjectVersionTorrent"],
          "Resource":["arn:aws:s3:::%s/*"]
        }
      ]
    }""" % bucket.name)


def gen_test_bucket(bucket_name):
    conn = _get_bucket_connection(S3_ADMIN_CREDENTIAL)
    # assure we have none
    try:
        bucket = conn.get_bucket(bucket_name)
        lgr.info("Deleting existing bucket %s", bucket.name)
        prune_and_delete_bucket(bucket)
    except:  # MIH: MemoryError?
        # so nothing to worry about
        pass
    finally:
        pass

    return conn.create_bucket(bucket_name)


def _gen_bucket_test0(bucket_name="datalad-test0", versioned=True):

    bucket = gen_test_bucket(bucket_name)

    # Enable web access to that bucket to everyone
    bucket.configure_website('index.html')
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    files("1version-nonversioned1.txt")
    files("2versions-nonversioned1.txt")

    if versioned:
        # make bucket versioned AFTER we uploaded one file already
        bucket.configure_versioning(True)

    files("2versions-nonversioned1.txt")
    files("2versions-nonversioned1.txt_sameprefix")
    for v in range(3):
        files("3versions-allversioned.txt")
    files("3versions-allversioned.txt_sameprefix")  # to test possible problems

    # File which was created and then removed
    bucket.delete_key(files("1version-removed.txt"))

    # File which was created/removed/recreated (with new content)
    bucket.delete_key(files("2versions-removed-recreated.txt"))
    files("2versions-removed-recreated.txt")
    files("2versions-removed-recreated.txt_sameprefix")

    # File which was created/removed/recreated (with new content)
    f = "1version-removed-recreated.txt"
    bucket.delete_key(files(f))
    files.reset_version(f)
    files(f)
    lgr.info("Bucket %s was generated and populated", bucket_name)

    return bucket


def gen_bucket_test0_versioned():
    return _gen_bucket_test0('datalad-test0-versioned', versioned=True)


def gen_bucket_test0_nonversioned():
    return _gen_bucket_test0('datalad-test0-nonversioned', versioned=False)


def gen_bucket_test1_dirs():
    bucket_name = 'datalad-test1-dirs-versioned'
    bucket = gen_test_bucket(bucket_name)
    bucket.configure_versioning(True)

    # Enable web access to that bucket to everyone
    bucket.configure_website('index.html')
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    files("d1", load="")  # creating an empty file
    # then we would like to remove that d1 as a file and make a directory out of it
    files("d1/file1.txt")
    # and then delete it and place it back
    files("d1", load="smth")


def gen_bucket_test2_obscurenames_versioned():
    # in principle bucket name could also contain ., but boto doesn't digest it
    # well
    bucket_name = 'datalad-test2-obscurenames-versioned'
    bucket = gen_test_bucket(bucket_name)
    bucket.configure_versioning(True)

    # Enable web access to that bucket to everyone
    bucket.configure_website('index.html')
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    # http://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html
    files("f 1", load="")
    files("f [1][2]")
    # Need to grow up for this .... TODO
    #files(u"юникод")
    #files(u"юни/код")
    # all fancy ones at once
    files("f!-_.*'( )")
    # the super-fancy which aren't guaranteed to be good idea (as well as [] above)
    files("f &$=@:+,?;")


def gen_bucket_test1_manydirs():
    # to test crawling with flexible subdatasets making decisions
    bucket_name = 'datalad-test1-manydirs-versioned'
    bucket = gen_test_bucket(bucket_name)
    bucket.configure_versioning(True)

    # Enable web access to that bucket to everyone
    bucket.configure_website('index.html')
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    files("d1", load="")  # creating an empty file
    # then we would like to remove that d1 as a file and make a directory out of it
    files("d1/file1.txt")
    files("d1/sd1/file1.txt")
    files("d1/sd2/file3.txt", load="a")
    files("d1/sd2/ssd1/file4.txt")
    files("d2/file1.txt")
    files("d2/sd1/file1.txt")
    files("d2/sd1/ssd/sssd/file1.txt")


def add_version_to_url(url, version, replace=False):
    """Add a version ID to `url`.

    Parameters
    ----------
    url : datalad.support.network.URL
        A URL.
    version : str
        The value of 'versionId='.
    replace : boolean, optional
        If a versionID is already present in `url`, replace it.

    Returns
    -------
    A versioned URL (str)
    """
    version_id = "versionId={}".format(version)
    if not url.query:
        query = version_id
    else:
        ver_match = re.match("(?P<pre>.*&)?"
                             "(?P<vers>versionId=[^&]+)"
                             "(?P<post>&.*)?",
                             url.query)
        if ver_match:
            if replace:
                query = "".join([ver_match.group("pre") or "",
                                 version_id,
                                 ver_match.group("post") or ""])
            else:
                query = url.query
        else:
            query = url.query + "&" + version_id
    return URL(**dict(url.fields, query=query)).as_str()


def get_versioned_url(url, guarantee_versioned=False, return_all=False, verify=False,
                      s3conn=None, update=False):
    """Given a url return a versioned URL

    Originally targeting AWS S3 buckets with versioning enabled

    Parameters
    ----------
    url : string
    guarantee_versioned : bool, optional
      Would fail if buckets is determined to have no versioning enabled.
      It will not fail if we fail to determine if bucket is versioned or
      not
    return_all: bool, optional
      If True, would return a list with URLs for all the versions of this
      file, sorted chronologically with latest first (when possible, e.g.
      for S3).  Remove markers get ignored
    verify: bool, optional
      Verify that URL is accessible. As discovered some versioned keys might
      be denied access to
    update : bool, optional
      If the URL already contains a version ID, update it to the latest version
      ID.  This option has no effect if return_all is true.

    Returns
    -------
    string or list of string
    """
    url_rec = URL(url)

    s3_bucket, fpath = None, url_rec.path.lstrip('/')

    was_versioned = False
    all_versions = []

    if url_rec.hostname.endswith('.s3.amazonaws.com'):
        if url_rec.scheme not in ('http', 'https'):
            raise ValueError("Do not know how to handle %s scheme" % url_rec.scheme)
        # bucket name could have . in it, e.g. openneuro.org
        s3_bucket = url_rec.hostname[:-len('.s3.amazonaws.com')]
    elif url_rec.hostname == 's3.amazonaws.com':
        if url_rec.scheme not in ('http', 'https'):
            raise ValueError("Do not know how to handle %s scheme" % url_rec.scheme)
        # url is s3.amazonaws.com/bucket/PATH
        s3_bucket, fpath = fpath.split('/', 1)
    elif url_rec.scheme == 's3':
        s3_bucket = url_rec.hostname  # must be
        if url_rec.query and 'versionId=' in url_rec.query:
            was_versioned = True
            all_versions.append(url)
        else:
            # and for now implement magical conversion to URL
            # TODO: wouldn't work if needs special permissions etc
            # actually for now
            raise NotImplementedError

    if s3_bucket:
        # TODO: cache
        if s3conn is None:
            # we need to reuse our providers
            from ..downloaders.providers import Providers
            providers = Providers.from_config_files()
            s3url = "s3://%s/" % s3_bucket
            s3provider = providers.get_provider(s3url)
            authenticator = s3provider.authenticator
            if not authenticator:
                # We will use anonymous one
                from ..downloaders.s3 import S3Authenticator
                authenticator = S3Authenticator()
            if authenticator.bucket is not None and authenticator.bucket.name == s3_bucket:
                # we have established connection before, so let's just reuse
                bucket = authenticator.bucket
            else:
                bucket = authenticator.authenticate(s3_bucket, s3provider.credential)  # s3conn or _get_bucket_connection(S3_TEST_CREDENTIAL)
        else:
            bucket = s3conn.get_bucket(s3_bucket)

        supports_versioning = True  # assume that it does
        try:
            supports_versioning = bucket.get_versioning_status()  # TODO cache
        except S3ResponseError as e:
            # might be forbidden, i.e. "403 Forbidden" so we try then anyways
            supports_versioning = 'maybe'

        if supports_versioning:
            all_keys = bucket.list_versions(fpath)
            # Filter and sort them so the newest one on top
            all_keys = [x for x in sorted(all_keys, key=lambda x: (x.last_modified, x.is_latest))
                        if ((x.name == fpath)  # match exact name, not just prefix
                            )
                        ][::-1]
            # our current assumptions
            assert(all_keys[0].is_latest)
            # and now filter out delete markers etc
            all_keys = [x for x in all_keys if isinstance(x, Key)]  # ignore DeleteMarkers
            assert(all_keys)

            for key in all_keys:
                url_versioned = add_version_to_url(
                    url_rec, key.version_id, replace=update and not return_all)

                all_versions.append(url_versioned)
                if verify:
                    # it would throw HTTPError exception if not accessible
                    _ = urlopen(Request(url_versioned))
                was_versioned = True
                if not return_all:
                    break

    if guarantee_versioned and not was_versioned:
        raise RuntimeError("Could not version %s" % url)

    if not all_versions:
        # we didn't get a chance
        all_versions = [url_rec.as_str()]

    if return_all:
        return all_versions
    else:
        return all_versions[0]


if __name__ == '__main__':
    import sys
    lgr.setLevel(logging.INFO)
    # TODO: proper cmdline
    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        if len(sys.argv) < 3:
            raise ValueError("Say 'all' to regenerate all, or give a generators name")
        name = sys.argv[2]
        if name.lower() == 'all':
            for f in locals().keys():
                if f.startswith('gen_bucket_'):
                    locals()[f]()
        else:
            locals()['gen_bucket_%s' % name]()
    else:
        print("nothing todo")
