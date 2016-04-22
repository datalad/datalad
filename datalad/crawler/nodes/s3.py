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
import time

from six import iteritems
from ...utils import updated
from ...dochelpers import exc_str
from ...support.s3 import get_key_url
from ...support.network import iso8601_to_epoch
from ...downloaders.providers import Providers
from ...downloaders.s3 import S3Downloader
from ...downloaders.base import TargetFileAbsent
from ..dbs.versions import SingleVersionDB

from logging import getLogger
lgr = getLogger('datalad.crawl.s3')


def get_version_for_key(k, fmt='0.0.%Y%m%d'):
    """Given a key return a version it identifies to be used for tagging

    Uses 0.0.YYYYMMDD by default
    """
    t = iso8601_to_epoch(k.last_modified)
    # format it
    return time.strftime(fmt, time.gmtime(t))


class crawl_s3(object):
    """Given a source bucket and optional prefix, generate s3:// urls for the content

    """
    def __init__(self,
                 bucket,
                 prefix=None,
                 url_schema='s3',
                 strategy='naive',
                 versionfx=get_version_for_key,
                 repo=None,
                 ncommits=None,
                 ):
        """

        Parameters
        ----------

        bucket: str
        prefix: str, optional
          Either to remember redirects for subsequent invocations
        versionfx: function, optional
          If not None, to define a version from the last processed key
        repo: GitRepo, optional
          Under which to store information about latest scraped version
        strategy: {'naive', 'commit-versions'}, optional
          With `naive` strategy no commits are made if there is a deletion,
          or update event, so a single run should result in a single commit
          even though interim different "load" could be added to annex under
          the same filename
        ncommits: int or None, optional
          If specified, used as max number of commits to perform.
          ??? In principle the same effect could be achieved by a node
          raising FinishPipeline after n'th commit
        """
        self.bucket = bucket
        self.prefix = prefix
        self.url_schema = url_schema
        assert(strategy in {'naive', 'commit-versions'})
        self.strategy = strategy
        self.versionfx = versionfx
        self.repo = repo
        self.ncommits = ncommits

    def __call__(self, data):

        stats = data.get('datalad_stats', None)
        url = "s3://%s" % self.bucket
        if self.prefix:
            url += "/" + self.prefix.lstrip('/')
        providers = Providers.from_config_files()
        downloader = providers.get_provider(url).get_downloader(url)

        # bucket = provider.authenticator.authenticate(bucket_name, provider.credential)
        try:
            _ = downloader.get_status(url)  # just to authenticate and establish connection
        except TargetFileAbsent as exc:
            lgr.debug("Initial URL %s lead to not something downloader could fetch: %s", url, exc_str(exc))
            pass
        bucket = downloader.bucket
        assert(bucket is not None)

        if self.repo:
            versions_db = SingleVersionDB(self.repo)
            prev_version = versions_db.version
        else:
            prev_version, versions_db = None, None

        # TODO:  we could probably use headers to limit from previously crawled last-modified
        # for now will be inefficient -- fetch all, sort, proceed
        from operator import attrgetter
        all_versions = bucket.list_versions(self.prefix)
        # Comparison becomes tricky whenever as if in our test bucket we have a collection
        # of rapid changes within the same ms, so they couldn't be sorted by last_modified, so we resolve based
        # on them being marked latest, or not being null (as could happen originally), and placing Delete after creation
        # In real life last_modified should be enough, but life can be as tough as we made it for 'testing'
        cmp = lambda k: (k.last_modified, k.name, k.is_latest, k.version_id != 'null', isinstance(k, DeleteMarker))
        versions_sorted = sorted(all_versions, key=cmp)  # attrgetter('last_modified'))
        # print '\n'.join(map(str, [cmp(k) for k in versions_sorted]))

        version_fields = ['last-modified', 'name', 'version-id']
        def get_version_cmp(k):
            # this one will return action version_id so we could uniquely identify
            return k.last_modified, k.name, k.version_id

        if prev_version:
            last_modified_, name_, version_id_ = [prev_version[f] for f in version_fields]
            # roll forward until we get to the element > this
            # to not breed list copies
            for i, k in enumerate(versions_sorted):
                lm, n, vid = get_version_cmp(k)
                if lm > last_modified_:
                    start = i
                    break
                elif lm == last_modified_:
                    # go by name/version_id to be matched and then switch to the next one
                    if (n, vid) == (name_, version_id_):
                        start = i+1  # from the next one
                        if stats:
                            stats.increment('skipped')
                        break
                stats.increment('skipped')
            versions_sorted = versions_sorted[start:]

        # a set of items which we have already seen/yielded so hitting any of them again
        # would mean conflict/versioning is necessary since two actions came for the same item
        staged = set()
        strategy = self.strategy
        e_prev = None
        ncommits = self.ncommits or 0

        # Adding None so we could deal with the last commit within the loop without duplicating
        # logic later outside
        def update_versiondb(e, force=False):
            # This way we could recover easier after a crash
            # TODO: config crawl.crawl_s3.versiondb.saveaftereach=True
            if force or True:
                versions_db.version = dict(zip(version_fields, get_version_cmp(e)))
        for e in versions_sorted + [None]:
            filename = e.name if e is not None else None
            if filename in staged or e is None:
                # We should finish this one and commit
                if staged:
                    if self.versionfx and e_prev is not None:
                        version = self.versionfx(e_prev)
                        if version not in stats.versions:
                            stats.versions.append(version)
                    if versions_db:
                        # Save current "version" DB so we would know where to pick up from
                        # upon next rerun.  Record should contain
                        # last_modified, name, versionid
                        # TODO?  what if e_prev was a DeleteMarker???
                        update_versiondb(e_prev, force=True)
                    if strategy == 'commit-versions':
                        yield updated(data, {'datalad_action': 'commit'})
                        if self.ncommits:
                            ncommits += 1
                            if self.ncommits <= ncommits:
                                lgr.debug("Interrupting on %dth commit since asked to do %d",
                                          ncommits, self.ncommits)
                                break
                    staged.clear()
                if e is None:
                    break  # we are done
            staged.add(filename)
            if isinstance(e, Key):
                if e.name.endswith('/'):
                    # signals a directory for which we don't care explicitly (git doesn't -- we don't! ;) )
                    continue
                url = get_key_url(e, schema=self.url_schema)
                # generate and pass along the status right away since we can
                yield updated(
                    data,
                    {
                        'url': url,
                        'url_status': S3Downloader.get_key_status(e, dateformat='iso8601'),
                        'filename': filename,
                        'datalad_action': 'annex',
                    })
                update_versiondb(e)
            elif isinstance(e, DeleteMarker):
                if strategy == 'commit-versions':
                    yield updated(data, {'filename': filename, 'datalad_action': 'remove'})
                update_versiondb(e)
            else:
                raise ValueError("Don't know how to treat %s" % e)
            e_prev = e