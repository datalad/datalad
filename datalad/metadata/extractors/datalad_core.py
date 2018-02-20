# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata extractor for Datalad's own core storage"""

from datalad.metadata.extractors.base import BaseMetadataExtractor

import logging
lgr = logging.getLogger('datalad.metadata.extractors.datalad_core')

from os.path import join as opj
from os.path import exists

from datalad.support.json_py import load as jsonload
from datalad.support.annexrepo import AnnexRepo
# use main version as core version
# this must stay, despite being a seemingly unused import, each extractor defines a version
from datalad.metadata.definitions import version as vocabulary_version


class MetadataExtractor(BaseMetadataExtractor):
    _dataset_metadata_filename = opj('.datalad', 'metadata', 'dataset.json')

    def _get_dataset_metadata(self):
        """
        Returns
        -------
        dict
          keys are homogenized datalad metadata keys, values are arbitrary
        """
        fpath = opj(self.ds.path, self._dataset_metadata_filename)
        obj = {}
        if exists(fpath):
            obj = jsonload(fpath, fixup=True)
        if 'definition' in obj:
            obj['@context'] = obj['definition']
            del obj['definition']
        obj['@id'] = self.ds.id
        return obj

    def _get_content_metadata(self):
        """Get ALL metadata for all dataset content.

        Returns
        -------
        generator((location, metadata_dict))
        """
        if not isinstance(self.ds.repo, AnnexRepo):
            for p in self.paths:
                # this extractor does give a response for ANY file as it serves
                # as an indicator of file presence (i.e. a file list) in the
                # content metadata, even if we know nothing but the filename
                # about a file
                yield (p, dict())
            return

        valid_paths = None
        # this is done to avoid passing a too long cmdline arg to git annex
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
