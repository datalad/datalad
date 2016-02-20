# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Basic crawler for the web
"""

import re
from distutils.version import LooseVersion

import os
from os import unlink
from os.path import splitext, dirname, basename, curdir
from os.path import lexists
from os.path import join as opj

from boto.s3.key import Key
from boto.s3.deletemarker import DeleteMarker

from six import iteritems
from ...utils import updated
from ...utils import find_files
from ...dochelpers import exc_str
from ...support.s3 import get_key_url
from ...support.versions import get_versions
from ...downloaders.base import DownloadError, UnhandledRedirectError
from ...downloaders.providers import Providers
from ...downloaders.s3 import S3Downloader

from logging import getLogger
lgr = getLogger('datalad.crawl.s3')

class crawl_s3(object):
    """Given a source bucket and optional prefix, generate s3:// urls for the content

    """
    def __init__(self,
                 bucket,
                 prefix=None,
                 url_schema='s3',
                 strategy='naive'
                 ):
        """

        Parameters
        ----------

        bucket: str
        prefix: str, optional
          Either to remember redirects for subsequent invocations
        """
        self.bucket = bucket
        self.prefix = prefix
        self.url_schema = url_schema
        assert(strategy in {'naive'})
        self.strategy = strategy

    def __call__(self, data):

        url = "s3://%s" % self.bucket
        if self.prefix:
            url += "/" + self.prefix.lstrip('/')
        providers = Providers.from_config_files()
        downloader = providers.get_provider(url).get_downloader(url)

        # bucket = provider.authenticator.authenticate(bucket_name, provider.credential)
        _ = downloader.get_status(url)  # just to authenticate and establish connection
        bucket = downloader.bucket
        assert(bucket is not None)

        # TODO:  we could probably use headers to limit from previously crawled last-modified
        # for now will be inefficient -- fetch all, sort, proceed
        from operator import attrgetter
        all_versions = sorted(bucket.list_versions(self.prefix), key=attrgetter('last_modified'))

        # a set of items which we have already seen/yielded so hitting any of them again
        # would mean conflict/versioning is necessary since two actions came for the same item
        staged = set()
        strategy = self.strategy
        for e in all_versions:
            filename = e.name
            if filename in staged:
                # We should finish this one and commit
                if strategy == 'TODO':
                    yield updated(data, {'datalad-action': 'commit'})
                #raise NotImplementedError
                staged = set()
            staged.add(filename)
            if isinstance(e, Key):
                url = get_key_url(e, schema=self.url_schema)
                # generate and pass along the status right away since we can
                yield updated(
                    data,
                    {
                        'url': url,
                        'url_status': S3Downloader.get_key_status(e, dateformat='iso8601'),
                        'filename': filename
                    })
            elif isinstance(e, DeleteMarker):
                if strategy == 'TODO':
                    yield updated(data, {'filename': filename, 'datalad-action': 'delete'})
                #raise NotImplementedError
            else:
                raise ValueError("Don't know how to treat %s" % e)

                # print all_versions
                # import q; q.d()
