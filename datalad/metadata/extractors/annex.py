# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 et:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata extractor for Git-annex metadata"""

from datalad.metadata.extractors.base import BaseMetadataExtractor

import logging
lgr = logging.getLogger('datalad.metadata.extractors.annexmeta')
from datalad.log import log_progress

from datalad.support.annexrepo import AnnexRepo
# use main version as core version
# this must stay, despite being a seemingly unused import, each extractor defines a version
from datalad.metadata.definitions import version as vocabulary_version


class MetadataExtractor(BaseMetadataExtractor):

    NEEDS_CONTENT = False

    def _get_dataset_metadata(self):
        return {}

    def _get_content_metadata(self):
        log_progress(
            lgr.info,
            'extractorannex',
            'Start annex metadata extraction from %s', self.ds,
            total=len(self.paths),
            label='Annex metadata extraction',
            unit=' Files',
        )
        repo = self.ds.repo   # OPT: .repo could be relatively expensive
        if not isinstance(repo, AnnexRepo):
            log_progress(
                lgr.info,
                'extractorannex',
                'Finished annex metadata extraction from %s', self.ds
            )
            return

        valid_paths = None
        if self.paths and sum(len(i) for i in self.paths) > 500000:
            valid_paths = set(self.paths)
        for file, meta in repo.get_metadata(
                self.paths if self.paths and valid_paths is None else '.'):
            if file.startswith('.datalad') or valid_paths and file not in valid_paths:
                # do not report on our own internal annexed files (e.g. metadata blobs)
                continue
            log_progress(
                lgr.info,
                'extractorannex',
                'Extracted annex metadata from %s', file,
                update=1,
                increment=True)
            meta = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                    for k, v in meta.items()}
            key = repo.get_file_annexinfo(file).get('key')
            if key:
                meta['key'] = key
            yield (file, meta)
        # we need to make sure that batch processes are terminated
        # otherwise they might cause trouble on windows
        repo.precommit()
        log_progress(
            lgr.info,
            'extractorannex',
            'Finished annex metadata extraction from %s', self.ds
        )
