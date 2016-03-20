# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
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

import logging
import datalad.log  # Just to have lgr setup happen this one used a script
lgr = logging.getLogger('datalad.s3')

from .keyring_ import keyring

from ..dochelpers import exc_str

try:
    import boto
    from boto.s3.key import Key
    from boto.exception import S3ResponseError
except ImportError:
    boto = Key = S3ResponseError = None
except Exception as e:
    lgr.warning("boto module failed to import although available: %s" % exc_str(e))
    boto = Key = S3ResponseError = None


# TODO: should become a config option and managed along with the rest
S3_ADMIN_CREDENTIAL = "datalad-datalad-admin-s3"
S3_TEST_CREDENTIAL = "datalad-datalad-test-s3"


def _get_bucket_connection(credential):
    # eventually we should be able to have multiple credentials associated
    # with different resources. Thus for now just making an option which
    # one to use
    # do full shebang with entering credentials
    from ..downloaders.providers import Credential
    credential = Credential(credential, "aws-s3", None)
    if not credential.is_known:
        credential.enter_new()
    creds = credential()
    return boto.connect_s3(creds["key_id"], creds["secret_id"])

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
        content_type = None
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

def get_key_url(e, schema='http'):
    """Generate an s3:// or http:// url given a key
    """
    if schema == 'http':
        return "http://{e.bucket.name}.s3.amazonaws.com/{e.name}?versionId={e.version_id}".format(e=e)
    elif schema == 's3':
        return "s3://{e.bucket.name}/{e.name}?versionId={e.version_id}".format(e=e)
    else:
        raise ValueError(schema)

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

def gen_test_bucket(bucket_name):
    conn = _get_bucket_connection(S3_ADMIN_CREDENTIAL)
    # assure we have none
    try:
        bucket = conn.get_bucket(bucket_name)
        lgr.info("Deleting existing bucket %s" % bucket.name)
        prune_and_delete_bucket(bucket)
    except:
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


from six.moves.urllib.request import urlopen, Request
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

    s3_bucket, fpath = None, url_rec.path.lstrip('/')

    if url_rec.netloc.endswith('.s3.amazonaws.com'):
        if not url_rec.scheme in ('http', 'https'):
            raise ValueError("Do not know how to handle %s scheme" % url_rec.scheme)
        # we know how to slice this cat
        s3_bucket = url_rec.netloc.split('.', 1)[0]
    elif url_rec.netloc == 's3.amazonaws.com':
        if not url_rec.scheme in ('http', 'https'):
            raise ValueError("Do not know how to handle %s scheme" % url_rec.scheme)
        # url is s3.amazonaws.com/bucket/PATH
        s3_bucket, fpath = fpath.split('/', 1)
    elif url_rec.scheme == 's3':
        s3_bucket = url_rec.netloc # must be
        # and for now implement magical conversion to URL
        # TODO: wouldn't work if needs special permissions etc
        # actually for now
        raise NotImplementedError

    was_versioned = False
    all_versions = []
    if s3_bucket:
        # TODO: cache
        if s3conn is None:
            # we need to reuse our providers
            from ..downloaders.providers import Providers
            providers = Providers.from_config_files()
            s3url = "s3://%s/" % s3_bucket
            s3provider = providers.get_provider(s3url)
            bucket = s3provider.authenticator.authenticate(s3_bucket, s3provider.credential)  # s3conn or _get_bucket_connection(S3_TEST_CREDENTIAL)
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
                        if (isinstance(x, Key)    # ignore DeleteMarkers
                            and (x.name == fpath) # match exact name, not just prefix
                            )
                        ][::-1]
            # our current assumptions
            assert(all_keys)
            assert(all_keys[0].is_latest)
            for key in all_keys:
                version_id = key.version_id
                query = ((url_rec.query + "&") if url_rec.query else "") \
                        + "versionId=%s" % version_id
                url_versioned = urlunparse(url_rec._replace(query=query))
                all_versions.append(url_versioned)
                if verify:
                    # it would throw HTTPError exception if not accessible
                    _ = urlopen(Request(url))
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
