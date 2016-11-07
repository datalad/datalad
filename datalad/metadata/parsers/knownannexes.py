# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parser for general information on available annexes"""

from datalad.utils import swallow_logs
from datalad.metadata.parsers.base import BaseMetadataParser


class MetadataParser(BaseMetadataParser):

    def has_metadata(self):
        repo = self.ds.repo
        return repo and hasattr(repo, 'repo_info')

    def get_metadata(self, dsid=None, full=False):
        repo = self.ds.repo
        meta = []
        # get all other annex ids, and filter out this one, origin and
        # non-specific remotes
        with swallow_logs():
            # swallow logs, because git annex complains about every remote
            # for which no UUID is configured -- many special remotes...
            repo_info = repo.repo_info(fast=True)
        for src in ('trusted repositories',
                    'semitrusted repositories',
                    'untrusted repositories'):
            for anx in repo_info.get(src, []):
                anxid = anx.get('uuid', '00000000-0000-0000-0000-0000000000')
                if anxid.startswith('00000000-0000-0000-0000-000000000'):
                    # ignore special
                    continue
                anx_meta = self._get_base_metadata_dict(anxid)
                # TODO find a better type; define in context
                anx_meta['@type'] = 'Annex'
                if 'description' in anx:
                    anx_meta['Description'] = anx['description']
                # XXX maybe report which one is local? Available in anx['here']
                # XXX maybe report the type of annex remote?
                meta.append(anx_meta)

        if len(meta):
            dsmeta = self._get_base_metadata_dict(dsid)
            dsmeta['availableFrom'] = [{'@id': m['@id']} for m in meta]
            meta.append(dsmeta)
        return meta
