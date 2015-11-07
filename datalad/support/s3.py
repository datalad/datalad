# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##g
"""Variety of helpers to deal with AWS S3"""

__docformat__ = 'restructuredtext'

import boto
import mimetypes

from boto.s3.key import Key
from boto.exception import S3ResponseError

from os.path import splitext

import keyring
import logging
import datalad.log
lgr = logging.getLogger('datalad.s3')

# TODO: should become a config option and managed along with the rest
S3_ADMIN_CREDENTIAL = "datalad-s3-admin"
S3_TEST_CREDENTIAL = "datalad-s3-test"


def get_bucket_connection(credential):
    # eventually we should be able to have multiple credentials associated
    # with different resources. Thus for now just making an option which
    # one to use
    return boto.connect_s3(
        keyring.get_password(credential, "key_id"),
        keyring.get_password(credential, "secret_id")
    )

class VersionedFilesPool(object):
    """Just a helper which would help to create versioned files in the bucket"""
    def __init__(self, bucket):
        self._versions = {}
        self._bucket = bucket

    def __call__(self, filename, prefix=''):
        self._versions[filename] = version = self._versions.get(filename, 0) + 1
        version_str = "version%d" % version
        # if we are to upload fresh content
        k = Key(self._bucket)
        k.key = filename
        #k.set_contents_from_filename('/home/yoh/.emacs')
        base, ext = splitext(filename)
        load = prefix
        content_type = None
        mtype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = {'Content-Type': mtype}

        if ext == 'html':
            load += '<html><body>%s</body></html>' % version_str
        else:
            load += version_str

        k.set_contents_from_string(load, headers=headers)
        return k

    def reset_version(self, filename):
        self._versions[filename] = 0


def prune_and_delete_bucket(bucket):
    """Deletes all the content and then deletes bucket

    Should be used with care -- no confirmation requested
    """
    bucket.delete_keys(bucket.list_versions(''))
    # this one doesn't work since it generates DeleteMarkers instead ;)
    #for key in b.list_versions(''):
    #    b.delete_key(key)
    bucket.delete()
    lgr.info("Bucket %s was removed"  % bucket.name)

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


def gen_bucket_test0(bucket_name="datalad-test0"):

    conn = get_bucket_connection(S3_ADMIN_CREDENTIAL)
    # assure we have none
    try:
        bucket = conn.get_bucket(bucket_name)
        lgr.info("Deleting existing bucket %s" % bucket.name)
        prune_and_delete_bucket(bucket)
    finally:
        pass

    bucket = conn.create_bucket(bucket_name)

    # Enable web access to that bucket to everyone
    bucket.configure_website('index.html')
    set_bucket_public_access_policy(bucket)

    files = VersionedFilesPool(bucket)

    files("1version-nonversioned1.txt")
    files("2versions-nonversioned1.txt")

    # make bucket versioned AFTER we uploaded one file already
    bucket.configure_versioning(True)

    files("2versions-nonversioned1.txt")
    files("2versions-nonversioned1.txt_sameprefix")
    for v in range(3):
        files("3versions-allversioned.txt")
    files("3versions-allversioned.txt_sameprefix") # to test possible problems

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
    lgr.info("Bucket %s was generated and populated" % bucket_name)

    return bucket


import urllib2
from six.moves.urllib.parse import urljoin, urlparse, urlsplit, urlunsplit, urlunparse, urlencode

def get_versioned_url(url, guarantee_versioned=False, return_all=False, verify=False,
                      s3conn=None):
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

    Returns
    -------
    string or list of string
    """
    url_rec = urlparse(url)

    s3_bucket = None # if AWS S3
    if url_rec.netloc.endswith('.s3.amazonaws.com'):
        if not url_rec.scheme in ('http', 'https'):
            raise ValueError("Do not know how to handle %s scheme" % url_rec.scheme)
        # we know how to slice this cat
        s3_bucket = url_rec.netloc.split('.', 1)[0]
    elif url_rec.scheme == 's3':
        s3_bucket = url_rec.netloc # must be
        # and for now implement magical conversion to URL
        # TODO: wouldn't work if needs special permissions etc
        # actually for now
        raise NotImplementedError

    was_versioned = False
    all_versions = []
    if s3_bucket:
        s3conn = s3conn or get_bucket_connection(S3_TEST_CREDENTIAL)
        bucket = s3conn.get_bucket(s3_bucket)    # TODO cache
        supports_versioning = True  # assume that it does
        try:
            supports_versioning = bucket.get_versioning_status()  # TODO cache
        except S3ResponseError as e:
            # might be forbidden, i.e. "403 Forbidden" so we try then anyways
            supports_versioning = 'maybe'

        if supports_versioning:
            fpath = url_rec.path.lstrip('/')
            all_keys = bucket.list_versions(fpath)
            # Filter and sort them so the newest one on top
            all_keys = [x for x in sorted(all_keys, key=lambda x: (x.last_modified, x.is_latest))
                        if (isinstance(x, Key)    # ignore DeleteMarkers
                            and (x.name == fpath) # match exact name, not just prefix
                            )
                        ][::-1]
            # our current assumptions
            assert(all_keys)
            assert(all_keys[0].is_latest)
            for key in all_keys:
                version_id = key.version_id
                query = ((url_rec.query + "&") if url_rec.query else "")                          + "versionId=%s" % version_id
                url_versioned = urlunparse(url_rec._replace(query=query))
                all_versions.append(url_versioned)
                if verify:
                    # it would throw HTTPError exception if not accessible
                    _ = urllib2.urlopen(urllib2.Request(url))
                was_versioned = True
                if not return_all:
                    break

    if guarantee_versioned and not was_versioned:
        raise RuntimeError("Could not version %s" % url)

    if not all_versions:
        # we didn't get a chance
        all_versions = [urlunparse(url_rec)]

    if return_all:
        return all_versions
    else:
        return all_versions[0]


if __name__ == '__main__':
    import sys
    lgr.setLevel(logging.INFO)
    # TODO: proper cmdline
    if len(sys.argv)>1 and sys.argv[1] == "generate":
        locals()['gen_bucket_%s' % sys.argv[2]]()
    else:
        print "nothing todo"