# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Helper utility to list things.  ATM list content of S3 bucket
"""

__docformat__ = 'restructuredtext'

from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import HTTPError

from .base import Interface
from ..ui import ui
from ..support.s3 import get_key_url
from ..support.param import Parameter
from ..support.constraints import EnsureStr, EnsureNone

from logging import getLogger
lgr = getLogger('datalad.api.ls')

class Ls(Interface):
    """Magical helper to list content of various things (ATM only S3 buckets)

    Examples:

      $ datalad ls s3://openfmri/tarballs/ds202
    """

    _params_ = dict(
        url=Parameter(
            doc="URL to list, e.g. s3:// url",
            constraints=EnsureStr(),
            #nargs='+'
        ),
        config_file=Parameter(
            doc="""Path to config file which could help the 'ls'.  E.g. for s3://
            URLs could be some ~/.s3cfg file which would provide credentials""",
            constraints=EnsureStr() | EnsureNone()
        ),
        list_content=Parameter(
            choices=(None, 'first10', 'md5', 'full'),
            doc="""List also the content or only first 10 bytes (first10), or md5
            checksum of an entry.  Might require expensive
            transfer and dump binary output to your screen.  Do not enable unless
            you know what you are after""",
            default=None
        )
    )

    def __call__(self, url, config_file=None, list_content=False):

        if url.startswith('s3://'):
            bucket_prefix = url[5:]
        else:
            raise ValueError("ATM supporting only s3:// URLs")

        import boto
        from hashlib import md5
        from boto.s3.key import Key
        from boto.exception import S3ResponseError
        from ..support.configparserinc import SafeConfigParser  # provides PY2,3 imports

        bucket_name, prefix = bucket_prefix.split('/', 1)

        if '?' in prefix:
            ui.message("We do not care about URL options ATM, they get stripped")
            prefix = prefix[:prefix.index('?')]

        ui.message("Connecting to bucket: %s" % bucket_name)
        if config_file:
            config = SafeConfigParser(); config.read(config_file)
            access_key = config.get('default', 'access_key')
            secret_key = config.get('default', 'secret_key')

            conn = boto.connect_s3(access_key, secret_key)
            try:
                bucket = conn.get_bucket(bucket_name)
            except S3ResponseError as e:
                ui.message("E: Cannot access bucket %s by name" % bucket_name)
                all_buckets = conn.get_all_buckets()
                all_bucket_names = [b.name for b in all_buckets]
                ui.message("I: Found following buckets %s" % ', '.join(all_bucket_names))
                if bucket_name in all_bucket_names:
                    bucket = all_buckets[all_bucket_names.index(bucket_name)]
                else:
                    raise RuntimeError("E: no bucket named %s thus exiting" % bucket_name)
        else:
            # TODO: expose credentials
            # We don't need any provider here really but only credentials
            from datalad.downloaders.providers import Providers
            providers = Providers.from_config_files()
            provider = providers.get_provider(url)
            if not provider:
                raise ValueError("don't know how to deal with this url %s -- no downloader defined.  Specify just s3cmd config file instead")
            bucket = provider.authenticator.authenticate(bucket_name, provider.credential)


        info = []
        for iname, imeth in [
            ("Versioning", bucket.get_versioning_status),
            ("   Website", bucket.get_website_endpoint),
            ("       ACL", bucket.get_acl),
        ]:
            try:
                ival = imeth()
            except Exception as e:
                ival = str(e).split('\n')[0]
            info.append(" {iname}: {ival}".format(**locals()))
        ui.message("Bucket info:\n %s" % '\n '.join(info))

        prefix_all_versions = list(bucket.list_versions(prefix))

        if not prefix_all_versions:
            ui.error("No output was provided for prefix %r" % prefix)
        else:
            max_length = max((len(e.name) for e in prefix_all_versions))
        for e in prefix_all_versions:
            ui.message(("%%-%ds %%s" % max_length) % (e.name, e.last_modified), cr=' ')
            if isinstance(e, Key):
                url = get_key_url(e, schema='http')
                try:
                    _ = urlopen(Request(url))
                    urlok = "OK"
                except HTTPError as err:
                    urlok = "E: %s" % err.code

                try:
                    acl = e.get_acl()
                except S3ResponseError as err:
                    acl = err.message

                content = ""
                if list_content:
                    # IO intensive, make an option finally!
                    try:
                        # _ = e.next()[:5]  if we are able to fetch the content
                        kwargs = dict(version_id = e.version_id)
                        if list_content in {'full', 'first10'}:
                            if list_content in 'first10':
                                kwargs['headers'] = {'Range': 'bytes=0-9'}
                            content = repr(e.get_contents_as_string(**kwargs))
                        elif list_content == 'md5':
                            digest = md5()
                            digest.update(e.get_contents_as_string(**kwargs))
                            content = digest.hexdigest()
                        else:
                            raise ValueError(list_content)
                        #content = "[S3: OK]"
                    except S3ResponseError as err:
                        content = err.message
                    finally:
                        content = " " + content

                ui.message("ver:%-32s  acl:%s  %s [%s]%s" % (e.version_id, acl, url, urlok, content))
            else:
                ui.message("del")


