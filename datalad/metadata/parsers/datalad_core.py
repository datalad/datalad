# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Metadata parser for Datalad's own core storage"""

from datalad.metadata.parsers.base import BaseMetadataParser

import logging
lgr = logging.getLogger('datalad.meta.datalad_core')

from os.path import join as opj
from os.path import exists

from datalad.support.json_py import load as jsonload
from datalad.support.annexrepo import AnnexRepo
# use main version as core version
# this must stay, despite being a seemingly unused import, each parser defines a version
from datalad.metadata.definitions import version as vocabulary_version


class MetadataParser(BaseMetadataParser):
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
        for file, meta in self.ds.repo.get_metadata(self.paths if self.paths else '.'):
            if file.startswith('.datalad'):
                # do not report on our own internal annexed files (e.g. metadata blobs)
                continue
            meta = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                    for k, v in meta.items()}
            yield (file, meta)
