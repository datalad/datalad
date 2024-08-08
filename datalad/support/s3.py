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

import logging
import mimetypes
import re
from pathlib import PurePath
from urllib.request import (
    Request,
    urlopen,
)

import boto3
from botocore.exceptions import ClientError

import datalad.log  # Just to have lgr setup happen this one used a script
from datalad.support.network import URL

lgr = logging.getLogger('datalad.s3')

# TODO: should become a config option and managed along with the rest
S3_ADMIN_CREDENTIAL = "datalad-datalad-admin-s3"
S3_TEST_CREDENTIAL = "datalad-datalad-test-s3"


def _get_s3_resource(credname=None):
    """Creates a boto3 s3 resource

    If credential name is given, DataLad credentials are retrieved or
    entered; otherwise boto3 credential discovery mechanism is used
    (~/.aws/config or env vars). Resources are a higher-level
    abstraction than clients, and seem more fitting for use in this
    module.
    """
    if credname is not None:
        from datalad.downloaders.credentials import AWS_S3
        credential = AWS_S3(credname, None)
        if not credential.is_known:
            credential.enter_new()
        creds = credential()
        session = boto3.session.Session(
            aws_access_key_id=creds["key_id"],
            aws_secret_access_key=creds["secret_id"],
        )
    else:
        session = boto3.session.Session()
    return session.resource("s3")


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
        version_str = f"version{version}"
        mtype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        if load is None:
            load = prefix
            if PurePath(filename).suffix == 'html':
                load += f'<html><body>{version_str}</body></html>'
            else:
                load += version_str

        object = self.bucket.Object(key=filename)
        object.put(
            Body=load.encode(),
            ContentType=mtype,
        )
        return object

    def reset_version(self, filename):
        self._versions[filename] = 0


def prune_and_delete_bucket(bucket):
    """Deletes all the content and then deletes bucket

    Should be used with care -- no confirmation requested
    """
    bucket.object_versions.delete()
    bucket.delete()
    lgr.info("Bucket %s was removed", bucket.name)


def set_bucket_public_access_policy(bucket):
    # we need to enable permissions for making content available
    bucket.Policy().put(Policy="""{
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
    s3 = _get_s3_resource(S3_ADMIN_CREDENTIAL)
    region = s3.meta.client.meta.region_name
    bucket = s3.Bucket(bucket_name)
    # assure we have none
    exists = True
    try:
        s3.meta.client.head_bucket(Bucket=bucket_name)
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            exists = False
        else:
            # likely 403
            raise e
    if exists:
        lgr.info("Deleting existing bucket %s", bucket.name)
        prune_and_delete_bucket(bucket)
    # by default, bucket is created in us-east, leading to constraint exception
    # if user has different (endpoint) region in config - read & use the latter
    bucket.create(CreateBucketConfiguration={"LocationConstraint": region})
    return bucket


def _gen_bucket_test0(bucket_name="datalad-test0", versioned=True):

    bucket = gen_test_bucket(bucket_name)

    # Enable web access to that bucket to everyone
    bucket.Website().put(
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
    )
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    files("1version-nonversioned1.txt")
    files("2versions-nonversioned1.txt")

    if versioned:
        # make bucket versioned AFTER we uploaded one file already
        bucket.Versioning().enable()

    files("2versions-nonversioned1.txt")
    files("2versions-nonversioned1.txt_sameprefix")
    for v in range(3):
        files("3versions-allversioned.txt")
    files("3versions-allversioned.txt_sameprefix")  # to test possible problems

    # File which was created and then removed
    #bucket.delete_key(files("1version-removed.txt"))
    files("1version-removed.txt").delete()

    # File which was created/removed/recreated (with new content)
    files("2versions-removed-recreated.txt").delete()
    files("2versions-removed-recreated.txt")
    files("2versions-removed-recreated.txt_sameprefix")

    # File which was created/removed/recreated (with new content)
    f = "1version-removed-recreated.txt"
    files(f).delete()
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
    bucket.Versioning().enable()

    # Enable web access to that bucket to everyone
    bucket.Website().put(
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
    )
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
    bucket.Versioning().enable()

    # Enable web access to that bucket to everyone
    bucket.Website().put(
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
    )
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
    bucket.Versioning().enable()

    # Enable web access to that bucket to everyone
    bucket.Website().put(
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}}
    )
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
                      s3client=None, update=False):
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
    s3client: botocore.client.S3, optional
      A boto3 client instance that will be used to interact with AWS; if None,
      a new one will be created.
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


    # hostname regex match allowing optional region code
    # bucket-name.s3.region-code.amazonaws.com
    match_virtual_hosted_style = re.match(
        r"^(.+)(\.s3)(?:[.-][a-z0-9-]+){0,1}(\.amazonaws\.com)$", url_rec.hostname
    )
    # s3.region-code.amazonaws.com/bucket-name/key-name
    match_path_style = re.match(
        r"^s3(?:\.[a-z0-9-]+){0,1}(\.amazonaws\.com)$", url_rec.hostname
    )

    if match_virtual_hosted_style is not None:
        s3_bucket = match_virtual_hosted_style.group(1)
    elif match_path_style is not None:
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
        if s3client is None:
            # we need to reuse our providers
            from ..downloaders.providers import Providers
            providers = Providers.from_config_files()
            s3url = "s3://%s/" % s3_bucket
            s3provider = providers.get_provider(s3url)
            authenticator = s3provider.authenticator
            if not authenticator:
                # we will use the default one
                from ..downloaders.s3 import S3Authenticator
                authenticator = S3Authenticator()
            if authenticator.client is not None:
                # we have established connection before, so let's just reuse
                s3client = authenticator.client
            else:
                s3client = authenticator.authenticate(s3_bucket, s3provider.credential)

        supports_versioning = True  # assume that it does
        try:
            # Status can be "Enabled" | "Suspended", or missing altogether
            response = s3client.get_bucket_versioning(Bucket=s3_bucket)
            supports_versioning = response.get("Status") == "Enabled"
        except ClientError as e:
            # might be forbidden, i.e. "403 Forbidden" so we try then anyways
            supports_versioning = 'maybe'

        if supports_versioning:
            response = s3client.list_object_versions(
                Bucket=s3_bucket,
                Prefix=fpath,
            )

            all_keys = response.get("Versions", [])
            # Filter and sort them so the newest one on top
            all_keys = [
                x
                for x in sorted(
                    all_keys,
                    key=lambda x: (x["LastModified"], x["IsLatest"]),
                    reverse=True,
                )
                if ((x["Key"] == fpath))  # match exact name, not just prefix
            ]

            # our current assumptions
            assert all_keys[0]["IsLatest"]

            # boto compatibility note: boto3 response should separate
            # Versions & DeleteMarkers, no action needed

            for key in all_keys:
                url_versioned = add_version_to_url(
                    url_rec, key["VersionId"], replace=update and not return_all)

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
            gb = [k for k in locals().keys() if k.startswith('gen_bucket')]
            for func_name in gb:
                locals()[func_name]()
        else:
            locals()['gen_bucket_%s' % name]()
    else:
        print("nothing to do")
