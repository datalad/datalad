# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
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

from datalad.support.annexrepo import AnnexRepo
# use main version as core version
# this must stay, despite being a seemingly unused import, each extractor defines a version
from datalad.metadata.definitions import version as vocabulary_version


class MetadataExtractor(BaseMetadataExtractor):
    def _get_dataset_metadata(self):
        return {}

    def _get_content_metadata(self):
        if not isinstance(self.ds.repo, AnnexRepo):
            return

        valid_paths = None
        if self.paths and sum(len(i) for i in self.paths) > 500000:
            valid_paths = set(self.paths)
        for file, meta in self.ds.repo.get_metadata(
                self.paths if self.paths and valid_paths is None else '.'):
            if file.startswith('.datalad') or valid_paths and file not in valid_paths:
                # do not report on our own internal annexed files (e.g. metadata blobs)
                continue
            meta = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                    for k, v in meta.items()}
            yield (file, meta)
